from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from decimal import localcontext

import polars as pl
import pytest

from quantlab.backtesting.data import DailyData
from quantlab.backtesting.engine import run_backtest
from quantlab.strategies.base import Signal
from quantlab.strategies.baselines import BuyAndHold, MeanReversion, Momentum

from .conftest import DAYS


def test_signal_cannot_fill_at_same_close_or_prior_open(make_data, targets, no_costs):
    data = make_data([(10, 100), (200, 200), (300, 300)])
    strategy = targets({DAYS[0]: 1})
    result = run_backtest(data, strategy, no_costs)
    fill = result.trades[0]
    assert fill["price"] == 200
    assert fill["timestamp"] == data.bars[1].open_time
    assert result.orders[0]["submitted_at"] == data.bars[0].available_at
    assert fill["timestamp"] > result.orders[0]["submitted_at"] > data.bars[0].close_time
    for context in strategy.observations:
        assert all(bar.available_at <= context.now for bar in context.history)
        assert context.history[-1] == context.bar


def test_delayed_bar_misses_open_and_waits_until_next_session(make_data, targets, no_costs):
    data = make_data([(100, 100)] * 3)
    late = replace(data.bars[0], available_at=data.bars[1].open_time + timedelta(hours=1))
    data = replace(data, bars=(late, *data.bars[1:]))
    result = run_backtest(data, targets({DAYS[0]: 1}), no_costs)
    assert result.trades[0]["timestamp"] == data.bars[2].open_time


def test_signal_at_open_is_not_eligible_for_that_open(make_data, targets, no_costs):
    data = make_data([(100, 100)] * 3)
    first = replace(data.bars[0], available_at=data.bars[1].open_time)
    data = replace(data, bars=(first, *data.bars[1:]))
    result = run_backtest(data, targets({DAYS[0]: 1}), no_costs)
    assert result.trades[0]["timestamp"] == data.bars[2].open_time


def test_future_close_is_not_exposed_through_portfolio_view(make_data, targets, no_costs):
    data = make_data([(100, 100), (100, 100), (100, 999)])
    second = replace(data.bars[1], available_at=data.bars[2].open_time + timedelta(hours=1))
    data = replace(data, bars=(data.bars[0], second, data.bars[2]))
    strategy = targets({DAYS[0]: 1})
    run_backtest(data, strategy, no_costs)
    context = strategy.observations[-1]
    assert context.bar.session_date == DAYS[1]
    assert context.now < data.bars[2].close_time
    assert context.portfolio.equity == 10000  # would be 10899 if today's unseen close leaked


@pytest.mark.parametrize("strategy", [Momentum(1), MeanReversion(2, threshold=D(0)), BuyAndHold()])
def test_future_price_mutation_does_not_change_past(make_data, strategy, no_costs):
    first = make_data([(100, 100), (100, 110), (110, 90), (90, 100)])
    second = make_data([(100, 100), (100, 110), (500, 900), (200, 500)])
    one = run_backtest(first, strategy, no_costs)
    two = run_backtest(second, strategy, no_costs)
    cutoff = first.bars[1].close_time
    assert [s for s in one.signals if s["timestamp"] <= cutoff] == [
        s for s in two.signals if s["timestamp"] <= cutoff
    ]
    assert [t for t in one.trades if t["timestamp"] <= cutoff] == [
        t for t in two.trades if t["timestamp"] <= cutoff
    ]
    assert one.equity[:2] == two.equity[:2]


def test_final_signal_expires_without_inventing_future_execution(make_data, targets, no_costs):
    data = make_data([(100, 100)] * 2)
    last = replace(data.bars[-1], available_at=data.bars[-1].close_time)
    data = replace(data, bars=(*data.bars[:-1], last))
    result = run_backtest(data, targets({DAYS[1]: 10}), no_costs)
    assert not result.trades
    assert result.orders[0]["status"] == "expired"
    assert result.orders[0]["reason"] == "end_of_data"


def test_multiple_pending_targets_replace_not_duplicate(make_data, no_costs):
    data = make_data([(100, 100)] * 3)
    # Two available bars arrive at the same time after the second open.
    when = data.bars[1].close_time
    data = replace(
        data,
        bars=(
            replace(data.bars[0], available_at=when),
            replace(data.bars[1], available_at=when),
            data.bars[2],
        ),
    )

    class ReplaceTarget:
        def on_bar(self, context):
            return (Signal("SYNTH", len(context.history) * 10),)

    result = run_backtest(data, ReplaceTarget(), no_costs)
    assert [o["status"] for o in result.orders] == ["cancelled", "filled"]
    assert result.trades[0]["quantity"] == 20


def test_accounting_does_not_depend_on_callers_decimal_context(make_data, no_costs):
    data = make_data([(10, 10)] * 3)
    with localcontext() as context:
        context.prec = 6
        one = run_backtest(data, BuyAndHold(D("1.23456789")), no_costs)
    with localcontext() as context:
        context.prec = 40
        two = run_backtest(data, BuyAndHold(D("1.23456789")), no_costs)
    assert one.equity == two.equity and one.trades == two.trades


def test_rejects_premature_or_unsorted_availability(make_snapshot):
    def premature(frame):
        return frame.with_columns(
            (pl.col("timestamp") - pl.duration(hours=1)).alias("available_at")
        )

    store, snapshot = make_snapshot([(100, 100)] * 2, availability=premature)
    with pytest.raises(ValueError, match="before"):
        DailyData.from_snapshot(store, snapshot)
