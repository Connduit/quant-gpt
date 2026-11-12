import json
import sqlite3
from datetime import timedelta

import pytest
from conftest import T, quote

from quantlab.paper.orders import PaperOrder
from quantlab.paper.runtime import PaperRuntime


def order(identity="o", quantity=5, **kwargs):
    return PaperOrder(
        identity, "s", kwargs.pop("instrument", "SPY"), quantity, T.isoformat(), **kwargs
    )


def test_order_states_invalid_terminal():
    o = order()
    o.transition("PENDING")
    o.transition("ACCEPTED")
    o.transition("FILLED")
    with pytest.raises(ValueError):
        o.transition("CANCELLED")


def test_later_quote_partial_shared_liquidity_and_fees(runtime):
    runtime.submit(order(quantity=15), now=T)
    runtime.submit(order("second", 5), now=T)
    runtime.ingest(quote(0, sequence="sameclock"), now=T)
    assert runtime.account.fills == []
    e = quote(1)
    runtime.ingest(e, now=e.received_at)
    assert runtime.orders["o"].state == "PARTIALLY_FILLED"
    assert runtime.orders["o"].filled == 10
    assert runtime.orders["second"].filled == 0
    e = quote(2)
    runtime.ingest(e, now=e.received_at)
    assert runtime.orders["o"].state == "FILLED"
    assert runtime.orders["second"].state == "FILLED"
    v = runtime.account.view()
    assert float(v["cash"]) == pytest.approx(100000 - 20 * 100.03 - 0.1)
    assert float(v["equity"]) == pytest.approx(100000 - 20 * 0.02 - 0.1)


@pytest.mark.parametrize(
    "kind,limit,stop",
    [
        ("market", None, None),
        ("limit", "100.03", None),
        ("stop", None, "100.02"),
        ("stop_limit", "100.03", "100.02"),
    ],
)
def test_order_types(runtime, kind, limit, stop):
    runtime.submit(order(order_type=kind, limit=limit, stop=stop), now=T)
    e = quote(1)
    runtime.ingest(e, now=e.received_at)
    if stop:
        assert not runtime.account.fills
        e = quote(2)
        runtime.ingest(e, now=e.received_at)
    assert runtime.orders["o"].state == "FILLED"
    assert float(runtime.account.fills[0]["price"]) == 100.03


def test_limit_not_guaranteed_at_touch_and_stop_gap(runtime):
    runtime.submit(order(order_type="limit", limit="100.02"), now=T)
    e = quote(1)
    runtime.ingest(e, now=e.received_at)
    assert not runtime.account.fills
    runtime.cancel("o")
    runtime.submit(
        PaperOrder("stop", "s", "SPY", 1, e.event_at.isoformat(), order_type="stop", stop="101"),
        now=e.received_at,
    )
    e = quote(2, bid="101", ask="101.02")
    runtime.ingest(e, now=e.received_at)
    e = quote(3, bid="110", ask="110.02")
    runtime.ingest(e, now=e.received_at)
    assert runtime.account.fills[-1]["price"] == "110.03"


def test_idempotency_collision_and_replacement(runtime):
    runtime.submit(order(), now=T)
    assert runtime.submit(order(), now=T).state == "ACCEPTED"
    with pytest.raises(ValueError):
        runtime.submit(order(quantity=6), now=T)
    runtime.replace("o", order("replacement", 2), now=T)
    assert runtime.orders["o"].state == "CANCELLED"
    assert runtime.orders["replacement"].state == "ACCEPTED"


def test_recovery_duplicate_event_no_double_fill(runtime):
    runtime.submit(order(), now=T)
    e = quote(1)
    runtime.ingest(e, now=e.received_at)
    config = runtime.configuration
    path = runtime.store.path
    expected = runtime.account.view()
    runtime.close()
    recovered = PaperRuntime(path, contracts=runtime.contracts, symbols=["SPY"])
    assert recovered.account.view() == expected
    assert not recovered.state["connected"]
    assert recovered.ingest(e, now=e.received_at) is False
    recovered.close()
    # Keep fixture teardown valid.
    runtime.store = type("Closed", (), {"close": lambda self: None})()
    assert config["mode"] == "replay"


def test_risk_reserves_pending_and_blocks_shorts(runtime):
    big = order("big", 100000)
    assert runtime.submit(big, now=T).state == "REJECTED"
    assert "order_units" in big.reason
    assert runtime.submit(order("short", -1), now=T).state == "REJECTED"


def test_stale_out_of_order_gap_and_kill(runtime):
    runtime.submit(order(), now=T)
    e = quote(5)
    runtime.ingest(e, now=e.received_at)
    old = quote(2)
    runtime.ingest(old, now=e.received_at)
    assert runtime.state["alerts"][-1]["code"] == "out_of_order"
    e = quote(1300)
    runtime.ingest(e, now=e.received_at)
    assert not runtime.state["connected"]
    runtime.control("kill", reason="operator emergency")
    assert runtime.state["killed"]
    assert runtime.account.quantity("SPY") == 5  # no automatic liquidation
    assert (
        runtime.submit(
            PaperOrder("blocked", "s", "SPY", 1, e.received_at.isoformat()), now=e.received_at
        ).state
        == "REJECTED"
    )


def test_sequence_collision_and_future_timestamp(runtime):
    e = quote(0, bid="101", ask="101.02")
    runtime.ingest(e, now=T)
    assert not runtime.state["connected"]
    with pytest.raises(ValueError):
        runtime.ingest(quote(5), now=T)


