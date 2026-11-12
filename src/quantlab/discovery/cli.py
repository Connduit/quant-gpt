"""Optional discovery commands are imported only when explicitly invoked."""

import json

import yaml

from quantlab.backtesting.report import dumps
from quantlab.discovery.registry import Registry
from quantlab.discovery.reports import comparison, generate_report
from quantlab.discovery.study import run_batch, run_single, run_study


def execute(args):
    name = args.discovery_command
    if name in ("study", "resume"):
        report = run_study(args.study, args.root, resume=name == "resume")
        print(
            dumps(
                {
                    "counts": report["counts"],
                    "eligible": len(report["eligible"]),
                    "rejected_or_failed": len(report["rejected_or_failed"]),
                    "study": report["study"],
                }
            )
        )
    elif name == "run":
        params = yaml.safe_load(args.parameters.read_text()) if args.parameters else None
        result = run_single(args.study, args.root, params)
        print(
            dumps(
                {
                    "experiment_id": result["experiment_id"],
                    "attempt_id": result["attempt"]["id"],
                    "status": result["attempt"]["status"],
                    "duplicate": result["duplicate"],
                }
            )
        )
    elif name == "batch":
        results = run_batch(
            args.study, args.root, [yaml.safe_load(p.read_text()) for p in args.parameters]
        )
        print(
            dumps(
                [
                    {
                        "experiment_id": r["experiment_id"],
                        "attempt_id": r["attempt"]["id"],
                        "status": r["attempt"]["status"],
                    }
                    for r in results
                ]
            )
        )
    elif name == "reproduce":
        result = run_single(args.study, args.root, reproduce_id=args.attempt_id)
        original = Registry(args.root).attempt(args.attempt_id)
        previous = json.loads(original["result"]) if original["result"] else None
        print(
            dumps(
                {
                    "attempt_id": result["attempt"]["id"],
                    "status": result["attempt"]["status"],
                    "summary_matches": bool(
                        previous
                        and result["result"]
                        and previous["summary"] == result["result"]["summary"]
                    ),
                }
            )
        )
    elif name == "list":
        print(
            dumps(
                [
                    {k: r[k] for k in ("experiment_id", "id", "role", "status", "reason", "run_id")}
                    for r in Registry(args.root).rows()
                ]
            )
        )
    elif name == "report":
        print(dumps(generate_report(args.root)))
    else:
        report = comparison(args.root)
        print(
            dumps(
                {
                    "candidates": report["rejected_or_failed"],
                    "trials": [
                        t for t in report["trial_history"] if t["disposition"] != "COMPLETE"
                    ],
                }
                if name == "rejected"
                else report
            )
        )
    return 0
