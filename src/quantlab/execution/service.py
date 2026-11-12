"""Explicitly armed, bounded sandbox test service; monitoring is the default."""

import json
import os
import signal
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from quantlab.discovery.common import code_version, fingerprint
from quantlab.execution.authority import Authority, ExecutionDenied
from quantlab.execution.broker import AlpacaPaperBroker
from quantlab.execution.controller import SandboxController
from quantlab.paper.feeds import AlpacaQuotes, FeedUnavailable
from quantlab.paper.orders import PaperOrder
from quantlab.paper.risk import PaperLimits


def configuration(path):
    path = Path(path).resolve()
    doc = yaml.safe_load(path.read_text())
    allowed = {
        "mode",
        "broker",
        "account_id",
        "database",
        "symbols",
        "risk",
        "strategy",
        "approval_file",
        "poll_seconds",
        "cancel_open_on_shutdown",
    }
    if (
        not isinstance(doc, dict)
        or set(doc) - allowed
        or doc.get("mode") != "BROKER_SANDBOX"
        or doc.get("broker") != "alpaca_paper"
    ):
        raise ExecutionDenied(
            "Strict Alpaca PAPER BROKER_SANDBOX configuration required; no LIVE fallback"
        )
    strategy = doc["strategy"]
    if (
        set(strategy) - {"id", "type", "version", "symbol", "target_units", "max_submissions"}
        or strategy["type"] != "fixed_target_sandbox_test"
    ):
        raise ExecutionDenied(
            "Only explicitly reviewed fixed-target sandbox engineering strategy supported"
        )
    if (
        strategy["symbol"] not in doc["symbols"]
        or type(strategy["target_units"]) is not int
        or not 1 <= strategy["target_units"] <= 10
    ):
        raise ValueError("Bound sandbox target to 1–10 shares of an allowed equity")
    if strategy.get("max_submissions") != 1 or not 1 <= doc.get("poll_seconds", 5) <= 30:
        raise ValueError("One submission and bounded polling required by sandbox test service")
    for key in ("database", "approval_file"):
        doc[key] = str((path.parent / doc[key]).resolve())
    PaperLimits(**doc.get("risk", {}))
    return doc


def authority_for(doc):
    key = os.getenv("QUANTLAB_SANDBOX_AUTHORIZATION_KEY")
    if not key:
        raise ExecutionDenied("Private sandbox authorization key unavailable")
    return Authority(key.encode(), mode=doc["mode"], account_id=doc["account_id"])


def approval_document(doc, authority, *, actor, reason, minutes=15, now=None):
    if not actor or not reason or type(minutes) is not int or not 1 <= minutes <= 60:
        raise ValueError("Explicit operator identity/reason and 1–60 minute expiry required")
    now = now or datetime.now(UTC)
    strategy = doc["strategy"]
    limits = PaperLimits(**doc.get("risk", {}))
    return authority.sign(
        {
            "mode": doc["mode"],
            "account_id": doc["account_id"],
            "kind": "SANDBOX_TEST",
            "strategy_id": strategy["id"],
            "strategy_version": strategy["version"],
            "strategy_definition_hash": fingerprint(strategy),
            "source_sha256": code_version()["source_sha256"],
            "risk_hash": fingerprint(limits.__dict__),
            "symbols": doc["symbols"],
            "actor": actor,
            "reason": reason,
            "origin": "human",
            "model_hash": None,
            "expires_at": (now + timedelta(minutes=minutes)).isoformat(),
        }
    )


