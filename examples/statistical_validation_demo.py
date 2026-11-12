"""Validate saved discovery candidates on verified development-only histories."""

import argparse
from pathlib import Path

from quantlab.backtesting.report import dumps
from quantlab.statistical.pipeline import run_validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/validation.example.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/statistical/milestone-5"))
    args = parser.parse_args()
    report = run_validation(args.config, args.output)
    print(
        dumps(
            {
                "candidates": [
                    {k: c[k] for k in ("strategy_id", "status", "rejection_reasons")}
                    for c in report["candidates"]
                ],
                "history": report["history"],
                "paper_trading_shortlist": report["paper_trading_shortlist"],
                "final_holdout": report["final_holdout"],
            }
        )
    )


if __name__ == "__main__":
    main()
