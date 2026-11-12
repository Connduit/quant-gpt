from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, Fill, Side
from quantlab.backtesting.portfolio import Portfolio
from quantlab.strategies.baselines import BuyAndHold

from .conftest import DAYS


def test_hand_calculated_partial_sales_and_cost_basis(make_data, targets):
    data = make_data([(100, 100), (110, 115), (120, 120), (130, 130)])
    strategy = targets({DAYS[0]: 10, DAYS[1]: 6, DAYS[2]: 0})
    config = BacktestConfig(D("10000"), Costs("0.1", "1", "0", "0", "0"))
    result = run_backtest(data, strategy, config)
    assert [trade["quantity"] for trade in result.trades] == [D(10), D(4), D(6)]
    assert [trade["realized_pnl"] for trade in result.trades] == [D(0), D("37.8"), D("117.2")]
    assert result.equity[1]["cash"] == D("8898")
    assert result.equity[1]["average_cost"] == D("110.2")
    assert result.equity[1]["equity"] == D("10048")
    assert result.equity[2]["cash"] == D("9376.6")
    assert result.equity[2]["unrealized_pnl"] == D("58.8")
    assert result.metrics["final_equity"] == D("10155")
    assert result.metrics["realized_pnl"] == D("155")
    assert result.metrics["unrealized_pnl"] == 0
    assert result.metrics["commissions"] == 5
    for row in result.equity:
        assert row["equity"] == (
            D(10000) + row["realized_pnl"] + row["unrealized_pnl"] + row["dividend_income"]
        )


def test_adverse_spread_slippage_and_commissions(make_data, targets):
    data = make_data([(100, 100)] * 3)
    strategy = targets({DAYS[0]: 10, DAYS[1]: 0})
    config = BacktestConfig(D(10000), Costs("0.1", "1", "0", "1", "4"))
    result = run_backtest(data, strategy, config)
    assert [t["price"] for t in result.trades] == [D("100.03"), D("99.97")]
    assert result.metrics["final_equity"] == D("9995.40")
    assert result.metrics["commissions"] == 4
    assert result.metrics["spread_cost"] == D("0.40")
    assert result.metrics["slippage_cost"] == D("0.20")


def test_gap_and_costs_can_reject_entire_order_without_mutation(make_data):
    data = make_data([(90, 90), (100, 100)])
    result = run_backtest(
        data, BuyAndHold(D(1)), BacktestConfig(D(100), Costs("0.005", 0, 0, 0, 0))
    )
    assert result.trades == []
    assert result.orders[0]["status"] == "rejected"
    assert result.orders[0]["reason"] == "insufficient_cash"
    assert result.equity[-1]["cash"] == 100
    assert result.equity[-1]["quantity"] == 0


def test_position_and_cash_limits_are_atomic():
    account = Portfolio(D(110))
    fill = Fill(
        1,
        "SYNTH",
        Side.BUY,
        D(1),
        datetime(2024, 1, 3, tzinfo=UTC),
        D(10),
        D(10),
        D(100),
        D(0),
        D(0),
    )
    account.apply_fill(fill)
    before = account.view({"SYNTH": D(10)})
    with pytest.raises(ValueError, match="insufficient_position"):
        account.apply_fill(replace(fill, side=Side.SELL, quantity=D(2)))
    with pytest.raises(ValueError, match="insufficient_cash_for_commission"):
        account.apply_fill(replace(fill, side=Side.SELL))
    assert account.view({"SYNTH": D(10)}) == before


def test_account_view_is_immutable():
    account = Portfolio(D(100))
    view = account.view({})
    with pytest.raises(TypeError):
        view.positions["SYNTH"] = None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"commission_per_share": "NaN"},
        {"commission_fixed": -1},
        {"slippage_bps": 10000},
        {"spread_bps": "Infinity"},
    ],
)
def test_invalid_execution_costs(kwargs):
    with pytest.raises(ValueError):
        Costs(**kwargs)


def test_minimum_commission(make_data):
    result = run_backtest(
        make_data([(100, 100)] * 2),
        BuyAndHold(D(1)),
        BacktestConfig(D(10000), Costs("0.01", 0, "1", 0, 0)),
    )
    assert result.trades[0]["commission"] == 1


def test_zero_equity_after_total_loss_stays_finite(make_data, targets):
    data = make_data([(2, 2), (2, 2), (1, 1), (1, 1)])
    result = run_backtest(
        data, targets({DAYS[0]: 1, DAYS[1]: 0}), BacktestConfig(D(3), Costs(0, 1, 0, 0, 0))
    )
    assert result.metrics["final_equity"] == 0
    assert result.metrics["total_return"] == -1
    assert result.metrics["annualized_return"] == -1
    assert result.metrics["maximum_drawdown"] == -1
    assert result.equity[-1]["daily_return"] == 0