def run_service(path, *, arm=False, resume=False, resume_reason=None, max_cycles=None):
    if resume and (not arm or not resume_reason):
        raise ExecutionDenied("Sandbox resume requires explicit arm flag and operator reason")
    doc = configuration(path)
    authority = authority_for(doc)
    broker = AlpacaPaperBroker(authority)
    strategy = doc["strategy"]
    root = Path(doc["database"]).parent
    root.mkdir(parents=True, exist_ok=True)
    feed = AlpacaQuotes(doc["symbols"], feed="iex")
    controller = SandboxController(
        doc["database"],
        broker,
        authority,
        symbols=doc["symbols"],
        limits=PaperLimits(**doc.get("risk", {})),
        strategy_definitions={strategy["id"]: strategy},
    )
    existing = controller.state["initialized"]
    stop = False
    execution_started = False

    def shutdown(signum, frame):
        nonlocal stop
        stop = True

    old = {s: signal.signal(s, shutdown) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        now = datetime.now(UTC)
        if not existing:
            controller.bootstrap(now=now)
        signed = json.loads(Path(doc["approval_file"]).read_text())
        controller.approve(signed, now=now)
        cycles = failures = 0
        while not stop and (max_cycles is None or cycles < max_cycles):
            now = datetime.now(UTC)
            for identity, payload in controller.store.db.execute(
                "SELECT id,payload FROM controls WHERE applied=0 ORDER BY id"
            ).fetchall():
                control = json.loads(payload)
                if control["action"] == "kill":
                    controller.kill(
                        now=now,
                        reason=control["reason"],
                        cancel_open=control.get("cancel_open", False),
                    )
                elif control["action"] == "pause":
                    controller.pause_strategy(control["strategy"], reason=control["reason"])
                else:
                    raise ExecutionDenied("Unsupported sandbox control")
                with controller.store.db:
                    controller.store.db.execute(
                        "UPDATE controls SET applied=1 WHERE id=?", (identity,)
                    )
            try:
                for event in feed.poll():
                    controller.receive(event, now=datetime.now(UTC))
                result = controller.reconcile(now=datetime.now(UTC))
                if not result["okay"]:
                    raise FeedUnavailable("Broker reconciliation unsafe; execution suspended")
                # Restart never arms without a separate explicit operator resume action.
                if arm and (not existing or resume) and cycles == 0 and result["okay"]:
                    if existing and controller.state["killed"]:
                        reset = authority.sign(
                            {
                                "mode": doc["mode"],
                                "account_id": doc["account_id"],
                                "operation": "kill_reset",
                                "actor": signed["body"]["actor"],
                                "expires_at": (
                                    datetime.now(UTC) + timedelta(minutes=1)
                                ).isoformat(),
                            }
                        )
                        controller.reset_kill(reset, now=datetime.now(UTC), reason=resume_reason)
                    controller.arm(
                        strategy["id"],
                        now=datetime.now(UTC),
                        reason="Explicit CLI sandbox-only arming with signed operator approval",
                    )
                    execution_started = True
                state = controller.state["strategies"][strategy["id"]]
                # One durable signal ID; uncertain/partial/restarted intents are never resubmitted.
                signal_id = "fixed-sandbox-test:" + fingerprint(strategy)
                if (
                    state["execution"] == "RUNNING"
                    and not controller.state["killed"]
                    and signal_id not in controller.orders
                ):
                    now = datetime.now(UTC)
                    controller.submit(
                        PaperOrder(
                            signal_id,
                            strategy["id"],
                            strategy["symbol"],
                            strategy["target_units"],
                            now.isoformat(),
                        ),
                        now=now,
                    )
                failures = 0
            except (FeedUnavailable, ValueError, ExecutionDenied) as exc:
                failures += 1
                controller.pause_strategy(
                    strategy["id"], reason="feed_or_strategy_failure:" + type(exc).__name__
                )
                if failures >= 5:
                    raise FeedUnavailable("Sandbox service failure budget exhausted") from exc
            report = controller.report()
            report["monitoring_only"] = not execution_started
            (root / "service-report.json").write_text(json.dumps(report, indent=2) + "\n")
            cycles += 1
            for _ in range(int(doc.get("poll_seconds", 5) * 10)):
                if stop:
                    break
                time.sleep(0.1)
    finally:
        controller.kill(
            now=datetime.now(UTC),
            reason="safe_service_shutdown",
            cancel_open=doc.get("cancel_open_on_shutdown", False) and execution_started,
        )
        (root / "service-report.json").write_text(json.dumps(controller.report(), indent=2) + "\n")
        controller.close()
        broker.close()
        feed.close()
        for sig, handler in old.items():
            signal.signal(sig, handler)