def test_futures_master_capital_multiplier_and_short(runtime):
    e = quote(1, symbol="MESM24", bid="5000", ask="5000.25")
    runtime.ingest(e, now=e.received_at)
    o = PaperOrder("future", "s", "MESM24", -1, e.event_at.isoformat())
    assert runtime.submit(o, now=e.received_at).state == "ACCEPTED"
    e = quote(2, symbol="MESM24", bid="5000", ask="5000.25")
    runtime.ingest(e, now=e.received_at)
    v = runtime.account.view()
    assert v["positions"]["MESM24"] == -1
    assert float(v["initial_capital"]) == 100000
    assert float(v["cash"]) == pytest.approx(100000 - 3.52)
    e = quote(3, symbol="MESM24", bid="4990", ask="4990.25")
    runtime.ingest(e, now=e.received_at)
    assert float(runtime.account.view()["equity"]) == pytest.approx(100000 + 48.125 - 3.52)


def test_eligibility_and_mode_restrictions(tmp_path):
    r = PaperRuntime(tmp_path / "a.sqlite", symbols=["SPY"])
    with pytest.raises(ValueError):
        r.register("bad", capital=1000, validation_status="REJECTED", approved=True)
    r.close()
    with pytest.raises(ValueError):
        PaperRuntime(tmp_path / "b.sqlite", mode="live")
    r = PaperRuntime(tmp_path / "c.sqlite", mode="realtime", symbols=["SPY"])
    with pytest.raises(ValueError):
        r.register("bad", capital=1000, experimental=True)
    r.close()


def test_atomic_rollback_and_tamper_detection(runtime):
    before = runtime.account.view()

    def fail():
        runtime.account.fill("SPY", 1, "100", "0", T, "broken", "s")
        raise RuntimeError("simulated crash before commit")

    with pytest.raises(RuntimeError):
        runtime._transaction("fail", "test", {}, fail)
    assert runtime.account.view() == before
    assert not runtime.store.contains("fail")
    path = runtime.store.path
    runtime.close()
    runtime.store = type("Closed", (), {"close": lambda self: None})()
    with sqlite3.connect(path) as db:
        state = json.loads(db.execute("SELECT payload FROM state").fetchone()[0])
        state["killed"] = True
        db.execute("UPDATE state SET payload=?", (json.dumps(state),))
    with pytest.raises(ValueError, match="reconcile"):
        PaperRuntime(path, contracts=runtime.contracts, symbols=["SPY"])


def test_strategy_reducing_order_does_not_double_count_exposure(runtime):
    e = quote(1, symbol="MESM24", bid="18000", ask="18000.25")
    runtime.ingest(e, now=e.received_at)
    runtime.submit(PaperOrder("entry", "s", "MESM24", 1, e.event_at.isoformat()), now=e.received_at)
    e = quote(2, symbol="MESM24", bid="18000", ask="18000.25")
    runtime.ingest(e, now=e.received_at)
    assert runtime.account.quantity("MESM24") == 1
    exit_order = PaperOrder("exit", "s", "MESM24", -1, e.event_at.isoformat())
    assert runtime.submit(exit_order, now=e.received_at).state == "ACCEPTED"
    e = quote(3, symbol="MESM24", bid="18000", ask="18000.25")
    runtime.ingest(e, now=e.received_at)
    assert runtime.account.quantity("MESM24") == 0


def test_pending_buys_reserve_cash_and_strategy_cannot_sell_anothers_shares(runtime):
    from dataclasses import replace

    runtime.limits = replace(
        runtime.limits,
        max_order_units=1000,
        position=2,
        strategy=2,
        gross=3,
        net=3,
        leverage=3,
        correlated=3,
    )
    runtime.submit(order("first", 900), now=T)
    assert runtime.submit(order("second", 900), now=T).state == "REJECTED"
    assert "cash_and_margin_reservation" in runtime.orders["second"].reason


def test_single_writer_and_uncoordinated_configuration_change(runtime):
    with pytest.raises(ValueError, match="writer"):
        PaperRuntime(runtime.store.path, contracts=runtime.contracts, symbols=["SPY"])


def test_day_order_expiry_and_disconnect_preserves_pending(runtime):
    runtime.submit(order(), now=T)
    runtime.control("disconnect", reason="test connection loss")
    e = quote(1)
    runtime.ingest(e, now=e.received_at)
    assert runtime.orders["o"].state == "ACCEPTED" and not runtime.account.fills
    runtime.control("connect", reason="fresh observation")
    runtime.control("resume", strategy="s", reason="reviewed recovery")
    e = quote(at=T + timedelta(days=1), sequence="nextday")
    runtime.ingest(e, now=e.received_at)
    assert runtime.orders["o"].state == "EXPIRED"


def test_shared_master_funding_transfer_reconciles(runtime):
    a = runtime.account
    a.prices["MESM24"] = __import__("decimal").Decimal("5000")
    a.fill("MESM24", 1, "5000", 0, T, "f1", "s")
    a.fill("MESM24", -1, "6000", 0, T, "f2", "s")
    a.prices["SPY"] = __import__("decimal").Decimal("100")
    a.fill("SPY", 1020, "100", 0, T, "stocks", "s")
    assert a.stocks.net_funding == 2000 and a.futures.net_funding == -2000
    assert a.view()["cash"] == 3000
    assert a.view()["equity"] == 105000


def test_disconnect_requires_new_observation_before_reconnect(runtime):
    runtime.control("disconnect", reason="lost socket")
    with pytest.raises(ValueError, match="New valid observation"):
        runtime.control("connect", reason="operator request before data")
    assert runtime.ingest(quote(), now=T) is False
    with pytest.raises(ValueError):
        runtime.control("connect", reason="duplicate is not fresh")
    e = quote(1)
    runtime.ingest(e, now=e.received_at)
    runtime.control("connect", reason="new valid observation verified")
    assert runtime.state["connected"]
