"""Hand-calculated financial and clock checks for Phase 12C."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal as D

import pytest

from quantlab.backtesting.actions import CorporateActions
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, OpeningEvent, Order, Side
from quantlab.profitability.strategy import StrategyPolicy, verify_prediction_rows


def test_cost_decomposition_and_same_open_rejection():
    now = datetime.fromisoformat("2024-01-02T14:30:00+00:00")
    order = Order(1, "AAA", Side.BUY, D(10), now - timedelta(seconds=1), D(10))
    costs = Costs(commission_per_share="0.1", spread_bps=20, slippage_bps=10, market_impact_bps=5)
    fill = costs.fill(order, OpeningEvent("AAA", now, D(100)))
    assert fill.price == D("100.25")
    assert fill.commission == D(1)
    assert fill.spread_cost == D(1)
    assert fill.slippage_cost == D(1)
    assert fill.market_impact_cost == D("0.5")
    with pytest.raises(ValueError, match="strictly before"):
        costs.fill(replace(order, submitted_at=now), OpeningEvent("AAA", now, D(100)))


def test_terminal_liquidation_net_cash_and_turnover(make_data, targets):
    data = make_data([(100, 100), (100, 100), (110, 110), (120, 120)])
    strategy = targets({data.bars[0].session_date: D(10)})
    result = run_backtest(
        data,
        strategy,
        BacktestConfig(D(2000), Costs("0.1", 0, 0, 0, 0), liquidate_at_end=True, whole_shares=True),
    )
    assert len(result.trades) == 2
    assert result.trades[0]["timestamp"] == data.bars[1].open_time
    assert result.trades[-1]["timestamp"] == data.bars[-1].open_time
    assert result.metrics["commissions"] == D(2)
    assert result.metrics["final_equity"] == D(2198)  # 200 gross profit less two $1 fees.
    assert result.metrics["total_return"] == pytest.approx(0.099)
    assert result.equity[-1]["cash"] == D(2198) and result.equity[-1]["quantity"] == 0
    assert result.metrics["gross_turnover"] == pytest.approx(
        2200 / ((2000 + 1999 + 2099 + 2198) / 4)
    )
    assert result.signals[-1]["decision"] == "EXIT"


def test_whole_and_fractional_target_assumptions(make_data, targets):
    data = make_data([(100, 100)] * 4)

    def run(whole):
        return run_backtest(
            data,
            targets({data.bars[0].session_date: D("1.5")}),
            BacktestConfig(D(1000), Costs(0, 0, 0, 0, 0), whole_shares=whole),
        )

    assert run(True).trades[0]["quantity"] == 1
    assert run(False).trades[0]["quantity"] == D("1.5")


def test_unknown_events_are_not_certified_empty_coverage():
    today = date(2024, 1, 1)
    with pytest.raises(ValueError, match="cannot claim"):
        CorporateActions("AAA", today, today, "unknown", coverage_method="unverified_events")
    value = CorporateActions(
        "AAA",
        today,
        today,
        "event evidence absent",
        complete=False,
        coverage_method="unverified_events",
        limitations=("Unknown events",),
    )
    assert not value.complete


def test_prediction_clocks_fail_before_execution():
    from datetime import UTC, datetime

    now = datetime(2024, 1, 2, tzinfo=UTC)
    row = dict(
        symbol="AAA",
        session_date=now.date(),
        prediction=0.1,
        momentum=0.1,
        ma_distance_long=0.1,
        realized_vol_long=0.2,
        dollar_volume_ma=1e7,
        train_label_max=now - timedelta(days=2),
        model_available_at=now - timedelta(days=1),
        prediction_at=now,
        execution_at=now + timedelta(hours=10),
    )
    verify_prediction_rows([row])
    for change in (
        {"execution_at": now},
        {"model_available_at": now + timedelta(seconds=1)},
        {"train_label_max": now},
        {"prediction": float("nan")},
    ):
        with pytest.raises(ValueError):
            verify_prediction_rows([{**row, **change}])
    with pytest.raises(ValueError, match="Duplicate"):
        verify_prediction_rows([row, row])
    with pytest.raises(ValueError):
        StrategyPolicy(probability_threshold=1.1)


def test_impact_is_allocated_without_double_counting():
    from datetime import UTC

    from quantlab.backtesting.models import Fill
    from quantlab.portfolio.ledger import distribute_fill

    fill = Fill(
        1,
        "AAA",
        Side.BUY,
        D(10),
        datetime(2024, 1, 2, tzinfo=UTC),
        D(100),
        D("100.25"),
        D(1),
        D(1),
        D(1),
        D("0.5"),
    )
    allocated = distribute_fill(fill, {"first": D(6), "second": D(4)})
    assert sum(v.market_impact_cost for v in allocated.values()) == D("0.5")
    assert allocated["first"].market_impact_cost == D("0.3")
