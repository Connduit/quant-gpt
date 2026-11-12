from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quantlab.backtesting.data import DailyData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, Fill, Side, decimal
from quantlab.backtesting.portfolio import Portfolio
from quantlab.data.ingestion import ingest
from quantlab.data.providers.base import DataRequest
from quantlab.data.providers.fixture import FixtureProvider
from quantlab.data.storage import SnapshotStore
from quantlab.portfolio.book import MultiStrategyBook, Registration
from quantlab.portfolio.ledger import reconcile
from quantlab.portfolio.risk import RiskLimits
from quantlab.strategies.baselines import BuyAndHold


def limits():
    return RiskLimits(
        maximum_gross=1,
        maximum_net=1,
        maximum_position=1,
        maximum_sector=1,
        maximum_correlated=1,
        maximum_strategy=1,
        maximum_daily_loss=1,
        maximum_drawdown=1,
        maximum_strategy_drawdown=1,
    )


@pytest.fixture
def feed(tmp_path):
    store = SnapshotStore(tmp_path)
    identifier, _ = ingest(
        FixtureProvider(), DataRequest("SYNTH", date(2024, 1, 2), date(2024, 1, 8)), store
    )
    return DailyData.from_snapshot(store, identifier)


def book():
    return MultiStrategyBook(
        [Registration("a", BuyAndHold(Decimal(10))), Registration("b", BuyAndHold(Decimal(10)))],
        limits=limits(),
        cash_buffer=0,
        schedule="daily",
        threshold=0,
        minimum_trade_value=0,
        maximum_turnover=2,
    )


def test_shared_cash_fill_attribution_and_fees(feed):
    b = book()
    config = BacktestConfig(
        decimal(10000), Costs(commission_per_share=decimal(".1"), slippage_bps=0)
    )
    result = run_backtest(feed, b, config)
    assert result.trades
    assert len(result.trades) == 1
    assert sum(float(v["pnl"]) for v in b.attribution[-2:]) == pytest.approx(
        float(result.metrics["final_equity"]) - 10000
    )
    assert sum(p.commissions for p in b.ledgers.values()) == sum(
        t["commission"] for t in result.trades
    )
    assert all(r["cash"] >= 0 for r in result.equity)
    assert (
        sum(p.positions["SYNTH"].quantity for p in b.ledgers.values())
        == result.positions[-1]["quantity"]
    )


def test_internal_netting_hand_calculated_no_extra_cash():
    b = book()
    master = Portfolio(decimal(2000))
    b.on_start(master, {"SYNTH": None}, BacktestConfig(decimal(2000), Costs(slippage_bps=0)))
    now = datetime(2024, 1, 2, tzinfo=UTC)
    fill = Fill(
        1,
        "SYNTH",
        Side.BUY,
        decimal(10),
        now,
        decimal(100),
        decimal(100),
        decimal(0),
        decimal(0),
        decimal(0),
    )
    master.apply_fill(fill)
    b.ledgers["a"].apply_fill(fill)
    b.targets = {"a": {"SYNTH": decimal(0)}, "b": {"SYNTH": decimal(10)}}
    b._cross(now, {"SYNTH": decimal(110)})
    assert master.cash == 1000
    assert b.ledgers["a"].positions["SYNTH"].quantity == 0
    assert b.ledgers["b"].positions["SYNTH"].quantity == 10
    assert b.ledgers["a"].view({"SYNTH": decimal(110)}).equity - 1000 == 100
    assert b.ledgers["b"].view({"SYNTH": decimal(110)}).equity - 1000 == 0
    assert all(
        abs(v) < Decimal("1e-18")
        for v in reconcile(b.ledgers, master, {"SYNTH": decimal(110)}).values()
    )


def test_opening_gap_cash_reduction_no_phantom_virtual_fill(feed):
    b = book()
    result = run_backtest(
        feed, b, BacktestConfig(decimal(410), Costs(commission_fixed=decimal(10), slippage_bps=10))
    )
    assert all(r["cash"] >= 0 for r in result.equity)
    assert any(r["decision"] in ("REDUCED", "REJECTED") for r in b.risk_decisions)
    assert sum(p.commissions for p in b.ledgers.values()) == sum(
        t["commission"] for t in result.trades
    )


def test_eligibility_and_manual_reactivation():
    with pytest.raises(PermissionError):
        MultiStrategyBook([Registration("failed", BuyAndHold(), "REJECTED", True)], mode="paper")
    with pytest.raises(PermissionError):
        MultiStrategyBook(
            [Registration("ok", BuyAndHold(), "VALIDATED_FOR_PAPER_TRADING", False)], mode="paper"
        )
    with pytest.raises(ValueError):
        MultiStrategyBook([Registration("a", BuyAndHold())], mode="live")
    b = book()
    b.registrations["a"].suspended = True
    with pytest.raises(PermissionError):
        b.reactivate("a", reason="")
    b.previous_strategy["a"] = decimal(100)
    b.reactivate("a", reason="reviewed", approved=True)
    assert not b.registrations["a"].suspended


