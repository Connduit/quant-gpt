"""Run research-only portfolio mechanics using evaluated real-data candidates."""

import argparse
from pathlib import Path

from quantlab.backtesting.report import dumps
from quantlab.portfolio.runner import run_portfolio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("configs/portfolio.example.yaml"))
    p.add_argument("--output", type=Path, default=Path("data/portfolios/milestone-6"))
    p.add_argument("--stress", action="store_true")
    a = p.parse_args()
    r = run_portfolio(a.config, a.output, stress=a.stress)
    print(
        dumps(
            {
                "mode": r["mode"],
                "paper_eligible": r["paper_eligible"],
                "returns": {k: v["performance"]["total_return"] for k, v in r["runs"].items()},
                "final_holdout": r["final_holdout"],
            }
        )
    )


if __name__ == "__main__":
    main()
