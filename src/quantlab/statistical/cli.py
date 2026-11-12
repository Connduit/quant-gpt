"""CLI adapters for validation runs and immutable report inspection."""

from pathlib import Path

from quantlab.backtesting.report import dumps
from quantlab.discovery.common import read_json
from quantlab.statistical.pipeline import run_validation


def execute(args):
    name = args.validation_command
    if name in ("run", "walk-forward", "robustness"):
        report = run_validation(args.validation_config, args.output)
        print(
            dumps(
                {
                    "output": str(args.output),
                    "candidates": [
                        {k: c[k] for k in ("strategy_id", "status", "rejection_reasons")}
                        for c in report["candidates"]
                    ],
                    "paper_trading_shortlist": report["paper_trading_shortlist"],
                    "final_holdout": report["final_holdout"],
                }
            )
        )
    else:
        reports = [
            read_json(Path(p) / "validation.json" if Path(p).is_dir() else Path(p))
            for p in args.reports
        ]
        if name in ("report", "compare"):
            result = (
                reports
                if name == "report"
                else [
                    {
                        "history": r["history"],
                        "candidates": [
                            {k: c[k] for k in ("strategy_id", "status", "rejection_reasons")}
                            for c in r["candidates"]
                        ],
                    }
                    for r in reports
                ]
            )
        else:
            candidates = [c for r in reports for c in r["candidates"]]
            if name in ("list", "rejected", "eligible"):
                result = [
                    {k: c[k] for k in ("strategy_id", "status", "rejection_reasons")}
                    for c in candidates
                    if name == "list"
                    or (
                        c["status"] == "REJECTED"
                        if name == "rejected"
                        else c["status"] == "VALIDATED_FOR_PAPER_TRADING"
                    )
                ]
            elif name == "confidence-intervals":
                result = [
                    {
                        "strategy_id": c["strategy_id"],
                        "uncertainty": c["diagnostics"]["uncertainty"],
                    }
                    for c in candidates
                ]
            else:
                result = [
                    {
                        "history": r["history"],
                        "complexity": r["effective_search_complexity"],
                        "tests": r["multiple_testing"],
                    }
                    for r in reports
                ]
        print(dumps(result))
    return 0
