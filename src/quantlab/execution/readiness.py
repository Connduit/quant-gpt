"""Evidence-based operator checklist; it cannot activate LIVE execution."""

import json
import sqlite3
from pathlib import Path

from quantlab.execution.authority import LIVE_ENABLED


def readiness(workspace):
    workspace = Path(workspace)

    def document(relative):
        path = workspace / relative
        return json.loads(path.read_text()) if path.is_file() else {}

    validation = document("docs/milestone-5-results.json")
    futures = document("docs/milestone-7-results.json")
    paper = document("docs/milestone-8-results.json")
    execution = document("docs/milestone-11-execution.json")
    verification = document("docs/milestone-11-tests.json")
    states = []
    for path in (
        workspace / "data/network-verification/holdout-vault.sqlite",
        workspace / "data/futures/holdout-vault.sqlite",
    ):
        if path.is_file():
            try:
                with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                    states.extend(row[0] for row in db.execute("SELECT state FROM holdouts"))
            except sqlite3.Error:
                states.append("UNREADABLE")
    holdout = "SEALED" if states and all(s == "SEALED" for s in states) else "UNKNOWN_OR_CHANGED"
    checks = [
        (
            "research_validation",
            "BLOCKED",
            (
                "No independently validated strategy is available; real investigations remain "
                "rejected."
            ),
        ),
        (
            "final_holdout",
            "BLOCKED",
            f"Ledger state {holdout}; no future authorization, evaluation or released result.",
        ),
        (
            "historical_data_quality",
            "BLOCKED",
            (
                "Equity actions/universe and futures historical margins/calendar coverage are "
                "incomplete."
            ),
        ),
        (
            "paper_performance",
            "BLOCKED",
            "Only historical experimental replay; no approved real-time paper operating history.",
        ),
        (
            "external_broker_sandbox",
            "VERIFIED" if execution.get("external_broker_verified") else "UNVERIFIED",
            "Mock tests are not external broker connectivity or routing verification.",
        ),
        (
            "risk_and_order_management",
            "ENGINEERING_TESTED" if verification.get("python_passed") else "UNVERIFIED",
            (
                "Per-order limits, idempotency, uncertainty and kill behavior require independent "
                "operational review."
            ),
        ),
        (
            "account_reconciliation",
            "MOCK_TESTED" if execution.get("restart_reconciled") else "UNVERIFIED",
            "Real broker balances, fees and activity coverage remain unverified.",
        ),
        (
            "crash_backup_recovery",
            "ENGINEERING_TESTED" if execution.get("backup_restore_verified") else "UNVERIFIED",
            "External positions must be reconciled before any restart is armed.",
        ),
        (
            "independent_review",
            "PENDING",
            "No human statistical/operational independent review recorded.",
        ),
        (
            "strategy_model_eligibility",
            "BLOCKED",
            "Zero research/paper/live-qualified strategies; sandbox test approval is separate.",
        ),
        (
            "capital_and_sizing",
            "PENDING",
            "No real-money capital allocation authorized; example limits are not optimal settings.",
        ),
        (
            "security_and_deployment",
            "REVIEW_REQUIRED",
            (
                "Credential isolation, TLS/host hardening, token rotation and deployment artifacts "
                "need operator review."
            ),
        ),
        (
            "monitoring",
            "ENGINEERING_TESTED" if verification.get("python_passed") else "UNVERIFIED",
            (
                "Mock alerts/model hooks tested; live degradation thresholds are not empirically "
                "verified."
            ),
        ),
        (
            "regulatory_tax_operator_readiness",
            "PENDING",
            "Operator must independently review applicable obligations and incident procedures.",
        ),
        (
            "separate_live_authorization",
            "BLOCKED",
            "No activation authorization; this build has no enabled LIVE broker path.",
        ),
    ]
    return {
        "live_enabled": LIVE_ENABLED,
        "status": "NOT_READY_FOR_LIVE",
        "eligible_strategy_ids": [],
        "holdout_state": holdout,
        "checks": [
            {"id": key, "status": status, "evidence": evidence} for key, status, evidence in checks
        ],
        "external_broker_verified": bool(execution.get("external_broker_verified")),
        "research_artifacts_available": bool(validation and futures),
        "replay_only": bool(paper),
        "limits": [
            "A completed checklist is not a profitability guarantee.",
            (
                "No checklist, API token, AI output or environment variable can enable LIVE in "
                "this build."
            ),
            "Final holdout access requires a separate future authorization; none occurred.",
        ],
    }
