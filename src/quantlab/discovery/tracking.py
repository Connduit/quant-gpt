"""Local SQLite MLflow records are linked to, but separate from, optimization state."""

import math
import time
from pathlib import Path
from threading import Lock

from mlflow import MlflowClient
from mlflow.entities import Metric, Param


class Tracker:
    def __init__(self, root: Path, name: str):
        self.client = MlflowClient(tracking_uri=f"sqlite:///{root.resolve() / 'mlflow.sqlite'}")
        self.lock = Lock()
        with self.lock:
            experiment = self.client.get_experiment_by_name(name)
            self.experiment_id = (
                experiment.experiment_id
                if experiment
                else self.client.create_experiment(
                    name, artifact_location=(root.resolve() / "mlflow-artifacts").as_uri()
                )
            )

    def start(self, identity, attempt, definition, trial_number=None):
        tags = {
            "quantlab.experiment_id": identity,
            "quantlab.attempt_id": attempt["id"],
            "quantlab.role": attempt["role"],
            "quantlab.code_sha256": definition["source_sha256"],
            "quantlab.dataset_seal": definition["seal_id"],
            "quantlab.hypothesis": definition["hypothesis"],
            "quantlab.evaluation_role": "search_validation",
            "quantlab.holdout": "not_accessible",
            "quantlab.synthetic": str(definition["synthetic"]),
        }
        if definition.get("git_commit"):
            tags["mlflow.source.git.commit"] = definition["git_commit"]
        if trial_number is not None:
            tags["quantlab.optuna_trial"] = str(trial_number)
        if attempt.get("parent_id"):
            tags["quantlab.parent_attempt"] = attempt["parent_id"]
        with self.lock:
            run = self.client.create_run(self.experiment_id, tags=tags, run_name=attempt["id"])
            params = {
                "target": definition["target"],
                "horizon": definition["horizon"],
                "model": definition["model"]["type"],
                "seed": definition["model"]["seed"],
                "feature_groups": ",".join(definition["groups"]),
                "training_sessions": definition["training_sessions"],
                "validation_sessions": definition["validation_sessions"],
                "test_sessions": definition["test_sessions"],
            }
            params.update(
                {f"model.{key}": value for key, value in definition["model"]["parameters"].items()}
            )
            params.update(
                {f"strategy.{key}": value for key, value in definition["strategy"].items()}
            )
            params.update({f"cost.{key}": value for key, value in definition["execution"].items()})
            self.client.log_batch(
                run.info.run_id, params=[Param(k, str(v)) for k, v in params.items()]
            )
        return run.info.run_id

    def finish(self, run_id, status, output: Path, result=None, reason=None):
        with self.lock:
            self.client.set_tag(run_id, "quantlab.status", status)
            if reason:
                self.client.set_tag(run_id, "quantlab.reason", reason[:3000])
            if result:
                summary = result["summary"]
                metrics = [
                    Metric(key, float(value), int(time.time() * 1000), 0)
                    for key, value in summary.items()
                    if isinstance(value, (float, int))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                ]
                self.client.log_batch(run_id, metrics=metrics)
                self.client.set_tag(run_id, "quantlab.eligible", str(summary["eligible"]))
                self.client.set_tag(
                    run_id, "quantlab.rejection_reasons", ",".join(summary["rejection_reasons"])
                )
                self.client.log_param(
                    run_id, "selected_features", ",".join(result["selected_features"])
                )
            if output.exists():
                self.client.log_artifacts(run_id, str(output))
            self.client.set_terminated(
                run_id,
                "FINISHED"
                if status in ("COMPLETE", "REJECTED")
                else "KILLED"
                if status in ("PRUNED", "INTERRUPTED", "NOT_RUN_BUDGET")
                else "FAILED",
            )
