from pathlib import Path

import pytest

from quantlab.discovery.config import load_study
from quantlab.discovery.data import prepare, verify_seal, worker_data
from quantlab.discovery.study import definition_for_number


def test_holdout_is_physically_absent_from_worker_inputs(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "registry")
    seal = verify_seal(Path(base["sealed_dir"]), base["seal_sha256"])
    assert seal["holdout_sessions_excluded"] == 25
    definition = definition_for_number(config, base, 0)
    feeds, frame, features, _ = worker_data(definition)
    assert all(str(b.session_date) < base["holdout_start"] for d in feeds.values() for b in d.bars)
    assert frame["label_end_at"].max().date().isoformat() < base["holdout_start"]
    assert "target" not in features and "label_known_at" not in features
    assert (
        definition.get("data_dir") is None
    )  # original snapshot store is not an objective capability
    assert all(d.manifest["provider"] == "discovery-development" for d in feeds.values())
    again = prepare(config, tmp_path / "registry")
    assert again["seal_id"] == base["seal_id"] and again["seal_sha256"] == base["seal_sha256"]
    assert (Path(base["sealed_dir"]) / "features.parquet").exists()


def test_seal_tampering_and_policy_changes_fail_closed(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "registry")
    definition = definition_for_number(config, base, 0)
    changed = dict(definition, holdout_start="2022-01-01")
    with pytest.raises(ValueError, match="policy"):
        worker_data(changed)
    path = Path(base["sealed_dir"]) / "features.parquet"
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        worker_data(definition)


def test_target_modes_remain_causal_and_have_appropriate_labels(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "registry")
    definition = definition_for_number(config, base, 0)
    for target in ("excess_return", "stock_return", "direction", "volatility"):
        _, frame, features, _ = worker_data(dict(definition, target=target))
        assert (frame["prediction_at"] < frame["execution_at"]).all()
        assert (frame["execution_at"] < frame["label_known_at"]).all()
        if target == "stock_return":
            assert frame["target"].equals(frame["forward_return"])
        if target == "volatility":
            assert (frame["target"] >= 0).all()
        assert "future_volatility" not in features


def test_horizon_candidates_share_evaluation_calendar(study_document, tmp_path):
    import yaml

    study_document["search"]["horizons"] = [1, 5, 10]
    path = tmp_path / "multi-horizon.yaml"
    path.write_text(yaml.safe_dump(study_document))
    config = load_study(path)
    base = prepare(config, tmp_path / "registry")
    definition = definition_for_number(config, base, 0)
    dates = []
    for horizon in (1, 5, 10):
        _, frame, features, _ = worker_data(dict(definition, horizon=horizon))
        dates.append(frame.select("symbol", "session_date").to_dicts())
        assert "boundary_known_at" not in features
        assert (frame["label_known_at"] <= frame["boundary_known_at"]).all()
    assert dates[0] == dates[1] == dates[2]
