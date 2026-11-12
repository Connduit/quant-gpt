from datetime import timedelta

import pytest
from conftest import T, fixture_approval, quote

from quantlab.execution.authority import Authority, ExecutionDenied
from quantlab.execution.controller import SandboxController
from quantlab.paper.orders import PaperOrder


def order(identity="signal", quantity=10, at=T, **kwargs):
    return PaperOrder(identity, "test", "SPY", quantity, at.isoformat(), **kwargs)


def test_all_modes_are_explicit_and_live_cannot_be_enabled(monkeypatch):
    monkeypatch.setenv("QUANTLAB_LIVE_ENABLED", "true")
    for mode in ("LIVE", "PAPER", "BACKTEST"):
        with pytest.raises(ExecutionDenied):
            Authority(b"x" * 32, mode=mode, account_id="account")


def test_signed_capability_is_bound_to_account_operation_payload_and_time(controller):
    a = controller.authority
    payload = {"symbol": "SPY", "qty": "1"}
    permit = a.permit("submit", payload, now=T)
    a.require(permit, "submit", payload, now=T)
    for operation, body in [("cancel", payload), ("submit", {"symbol": "AAPL", "qty": "1"})]:
        with pytest.raises(ExecutionDenied):
            a.require(permit, operation, body, now=T)
    with pytest.raises(ExecutionDenied):
        a.require(permit, "submit", payload, now=T + timedelta(minutes=1))


def test_partial_fills_duplicates_cash_positions_and_reconciliation(controller):
    c = controller
    o = c.submit(order(), now=T)
    client = next(iter(c.broker.orders))
    c.broker.publish_fill(client, 3, "100.03", now=T + timedelta(seconds=1))
    assert c.reconcile(now=T + timedelta(seconds=1))["okay"]
    assert c.orders[o.client_id].state == "PARTIALLY_FILLED"
    expected = c.account.view()
    c.broker.duplicate_callbacks = True
    assert c.reconcile(now=T + timedelta(seconds=2))["okay"]
    assert c.account.view() == expected and len(c.account.fills) == 1
    c.broker.publish_fill(client, 7, "100.03", now=T + timedelta(seconds=3))
    assert c.reconcile(now=T + timedelta(seconds=3))["okay"]
    assert c.orders[o.client_id].state == "FILLED" and c.account.quantity("SPY") == 10
    assert float(c.account.view()["cash"]) == pytest.approx(100000 - 1000.3 - 0.05)
    assert c.broker.submit_calls == 1
    c.submit(order(), now=T + timedelta(seconds=4))
    assert c.broker.submit_calls == 1


def test_uncertain_acceptance_never_retries_and_recovers_by_stable_client_id(controller):
    c = controller
    c.broker.timeout_after_accept = True
    o = c.submit(order(), now=T)
    assert o.state == "PENDING" and not c.state["reconciled"]
    c.submit(order(), now=T)
    assert c.broker.submit_calls == 1
    assert c.reconcile(now=T + timedelta(seconds=1))["okay"]
    assert c.orders["signal"].state == "ACCEPTED" and not c.state["uncertain"]
    assert c.state["strategies"]["test"]["execution"] == "PAUSED"


def test_malformed_ack_is_uncertain_and_does_not_release_reservations(controller):
    c = controller
    c.broker.malformed_ack = True
    assert c.submit(order(), now=T).state == "PENDING"
    assert c.state["uncertain"] and not c.state["connected"]
    assert c.submit(order("second"), now=T).state == "REJECTED"
    assert c.broker.submit_calls == 1


def test_risk_rejects_oversize_short_stale_and_expired_approval(controller):
    c = controller
    assert c.submit(order("big", 10000), now=T).state == "REJECTED"
    assert c.submit(order("short", -1), now=T).state == "REJECTED"
    assert (
        c.submit(order("stale", 1, at=T + timedelta(minutes=3)), now=T + timedelta(minutes=3)).state
        == "REJECTED"
    )
    with pytest.raises(ExecutionDenied):
        c.submit(order("expired", at=T + timedelta(days=2)), now=T + timedelta(days=2))
    assert c.broker.submit_calls == 0


