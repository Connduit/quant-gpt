import json
from pathlib import Path

from quantlab.discovery.common import write_json
from quantlab.discovery.registry import Registry


def comparison(root: Path, parent_ids=None):
    registry = Registry(root)
    rows = []
    latest = {}
    for row in registry.rows():
        if row["role"] == "trial" or parent_ids is not None:
            latest[row["experiment_id"]] = row
    for row in latest.values():
        result = json.loads(row["result"]) if row["result"] else None
        summary = result["summary"] if result else {}
        rows.append(
            {
                "experiment_id": row["experiment_id"],
                "attempt_id": row["id"],
                "role": row["role"],
                "parent_id": row["parent_id"],
                "status": row["status"],
                "reason": row["reason"],
                "eligible": row["status"] == "COMPLETE" and summary.get("eligible", False),
                "score": summary.get("score"),
                "summary": summary,
                "artifact_path": row["artifact_path"],
                "mlflow_run_id": row["run_id"],
                "hypothesis": row["hypothesis"],
                "configuration": json.loads(row["definition"]),
                "selected_features": result["selected_features"] if result else [],
                "validation_windows": result["windows"] if result else [],
                "action_coverage": result.get("action_coverage", {}) if result else {},
            }
        )
    rows.sort(
        key=lambda r: (
            not r["eligible"],
            -r["score"] if r["score"] is not None else float("inf"),
            r["experiment_id"],
        )
    )
    return {
        "counts": registry.counts(),
        "eligible": [r for r in rows if r["eligible"]],
        "rejected_or_failed": [r for r in rows if not r["eligible"]],
        "evaluation_role": "search_validation",
        "final_holdout": "not_evaluated",
        "trial_history": registry.links(),
        "warnings": [
            "Ranking thresholds and weights are user heuristics, not scientific evidence.",
            "Multiple testing, selection bias and validation reuse can yield false discoveries.",
            "Zero eligible strategies is valid; do not auto-promote Optuna best_trial.",
        ],
    }


def generate_report(root: Path):
    report = comparison(root)
    directory = root / "reports"
    directory.mkdir(exist_ok=True)
    write_json(directory / "ranking.json", report)
    lines = [
        "# Discovery search-validation report",
        "",
        "These are searched validation results, not independent final holdout results.",
        "",
        f"Unique hypotheses: {report['counts']['unique_hypotheses']}; "
        f"attempts: {report['counts']['attempts']}; "
        f"Optuna trials: {report['counts']['optuna_trials']}.",
        "",
        "| Experiment | Status | Eligible | Score | Explanation |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in (*report["eligible"], *report["rejected_or_failed"]):
        lines.append(
            f"| {row['experiment_id'][:16]} | {row['status']} | {row['eligible']} | "
            f"{row['score']} | {row['reason'] or ''} |"
        )
    lines += ["", "Final holdout: not evaluated.", "", *report["warnings"]]
    (directory / "ranking.md").write_text("\n".join(lines) + "\n")
    return report
