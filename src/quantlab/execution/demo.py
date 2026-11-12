"""Full mock broker pipeline when external sandbox credentials/network are absent."""

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantlab.backtesting.report import dumps
from quantlab.discovery.common import fingerprint
from quantlab.execution.authority import Authority
from quantlab.execution.backup import backup, restore
from quantlab.execution.controller import SandboxController
from quantlab.execution.mock import MockBroker
from quantlab.paper.events import MarketEvent
from quantlab.paper.orders import PaperOrder


def demonstrate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    # Entirely synthetic broker observations: this tests engineering, not profitability.
    start = datetime(2024, 6, 3, 13, 30, tzinfo=UTC)
    secret = secrets.token_bytes(32)
    key_path = output / "mock-authorization.key"
    key_path.write_bytes(secret)
    key_path.chmod(0o600)
    authority = Authority(secret, mode="BROKER_SANDBOX", account_id="explicit-mock-paper-account")
    broker = MockBroker(authority, output / "mock-broker.json")
    database = output / "oms.sqlite"
    controller = SandboxController(database, broker, authority, symbols=["SPY"])
    controller.bootstrap(now=start)
    approval = authority.sign(
        {
            "mode": "BROKER_SANDBOX",
            "account_id": authority.account_id,
            "kind": "SANDBOX_TEST",
            "strategy_id": "test",
            "strategy_version": "test-only-v1",
            "strategy_definition_hash": fingerprint(controller.definitions["test"]),
            "source_sha256": controller.configuration["source_sha256"],
            "risk_hash": fingerprint(controller.limits.__dict__),
            "symbols": ["SPY"],
            "actor": "simulated_test_operator",
            "reason": "User-requested mock pipeline engineering demonstration",
            "origin": "simulated_fixture",
            "model_hash": None,
            "expires_at": (start + timedelta(hours=1)).isoformat(),
        }
    )
    controller.approve(approval, now=start)

    def observation(second, price):
        t = start + timedelta(seconds=second)
        bid, ask = price, price + 0.02
        broker.mark("SPY", str((bid + ask) / 2))
        event = MarketEvent(
            "SPY",
            "explicit_mock",
            t,
            t,
            "quote",
            "replay",
            str(second),
            str(bid),
            str(ask),
            1000,
            1000,
        )
        controller.receive(event, now=t)
        return t

    t = observation(0, 100)
    assert controller.reconcile(now=t)["okay"]
    controller.arm(
        "test", now=t, reason="Explicit simulated test operator; not real paper eligibility"
    )
    broker.timeout_after_accept = True
    controller.submit(PaperOrder("entry", "test", "SPY", 10, t.isoformat()), now=t)
    assert controller.state["uncertain"]
    controller.submit(PaperOrder("entry", "test", "SPY", 10, t.isoformat()), now=t)
    assert broker.submit_calls == 1
    t = observation(1, 100)
    assert controller.reconcile(now=t)["okay"]
    controller.arm("test", now=t, reason="Accepted order recovered by client ID; no resubmission")
    client = next(iter(broker.orders))
    broker.publish_fill(client, 4, "100.03", now=start + timedelta(seconds=2))
    t = observation(2, 100)
    assert controller.reconcile(now=t)["okay"]
    broker.duplicate_callbacks = True
    assert controller.reconcile(now=t)["okay"]
    assert len(controller.account.fills) == 1
    controller.close()
    broker.close()
    # Reconstruct both independent durable stores; never re-fund or resubmit.
    broker = MockBroker(authority, output / "mock-broker.json")
    controller = SandboxController(database, broker, authority, symbols=["SPY"])
    assert not controller.state["reconciled"]
    t = observation(3, 100)
    assert controller.reconcile(now=t)["okay"]
    restart_ok = controller.account.quantity("SPY") == 4 and controller.orders["entry"].filled == 4
    controller.arm(
        "test", now=t, reason="Operator reviewed fresh data and broker reconciliation after restart"
    )
    broker.publish_fill(client, 6, "100.03", now=start + timedelta(seconds=4))
    t = observation(4, 100)
    assert controller.reconcile(now=t)["okay"]
    broker.connected = False
    assert not controller.reconcile(now=start + timedelta(seconds=5))["okay"]
    broker.connected = True
    t = observation(6, 100)
    assert controller.reconcile(now=t)["okay"]
    controller.arm("test", now=t, reason="Explicit operator recovery after simulated outage")
    controller.submit(PaperOrder("exit", "test", "SPY", -10, t.isoformat()), now=t)
    exit_client = [k for k in broker.orders if k != client][0]
    broker.publish_fill(exit_client, 10, "100.00", now=start + timedelta(seconds=7))
    t = observation(7, 100)
    assert controller.reconcile(now=t)["okay"]
    controller.submit(
        PaperOrder(
            "pending-limit", "test", "SPY", 1, t.isoformat(), order_type="limit", limit="99"
        ),
        now=t,
    )
    kill = controller.kill(
        now=t,
        reason="Verify new-order block and explicit open-order cancellation",
        cancel_open=True,
    )
    assert controller.reconcile(now=t)["okay"]
    blocked = controller.submit(PaperOrder("after-kill", "test", "SPY", 1, t.isoformat()), now=t)
    assert blocked.state == "REJECTED"
    snapshot = controller.account.view()
    backup_path = output / "backup.sqlite"
    backup(database, backup_path)
    restored = output / "restored.sqlite"
    restore(backup_path, restored)
    restored_controller = SandboxController(restored, broker, authority, symbols=["SPY"])
    backup_ok = (
        restored_controller.account.view() == snapshot
        and not restored_controller.state["reconciled"]
    )
    restored_controller.close()
    result = controller.report() | {
        "mock_demonstration": True,
        "real_market_observations": False,
        "restart_reconciled": restart_ok,
        "backup_restore_verified": backup_ok,
        "uncertain_order_recovered_without_resubmit": True,
        "duplicate_fill_ignored": True,
        "outage_recovery_verified": True,
        "kill_result": kill,
        "final_holdout_accessed": False,
        "no_profitability_evidence": True,
        "source_sha256": controller.configuration["source_sha256"],
        "limitations": [
            "Mock broker and synthetic quotes; external Alpaca paper routing remains unverified.",
            "No research/paper-qualified strategy exists.",
            "LIVE is disabled; no real-money orders were sent.",
        ],
    }
    (output / "execution-report.json").write_text(dumps(result) + "\n")
    controller.close()
    broker.close()
    return result
