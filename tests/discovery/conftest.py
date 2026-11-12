from dataclasses import asdict

import pytest
import yaml

from quantlab.features import FeatureConfig
from quantlab.research.synthetic import synthetic_snapshots


@pytest.fixture(scope="session")
def discovery_input(tmp_path_factory):
    root = tmp_path_factory.mktemp("discovery-input")
    snapshots, dates = synthetic_snapshots(root, sessions=180)
    features = FeatureConfig(
        return_windows=(1, 3, 5, 10),
        short_window=3,
        long_window=5,
        atr_window=3,
        rsi_window=3,
        macd_fast=2,
        macd_slow=4,
        macd_signal=2,
        bollinger_window=3,
    )
    experiment = {
        "experiment": {"name": "deterministic_discovery", "primary_model": "ridge"},
        "data": {
            "data_dir": str(root),
            "snapshots": snapshots,
            "universe": ["AAA", "BBB", "CCC"],
            "benchmark": "SPY",
            "prediction_horizon": 5,
            "holdout_start": str(dates[-25]),
        },
        "features": {**asdict(features), "return_windows": list(features.return_windows)},
        "models": [{"type": "ridge"}],
        "validation": {"training_sessions": 40, "validation_sessions": 15, "test_sessions": 30},
        "execution": {"initial_cash": "10000", "slippage_bps": 1, "commission_per_share": ".005"},
    }
    path = root / "experiment.yaml"
    path.write_text(yaml.safe_dump(experiment))
    return path, root, dates


@pytest.fixture
def study_document(discovery_input):
    path, _, _ = discovery_input
    return {
        "study": {
            "name": "unit_discovery",
            "hypothesis": "Explicit synthetic correctness test",
            "experiment": str(path),
            "seed": 42,
            "max_trials": 2,
            "max_wall_seconds": 180,
        },
        "resources": {
            "workers": 2,
            "cpu_threads": 1,
            "memory_mb": 4096,
            "trial_wall_seconds": 60,
            "trial_cpu_seconds": 30,
            "max_attempts": 2,
        },
        "search": {
            "feature_sets": {"momentum": ["momentum", "volatility"]},
            "targets": ["excess_return"],
            "horizons": [5],
            "models": {"ridge": {"alpha": {"type": "float", "low": 0.1, "high": 10, "log": True}}},
            "strategy": {"top_n": {"type": "categorical", "choices": [1, 2]}},
        },
        "eligibility": {
            "minimum_windows": 2,
            "minimum_fills": 0,
            "minimum_exit_fills": 0,
            "maximum_drawdown": 1,
            "maximum_turnover": 1e6,
            "maximum_window_excess_std": 10,
            "minimum_positive_window_fraction": 0,
            "minimum_mean_excess": -10,
            "minimum_mean_baseline_excess": -10,
            "maximum_cost_degradation": 10,
            "maximum_top_trade_profit_share": 1,
        },
        "cost_multipliers": [2],
        "robustness": {"top_k": 0},
    }


@pytest.fixture
def study_file(tmp_path, study_document):
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study_document))
    return path
