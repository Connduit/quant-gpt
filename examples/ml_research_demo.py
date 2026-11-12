"""Run the complete CPU research experiment on explicitly synthetic multi-stock data."""

import argparse
import json
from pathlib import Path

import yaml

from quantlab.research.runner import run_experiment
from quantlab.research.synthetic import synthetic_snapshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/research/milestone-3-demo"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ml-demo-inputs"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; use another directory")
    snapshots, dates = synthetic_snapshots(args.data_dir)
    config = {
        "experiment": {"name": "synthetic_cpu_ranking", "primary_model": "ridge"},
        "data": {
            "data_dir": str(args.data_dir.resolve()),
            "snapshots": snapshots,
            "universe": ["AAA", "BBB", "CCC"],
            "benchmark": "SPY",
            "prediction_horizon": 5,
            "holdout_start": str(dates[-50]),
        },
        "models": [
            {"type": "ridge", "parameters": {"alpha": 10}},
            {"type": "logistic", "objective": "classification"},
            {"type": "random_forest", "parameters": {"n_estimators": 24, "max_depth": 3}},
            {
                "type": "lightgbm",
                "parameters": {"n_estimators": 24, "num_leaves": 7, "min_child_samples": 8},
            },
            {"type": "xgboost", "parameters": {"n_estimators": 24, "max_depth": 3}},
        ],
        "validation": {"training_sessions": 80, "validation_sessions": 30, "test_sessions": 40},
        "strategy": {
            "top_n": 2,
            "rebalance_sessions": 5,
            "maximum_position_weight": 0.4,
            "cash_allocation": 0.2,
        },
        "execution": {"slippage_bps": 5, "spread_bps": 2, "commission_per_share": "0.005"},
    }
    config_path = args.data_dir / "experiment.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    report = run_experiment(config_path, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "synthetic": True,
                "folds": len(report["folds"]),
                "models": list(report["folds"][0]["models"]),
                "conclusion": report["conclusion"],
                "holdout": report["holdout"],
            },
            default=str,
        )
    )


if __name__ == "__main__":
    main()
