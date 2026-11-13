import copy
import time
from dataclasses import replace
from pathlib import Path

import optuna
import pytest
import yaml
from mlflow import MlflowClient

from quantlab.discovery.config import load_study
from quantlab.discovery.data import prepare
from quantlab.discovery.engine import ExperimentEngine
from quantlab.discovery.registry import Registry
from quantlab.discovery.study import definition_for_number, run_single, run_study


def test_subprocess_mlflow_duplicate_and_exact_reproduction(study_file, tmp_path):
    root = tmp_path / "experiments"
    first = run_single(study_file, root)
    assert first["attempt"]["status"] == "REJECTED", first["attempt"]["reason"]
    assert "nonpositive_net_return" in first["result"]["summary"]["rejection_reasons"]
    assert first["result"]["holdout"]["status"] == "not_accessible_to_trials"
    assert len(first["result"]["windows"]) >= 2
    duplicate = run_single(study_file, root)
    assert duplicate["duplicate"] and duplicate["attempt"]["id"] == first["attempt"]["id"]
    client = MlflowClient(tracking_uri=f"sqlite:///{root / 'mlflow.sqlite'}")
    tracked = client.get_run(first["attempt"]["run_id"])
    assert tracked.info.status == "FINISHED"
    assert tracked.data.tags["quantlab.evaluation_role"] == "search_validation"
    assert tracked.data.tags["quantlab.experiment_id"] == first["experiment_id"]
    assert "score" in tracked.data.metrics and "model.alpha" in tracked.data.params
    assert any(a.path == "result.json" for a in client.list_artifacts(tracked.info.run_id))
    repeated = run_single(study_file, root, reproduce_id=first["attempt"]["id"])
    assert not repeated["duplicate"]
    assert repeated["result"]["summary"] == first["result"]["summary"]
    original = Registry(root).attempt(first["attempt"]["id"])
    assert original["status"] == "REJECTED" and original["number"] == 1
    for previous, next_window in zip(
        first["result"]["windows"], first["result"]["windows"][1:], strict=False
    ):
        assert previous["label_known_max"] < next_window["prediction_start"]
    for window in first["result"]["windows"]:
        assert window["evaluation_role"] == "search_validation"
        assert "in_sample" in window and "inner_validation" in window
        assert window["fitted_at"] > window["train_label_max"]
        assert "2" in window["cost_stress"]


def test_failed_worker_is_retained_and_retry_is_bounded(study_file, tmp_path):
    config = load_study(study_file)
    root = tmp_path / "failures"
    base = prepare(config, root)
    definition = definition_for_number(config, base, 0)
    definition["model"]["parameters"]["alpha"] = -1
    engine = ExperimentEngine(root, config.name, config.resources)
    one = engine.run(definition)
    assert one["attempt"]["status"] == "FAILED"
    assert (
        one["attempt"]["reason"]
        and (Path(one["attempt"]["artifact_path"]) / "failure.json").exists()
    )
    two = engine.run(definition)
    assert two["attempt"]["number"] == 2
    three = engine.run(definition)
    assert three["duplicate"] and three["attempt"]["id"] == two["attempt"]["id"]
    assert len(engine.registry.rows()) == 2


def test_wall_memory_and_cpu_limits_are_reported(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "input")
    definition = definition_for_number(config, base, 0)
    expired = ExperimentEngine(tmp_path / "expired", config.name, config.resources)
    result = expired.run(definition, deadline=time.monotonic() - 1)
    assert result["attempt"]["status"] == "NOT_RUN_BUDGET"
    assert result["result"] is None
    limited = ExperimentEngine(
        tmp_path / "memory", config.name, replace(config.resources, memory_mb=128)
    )
    result = limited.run(definition)
    assert result["attempt"]["status"] == "MEMORY_LIMIT", result["attempt"]["reason"]
    busy = copy.deepcopy(definition)
    busy["model"] = {
        "type": "random_forest",
        "objective": "regression",
        "seed": 42,
        "parameters": {"n_estimators": 5000},
    }
    wall = ExperimentEngine(
        tmp_path / "wall",
        config.name,
        replace(config.resources, trial_wall_seconds=1, trial_cpu_seconds=30),
    )
    result = wall.run(busy)
    assert result["attempt"]["status"] == "TIMEOUT"
    cpu = ExperimentEngine(
        tmp_path / "cpu", config.name, replace(config.resources, trial_cpu_seconds=1)
    )
    result = cpu.run(busy)
    assert result["attempt"]["status"] == "CPU_LIMIT", result["attempt"]["reason"]


