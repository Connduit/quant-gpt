import copy
from pathlib import Path

import polars as pl
import pytest

from quantlab.discovery.config import load_study
from quantlab.discovery.data import prepare
from quantlab.discovery.engine import ExperimentEngine
from quantlab.discovery.study import definition_for_number
from quantlab.statistical.pipeline import history, return_folds


def test_validation_retrain_gap_delay_and_lineage(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "inputs")
    definition = definition_for_number(config, base, 0)
    definition.update(
        gap_sessions=2, retraining_sessions=20, execution_delay_sessions=1, expanding=False
    )
    engine = ExperimentEngine(tmp_path / "validation", config.name, config.resources)
    result = engine.run(definition, role="statistical_validation", parent_id="prior-discovery")
    assert result["result"], result["attempt"]
    path = Path(result["attempt"]["artifact_path"])
    folds = return_folds(path, definition["holdout_start"])
    assert len(folds) >= 2
    assert max(d for f in folds for d in f["dates"]) < definition["holdout_start"]
    predictions = pl.read_parquet(path / "predictions.parquet")
    assert (predictions["train_label_max"] < predictions["model_available_at"]).all()
    assert (predictions["model_available_at"] <= predictions["prediction_at"]).all()
    assert history([tmp_path / "validation"])["unique_hypotheses"] == 1
    # A source data edit must not silently change validation inputs.
    changed = copy.deepcopy(definition)
    changed["holdout_start"] = "2000-01-01"
    failed = engine.run(changed, role="statistical_validation")
    assert failed["result"] is None
    assert failed["attempt"]["status"] not in ("COMPLETE", "REJECTED")
    assert history([tmp_path / "validation"])["unique_hypotheses"] == 2


def test_return_artifacts_reject_holdout_and_overlap(tmp_path):
    from quantlab.discovery.common import write_json

    directory = tmp_path / "window-0" / "backtest"
    directory.mkdir(parents=True)
    write_json(tmp_path / "result.json", {"windows": [{"number": 0}]})
    for name in ("equity", "benchmark_equity"):
        (directory / f"{name}.csv").write_text("session_date,daily_return\n2019-01-02,0.1\n")
    import hashlib

    write_json(
        directory / "report.json",
        {
            "artifacts_sha256": {
                f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in directory.glob("*.csv")
            }
        },
    )
    with pytest.raises(ValueError, match="Holdout"):
        return_folds(tmp_path, "2019-01-02")
    (directory / "equity.csv").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        return_folds(tmp_path, "2019-01-02")