def test_daily_weekly_monthly_rebalance(feed):
    counts = []
    for schedule in ("daily", "weekly", "monthly"):
        b = book()
        b.schedule = schedule
        run_backtest(feed, b, BacktestConfig(decimal(10000), Costs(slippage_bps=0)))
        counts.append(len(b.logs))
    assert counts[0] >= counts[1] >= counts[2]


def test_future_reference_returns_cannot_change_early_allocations(feed):
    b = book()
    b.method = "inverse_volatility"
    b.reference_history = (
        {"available_at": datetime(2030, 1, 1, tzinfo=UTC), "returns": [100, -100]},
    )
    run_backtest(feed, b, BacktestConfig(decimal(10000), Costs(slippage_bps=0)))
    assert all(a["cash_weight"] == 1 for a in b.allocations)


def test_dividends_and_splits_reconcile_attribution():
    from types import SimpleNamespace

    b = book()
    master = Portfolio(decimal(2000))
    b.on_start(master, {"SYNTH": None}, BacktestConfig(decimal(2000)))
    now = datetime(2024, 1, 2, tzinfo=UTC)
    fill = Fill(
        1,
        "SYNTH",
        Side.BUY,
        decimal(10),
        now,
        decimal(100),
        decimal(100),
        decimal(0),
        decimal(0),
        decimal(0),
    )
    master.apply_fill(fill)
    b.ledgers["a"].apply_fill(fill)
    master.split("SYNTH", decimal(2))
    b.on_action("split", ("SYNTH", SimpleNamespace(ratio=decimal(2))), now)
    master.accrue_dividend(1, "SYNTH", decimal(1))
    b.on_action("dividend_ex", ("SYNTH", 1, SimpleNamespace(amount=decimal(1))), now)
    assert master.view({"SYNTH": decimal(50)}).dividend_receivable == 20
    reconcile(b.ledgers, master, {"SYNTH": decimal(50)})
    master.pay_dividend(1)
    b.on_action("dividend_pay", ("SYNTH", 1, None), now)
    reconcile(b.ledgers, master, {"SYNTH": decimal(50)})


def test_liquidity_and_unavailable_execution_no_phantom_positions(feed):
    b = book()
    b.maximum_participation = 0.001
    result = run_backtest(feed, b, BacktestConfig(decimal(10000), Costs(slippage_bps=0)))
    assert result.trades[0]["quantity"] <= decimal(1)
    b = book()
    b.execution_available = False
    result = run_backtest(feed, b, BacktestConfig(decimal(10000), Costs(slippage_bps=0)))
    assert not result.trades
    assert result.metrics["final_equity"] == 10000
    assert all(not p.positions for p in b.ledgers.values())


def test_suspension_and_documented_one_time_stress_cap(feed):
    bars = tuple(
        replace(b, open=b.open / 2, high=b.high / 2, low=b.low / 2, close=b.close / 2)
        if i >= 2
        else b
        for i, b in enumerate(feed.bars)
    )
    b = book()
    b.limits = replace(limits(), maximum_drawdown=0.05, maximum_strategy_drawdown=0.05)
    result = run_backtest(
        replace(feed, bars=bars), b, BacktestConfig(decimal(10000), Costs(slippage_bps=0))
    )
    assert b.stressed
    assert all(r.suspended for r in b.registrations.values())
    assert sum(e["kind"] == "portfolio_stress_cap" for e in b.logs) == 1
    assert result.positions[-1]["quantity"] > 0
    with pytest.raises(PermissionError):
        b.reactivate_portfolio(reason="review")
    b.reactivate_portfolio(reason="manual review", approved=True)
    assert not b.stressed


def test_repeated_fractional_attribution_and_complete_exit():
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 34
        b = book()
        master = Portfolio(decimal(100000))
        b.on_start(master, {"SYNTH": None}, BacktestConfig(decimal(100000)))
        now = datetime(2024, 1, 2, tzinfo=UTC)
        for _ in range(40):
            b.targets = {"a": {"SYNTH": decimal(1000)}, "b": {"SYNTH": decimal(2000)}}
            fill = Fill(
                1,
                "SYNTH",
                Side.BUY,
                decimal(3),
                now,
                decimal(10),
                decimal(10),
                decimal(".01"),
                decimal(0),
                decimal(0),
            )
            master.apply_fill(fill)
            b.on_fill(fill)
            actual = sum(p.positions["SYNTH"].quantity for p in b.ledgers.values())
            assert actual == master.positions["SYNTH"].quantity
            assert all(
                p.positions["SYNTH"].quantity
                == p.positions["SYNTH"].quantity.quantize(decimal("1e-18"))
                for p in b.ledgers.values()
            )
        b.targets = {"a": {"SYNTH": decimal(0)}, "b": {"SYNTH": decimal(0)}}
        fill = replace(fill, side=Side.SELL, quantity=master.positions["SYNTH"].quantity)
        master.apply_fill(fill)
        b.on_fill(fill)
        assert all(p.positions["SYNTH"].quantity == 0 for p in b.ledgers.values())
        reconcile(b.ledgers, master, {"SYNTH": decimal(10)})
