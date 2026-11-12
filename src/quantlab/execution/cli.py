"""Execution inspection/readiness and explicit mock or PAPER sandbox operation."""

import json
import sqlite3

from quantlab.backtesting.report import dumps
from quantlab.execution.backup import backup, restore
from quantlab.execution.readiness import readiness
from quantlab.paper.store import PaperStore


def execute(args):
    if args.execution_command == "sandbox-demo":
        from quantlab.execution.demo import demonstrate

        result = demonstrate(args.output)
        print(
            dumps(
                {
                    "output": str(args.output),
                    "mode": result["execution_mode"],
                    "broker": result["broker"],
                    "external_broker_verified": result["external_broker_verified"],
                    "live_enabled": False,
                    "restart_reconciled": result["restart_reconciled"],
                    "backup_restore_verified": result["backup_restore_verified"],
                }
            )
        )
        return 0
    if args.execution_command == "readiness":
        result = readiness(args.workspace)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(dumps(result) + "\n")
        print(dumps(result))
        return 0
    if args.execution_command in ("backup", "restore"):
        result = (backup if args.execution_command == "backup" else restore)(
            args.database, args.output
        )
        print(dumps(result))
        return 0
    if args.execution_command in ("kill", "pause"):
        control = {"action": args.execution_command, "reason": args.reason}
        if args.execution_command == "kill":
            control["cancel_open"] = args.cancel_open
        else:
            control["strategy"] = args.strategy
        PaperStore.queue(args.database, control)
        print(
            dumps(
                {
                    "queued": True,
                    "applied": False,
                    "execution": "BROKER_SANDBOX",
                    "live_enabled": False,
                }
            )
        )
        return 0
    if args.execution_command == "inspect":
        with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            state = json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])
        print(
            dumps({"state": state, "cached_not_current_broker_state": True, "live_enabled": False})
        )
        return 0
    from quantlab.execution.service import (
        approval_document,
        authority_for,
        configuration,
        run_service,
    )

    if args.execution_command == "approve-sandbox-test":
        doc = configuration(args.execution_config)
        authority = authority_for(doc)
        result = approval_document(
            doc, authority, actor=args.actor, reason=args.reason, minutes=args.minutes
        )
        if args.output.exists():
            raise ValueError("Approval destination exists; preserve audit history")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(dumps(result) + "\n")
        args.output.chmod(0o600)
        print(dumps({"sandbox_approval_written": str(args.output), "live_enabled": False}))
        return 0
    run_service(
        args.execution_config,
        arm=args.arm_approved_sandbox_test,
        resume=args.resume_reconciled_sandbox_test,
        resume_reason=args.resume_reason,
    )
    return 0