def test_optuna_persistence_parallel_trials_and_resume(study_file, tmp_path):
    root = tmp_path / "study"
    report = run_study(study_file, root)
    assert report["study"]["trials"] == 2
    assert report["counts"]["optuna_trials"] == 2
    state = optuna.load_study(
        study_name="unit_discovery", storage=f"sqlite:///{root / 'optuna.sqlite'}"
    )
    assert all(t.state == optuna.trial.TrialState.COMPLETE for t in state.trials)
    for trial in state.trials:
        assert trial.user_attrs["attempt_id"] and trial.user_attrs["mlflow_run_id"]
        assert trial.user_attrs["experiment_id"]
    before = len(Registry(root).rows())
    resumed = run_study(study_file, root, resume=True)
    assert resumed["study"]["trials"] == 2 and len(Registry(root).rows()) == before
    with pytest.raises(ValueError, match="resume"):
        run_study(study_file, root)


def test_optuna_validation_boundary_pruning(study_document, tmp_path):
    study_document["study"]["max_trials"] = 1
    study_document["prune_below"] = 1e6
    path = tmp_path / "prune.yaml"
    path.write_text(yaml.safe_dump(study_document))
    root = tmp_path / "prune"
    report = run_study(path, root)
    assert not report["eligible"]
    state = optuna.load_study(
        study_name="unit_discovery", storage=f"sqlite:///{root / 'optuna.sqlite'}"
    )
    assert state.trials[0].state == optuna.trial.TrialState.PRUNED
    assert Registry(root).rows()[0]["status"] == "PRUNED"


def test_resume_recovers_interrupted_optimizer_trial(study_file, tmp_path):
    root = tmp_path / "interrupted"
    root.mkdir()
    state = optuna.create_study(
        study_name="unit_discovery", storage=f"sqlite:///{root / 'optuna.sqlite'}"
    )
    trial = state.ask()
    trial.set_user_attr("owner_pid", 987654321)
    trial.set_user_attr("owner_start", 0)
    report = run_study(study_file, root, resume=True)
    loaded = optuna.load_study(
        study_name="unit_discovery", storage=f"sqlite:///{root / 'optuna.sqlite'}"
    )
    assert loaded.trials[0].state == optuna.trial.TrialState.FAIL
    assert loaded.trials[1].state == optuna.trial.TrialState.COMPLETE
    assert report["counts"]["optuna_trials"] == 2
    assert any(row["disposition"] == "INTERRUPTED" for row in report["trial_history"])


def test_tracking_failure_preserves_result_and_can_be_retried(study_file, tmp_path, monkeypatch):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "input")
    definition = definition_for_number(config, base, 0)
    engine = ExperimentEngine(tmp_path / "tracking", config.name, config.resources)
    original = engine.tracker.finish

    def fail(*args, **kwargs):
        raise OSError("simulated artifact tracking failure")

    monkeypatch.setattr(engine.tracker, "finish", fail)
    failed = engine.run(definition)
    assert failed["attempt"]["status"] == "TRACKING_FAILED" and failed["result"] is not None
    assert (Path(failed["attempt"]["artifact_path"]) / "result.json").exists()
    monkeypatch.setattr(engine.tracker, "finish", original)
    retry = engine.run(definition)
    assert retry["attempt"]["status"] == "REJECTED"
    assert "nonpositive_net_return" in retry["result"]["summary"]["rejection_reasons"]
    assert failed["result"]["summary"] == retry["result"]["summary"]
    assert engine.registry.attempt(failed["attempt"]["id"])["status"] == "TRACKING_FAILED"


def test_batch_records_every_candidate_when_preparation_uses_budget(
    study_document, tmp_path, monkeypatch
):
    import quantlab.discovery.study as orchestration

    study_document["study"]["max_wall_seconds"] = 1
    path = tmp_path / "batch.yaml"
    path.write_text(yaml.safe_dump(study_document))
    original = orchestration.prepare

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        time.sleep(1.1)
        return result

    monkeypatch.setattr(orchestration, "prepare", delayed)
    common = {
        "target": "excess_return",
        "model_for_excess_return": "ridge",
        "feature_set": "momentum",
        "horizon": 5,
        "strategy.top_n": 1,
    }
    root = tmp_path / "batch"
    outcomes = orchestration.run_batch(
        path, root, [{**common, "model.ridge.alpha": 1}, {**common, "model.ridge.alpha": 2}]
    )
    assert len(outcomes) == 2
    assert all(r["attempt"]["status"] == "NOT_RUN_BUDGET" for r in outcomes)
    assert all(r["attempt"]["child_pid"] is None for r in outcomes)
    assert len(Registry(root).rows()) == 2
