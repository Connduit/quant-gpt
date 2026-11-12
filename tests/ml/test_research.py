import json
import os
from dataclasses import asdict

import polars as pl
import pytest
import yaml

from quantlab.cli import main
from quantlab.ml.models import ResearchModel
from quantlab.research.config import RankingConfig, load_experiment
from quantlab.research.runner import run_experiment


def configuration(ml_feeds, small_features):
    _, snapshots, dates, root = ml_feeds
    return {
        "experiment": {"name": "explicit_synthetic_integration", "primary_model": "ridge"},
        "data": {
            "data_dir": str(root),
            "snapshots": snapshots,
            "universe": ["AAA", "BBB", "CCC"],
            "benchmark": "SPY",
            "prediction_horizon": 5,
            "holdout_start": str(dates[-25]),
        },
        "features": {
            **asdict(small_features),
            "return_windows": list(small_features.return_windows),
        },
        "models": [
            {"type": "ridge"},
            {"type": "logistic", "objective": "classification"},
            {"type": "random_forest", "parameters": {"n_estimators": 8}},
            {"type": "lightgbm", "parameters": {"n_estimators": 8, "min_child_samples": 5}},
            {"type": "xgboost", "parameters": {"n_estimators": 8, "max_depth": 2}},
        ],
        "validation": {"training_sessions": 40, "validation_sessions": 15, "test_sessions": 40},
        "strategy": {
            "top_n": 2,
            "rebalance_sessions": 5,
            "cash_allocation": 0.2,
            "maximum_position_weight": 0.4,
        },
    }


def test_full_research_all_models_oos_exports_and_repeatability(ml_feeds, small_features, tmp_path):
    config = configuration(ml_feeds, small_features)
    path = tmp_path / "experiment.yaml"
    config["data"]["data_dir"] = os.path.relpath(config["data"]["data_dir"], tmp_path)
    path.write_text(yaml.safe_dump(config))
    first = run_experiment(path, tmp_path / "one")
    second = run_experiment(path, tmp_path / "two")
    assert load_experiment(tmp_path / "one" / "configuration.yaml").data_dir == ml_feeds[3]
    assert first["holdout"]["status"] == "not_evaluated"
    assert first["synthetic"] is True
    assert first["trading"] == second["trading"]
    assert set(first["trading"]) == {
        "ml",
        "random",
        "momentum",
        "mean_reversion",
        "equal_weight",
        "spy_buy_hold",
    }
    assert set(first["folds"][0]["models"]) == {
        "ridge",
        "logistic",
        "random_forest",
        "lightgbm",
        "xgboost",
    }
    predictions = pl.read_parquet(tmp_path / "one" / "out_of_sample_predictions.parquet")
    assert (predictions["train_label_max"] < predictions["model_available_at"]).all()
    assert (predictions["model_available_at"] <= predictions["prediction_at"]).all()
    assert (predictions["prediction_at"] < predictions["execution_at"]).all()
    assert predictions["label_end_at"].max().date() < load_experiment(path).holdout_start
    model = ResearchModel.load(tmp_path / "one" / "models" / "fold-0" / "ridge")
    sample = predictions.filter((pl.col("fold") == 0) & (pl.col("model") == "ridge"))
    assert model.predict(sample).tolist() == sample["prediction"].to_list()
    assert first["trading"]["ml"]["performance"]["fill_count"] > 0
    for mode in first["trading"]:
        if mode == "spy_buy_hold":
            continue
        artifact = tmp_path / "one" / "backtests" / mode / "report.json"
        assert artifact.exists()
        assert (artifact.parent / "positions.csv").exists()
    if not first["ml_outperformed_all_baselines"]:
        assert "did not outperform" in first["conclusion"]
    with pytest.raises(ValueError, match="exists"):
        run_experiment(path, tmp_path / "one")


def test_research_cli_and_configuration_rejection(ml_feeds, small_features, tmp_path, capsys):
    config = configuration(ml_feeds, small_features)
    config["models"] = [{"type": "ridge"}]
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config))
    assert main(["research", "--experiment", str(path), "--output", str(tmp_path / "cli")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["synthetic"] and result["folds"] > 0
    config["strategy"]["unknown_rule"] = True
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="Unknown"):
        load_experiment(path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"top_n": 0},
        {"cash_allocation": 1},
        {"maximum_position_weight": 1.1},
        {"minimum_dollar_volume": float("nan")},
        {"rebalance_sessions": True},
    ],
)
def test_ranking_limits_fail_closed(kwargs):
    with pytest.raises(ValueError):
        RankingConfig(**kwargs)