def test_cancel_replace_and_kill_are_distinct_from_liquidation(controller):
    c = controller
    c.submit(order(order_type="limit", limit="99"), now=T)
    replacement = order("replacement", 2, order_type="limit", limit="98")
    c.replace("signal", replacement, now=T)
    assert c.orders["signal"].state == "CANCELLED" and c.orders["replacement"].state == "ACCEPTED"
    result = c.kill(now=T, reason="operator test", cancel_open=True)
    assert not result["positions_liquidated"] and c.state["killed"]
    assert c.reconcile(now=T)["okay"]
    assert c.orders["replacement"].state == "CANCELLED"
    assert c.submit(order("blocked"), now=T).state == "REJECTED"


def test_restart_requires_external_reconciliation_and_new_data(controller):
    c = controller
    c.submit(order(), now=T)
    path = c.store.path
    c.close()
    recovered = SandboxController(path, c.broker, c.authority, symbols=["SPY"])
    try:
        assert not recovered.state["connected"]
        with pytest.raises(ExecutionDenied):
            recovered.arm("test", now=T, reason="premature")
        assert recovered.reconcile(now=T + timedelta(seconds=1))["okay"]
        with pytest.raises(ExecutionDenied):
            recovered.arm("test", now=T + timedelta(seconds=1), reason="no new data")
        recovered.receive(quote(2), now=T + timedelta(seconds=2))
        recovered.arm("test", now=T + timedelta(seconds=2), reason="reconciled and fresh")
        assert c.broker.submit_calls == 1
    finally:
        recovered.close()


def test_unknown_balances_fills_and_connection_failure_suspend(controller):
    c = controller
    c.broker.cash_discrepancy = 5
    assert not c.reconcile(now=T)["okay"]
    assert c.state["strategies"]["test"]["execution"] == "PAUSED"
    c.broker.cash_discrepancy = 0
    c.broker.connected = False
    assert c.reconcile(now=T)["errors"] == ["broker_read_failure"]
    assert not c.state["connected"]


def test_fixture_approval_cannot_authorize_external_broker(controller):
    c = controller
    c.broker.kind = "alpaca_paper"
    with pytest.raises(ExecutionDenied):
        c.approve(fixture_approval(c), now=T)
    c.broker.kind = "mock"


def test_model_drift_pauses_and_rollback_requires_separate_review(controller):
    c = controller
    c.approve(
        fixture_approval(c, model_hash="old-model", baseline={"return": {"mean": 0, "std": 1}}),
        now=T,
    )
    c.arm("test", now=T, reason="test model monitoring")
    c.model_observation("test", {"return": 10}, 0.1, 2, model_hash="old-model", now=T)
    assert c.state["strategies"]["test"]["execution"] == "PAUSED"
    body = {
        "mode": "BROKER_SANDBOX",
        "account_id": c.authority.account_id,
        "expires_at": (T + timedelta(days=1)).isoformat(),
        "operation": "model_rollback",
        "strategy_id": "test",
        "model_hash": "reviewed-model",
        "actor": "test-reviewer",
        "reason": "known approved rollback",
    }
    c.rollback_model("test", "reviewed-model", c.authority.sign(body), now=T)
    assert c.state["approval"] is None
    with pytest.raises(ExecutionDenied):
        c.arm("test", now=T, reason="must not restart automatically")


def test_futures_contract_cannot_be_misrouted_to_stock_broker(tmp_path, controller):
    with pytest.raises(ExecutionDenied, match="Futures brokerage adapter unavailable"):
        SandboxController(
            tmp_path / "wrong.sqlite", controller.broker, controller.authority, symbols=["ESZ13"]
        )
