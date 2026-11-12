"""Real LEAN historical sample discovery; synthetic data only with explicit --synthetic."""

import argparse
import json
from datetime import date
from pathlib import Path

import yaml

from quantlab.data.providers.lean import import_lean_universe
from quantlab.discovery.study import run_study
from quantlab.research.synthetic import synthetic_snapshots


def write_configs(data_dir, snapshots, *, synthetic=False, trials=4, workers=2):
    experiment = {
        "experiment": {"name": "bounded_discovery_input", "primary_model": "ridge"},
        "data": {
            "data_dir": str(data_dir.resolve()),
            "snapshots": snapshots,
            "benchmark": "SPY",
            "universe": [s for s in snapshots if s != "SPY"],
            "prediction_horizon": 5,
            "holdout_start": "2023-03-29" if synthetic else "2019-01-02",
        },
        "models": [{"type": "ridge"}],
        "validation": {
            "training_sessions": 80 if synthetic else 504,
            "validation_sessions": 30 if synthetic else 126,
            "test_sessions": 40 if synthetic else 126,
            "embargo_sessions": 1,
        },
        "strategy": {
            "top_n": 2 if synthetic else 3,
            "cash_allocation": 0.2,
            "maximum_position_weight": 0.4 if synthetic else 0.3,
            "minimum_dollar_volume": 1e6,
        },
        "execution": {
            "initial_cash": "100000",
            "commission_per_share": ".005",
            "slippage_bps": 5,
            "spread_bps": 2,
        },
    }
    base = data_dir / "discovery-research.yaml"
    base.write_text(yaml.safe_dump(experiment, sort_keys=False))
    study = {
        "study": {
            "name": "synthetic_discovery_check" if synthetic else "lean_factor_proxy_discovery",
            "hypothesis": (
                "Test whether bounded causal feature/model/ranking variants "
                "beat SPY and simpler baselines after costs."
            ),
            "experiment": str(base.resolve()),
            "seed": 42,
            "max_trials": trials,
            "max_wall_seconds": 900,
        },
        "resources": {
            "workers": workers,
            "cpu_threads": 1,
            "memory_mb": 4096,
            "trial_wall_seconds": 180,
            "trial_cpu_seconds": 120,
            "max_attempts": 2,
        },
        "search": {
            "feature_sets": {
                "momentum_volume": ["momentum", "volume", "relative_strength"],
                "reversion_regime": ["mean_reversion", "volatility", "market_regime"],
                "technical": ["technical", "market_regime"],
            },
            "targets": ["excess_return", "stock_return", "direction", "volatility"],
            "horizons": [1, 5, 10],
            "models": {
                "ridge": {"alpha": {"type": "float", "low": 0.1, "high": 20, "log": True}},
                "logistic": {"C": {"type": "float", "low": 0.1, "high": 10, "log": True}},
                "random_forest": {
                    "n_estimators": {"type": "int", "low": 8, "high": 16, "step": 4},
                    "max_depth": {"type": "int", "low": 2, "high": 4},
                },
                "lightgbm": {
                    "n_estimators": {"type": "int", "low": 8, "high": 16, "step": 4},
                    "num_leaves": {"type": "int", "low": 4, "high": 8},
                },
                "xgboost": {
                    "n_estimators": {"type": "int", "low": 8, "high": 16, "step": 4},
                    "max_depth": {"type": "int", "low": 2, "high": 4},
                },
            },
            "strategy": {
                "top_n": {"type": "categorical", "choices": [1, 2] if synthetic else [2, 3]},
                "rebalance_sessions": {"type": "categorical", "choices": [5, 10]},
                "position_sizing": {
                    "type": "categorical",
                    "choices": ["equal", "inverse_volatility"],
                },
                "volatility_adjusted": {"type": "categorical", "choices": [False, True]},
                "regime_filter": {"type": "categorical", "choices": [False, True]},
            },
        },
        "cost_multipliers": [2],
        "robustness": {
            "top_k": 1,
            "max_variants": 6,
            "include_rejected_for_diagnostics": True,
            "parameter_fraction": 0.2,
            "window_fraction": 0.2,
        },
    }
    path = data_dir / "discovery-study.yaml"
    path.write_text(yaml.safe_dump(study, sort_keys=False))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/discovery/real-demo"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/discovery-real-inputs"))
    parser.add_argument(
        "--synthetic", action="store_true", help="Explicit software-test fixture alternative"
    )
    parser.add_argument(
        "--allow-factor-proxy",
        action="store_true",
        help="Acknowledge missing actual pay dates and uncertified event completeness",
    )
    parser.add_argument("--trials", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.root.exists():
        parser.error("Use a new root, or resume the saved study with the CLI")
    if args.synthetic:
        snapshots, _ = synthetic_snapshots(args.data_dir)
    else:
        report = import_lean_universe(
            args.data_dir,
            date(2014, 4, 3),
            date(2019, 12, 31),
            allow_factor_proxy=args.allow_factor_proxy,
        )
        snapshots = report["snapshots"]
    path = write_configs(
        args.data_dir, snapshots, synthetic=args.synthetic, trials=args.trials, workers=args.workers
    )
    result = run_study(path, args.root)
    print(
        json.dumps(
            {
                "config": str(path),
                "root": str(args.root),
                "synthetic": args.synthetic,
                "eligible": len(result["eligible"]),
                "rejected_or_failed": len(result["rejected_or_failed"]),
                "counts": result["counts"],
                "final_holdout": "not_evaluated",
            }
        )
    )


if __name__ == "__main__":
    main()
