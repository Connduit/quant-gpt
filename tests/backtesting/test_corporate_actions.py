import json
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from quantlab.backtesting.actions import CorporateActions, Dividend, Split
from quantlab.backtesting.data import DailyData
from quantlab.backtesting.engine import run_backtest

from .conftest import DAYS


def ledger(*, splits=(), dividends=()):
    return CorporateActions(
        "SYNTH", DAYS[0], date(2024, 2, 1), "explicit synthetic test ledger", splits, dividends
    )


@pytest.mark.parametrize(
    "ratio,price,quantity,cost",
    [
        (D(2), 50, 20, 50),
        (D("0.5"), 200, 5, 200),
    ],
)
def test_split_preserves_value_and_cost_basis(
    make_data, targets, no_costs, ratio, price, quantity, cost
):
    actions = ledger(splits=(Split(DAYS[2], ratio),))
    data = make_data([(100, 100), (100, 100), (price, price), (price, price)], actions=actions)
    strategy = targets({DAYS[0]: 10})
    result = run_backtest(data, strategy, no_costs)
    assert result.equity[-1]["quantity"] == quantity
    assert result.equity[-1]["average_cost"] == cost
    assert all(row["equity"] == 10000 for row in result.equity)
    assert strategy.observations[-1].history[0].close == D(100) / ratio
    assert strategy.observations[1].history[0].close == 100  # action not known yet


def test_split_adjusts_pending_orders_without_double_exposure(make_data, targets, no_costs):
    actions = ledger(splits=(Split(DAYS[2], D(2)),))
    data = make_data([(100, 100), (100, 100), (50, 50), (50, 50)], actions=actions)
    result = run_backtest(data, targets({DAYS[1]: 10}), no_costs)
    assert result.orders[0]["original_quantity"] == 10
    assert result.orders[0]["quantity"] == 20
    assert result.trades[0]["quantity"] == 20
    assert result.trades[0]["price"] == 50
    assert result.equity[-1]["cash"] == 9000


def test_dividend_entitlement_survives_ex_date_sale(make_data, targets, no_costs):
    actions = ledger(dividends=(Dividend(DAYS[2], DAYS[3], D(2)),))
    data = make_data([(100, 100), (100, 100), (98, 98), (98, 98)], actions=actions)
    result = run_backtest(data, targets({DAYS[0]: 10, DAYS[1]: 0}), no_costs)
    assert result.equity[2]["cash"] == 9980
    assert result.equity[2]["dividend_receivable"] == 20
    assert result.equity[2]["equity"] == 10000
    assert result.equity[-1]["cash"] == 10000
    assert result.metrics["dividend_income"] == 20
    assert result.metrics["realized_pnl"] == -20
    assert result.metrics["final_equity"] == 10000
    assert all(row["timestamp"].utcoffset().total_seconds() == 0 for row in result.actions)


def test_ex_date_buyer_does_not_receive_dividend(make_data, targets, no_costs):
    actions = ledger(dividends=(Dividend(DAYS[2], DAYS[3], D(2)),))
    data = make_data([(100, 100), (100, 100), (98, 98), (98, 98)], actions=actions)
    result = run_backtest(data, targets({DAYS[1]: 10}), no_costs)
    assert result.metrics["dividend_income"] == 0
    assert result.equity[-1]["cash"] == 9020


def test_dividend_receivable_cannot_fund_orders(make_data, targets, no_costs):
    actions = ledger(dividends=(Dividend(DAYS[2], date(2024, 2, 1), D(2)),))
    data = make_data([(100, 100), (100, 100), (98, 98)], actions=actions)
    result = run_backtest(data, targets({DAYS[0]: 100, DAYS[1]: 102}), no_costs)
    assert result.orders[1]["status"] == "rejected"
    assert result.orders[1]["reason"] == "insufficient_cash"
    assert result.equity[-1]["dividend_receivable"] == 200
    assert result.equity[-1]["cash"] == 0


def test_dividend_unpaid_at_end_remains_in_equity_not_spendable_cash(make_data, targets, no_costs):
    actions = ledger(dividends=(Dividend(DAYS[2], date(2024, 2, 1), D(2)),))
    data = make_data([(100, 100), (100, 100), (98, 98)], actions=actions)
    result = run_backtest(data, targets({DAYS[0]: 10}), no_costs)
    assert result.equity[-1]["cash"] == 9000
    assert result.equity[-1]["dividend_receivable"] == 20
    assert result.metrics["final_equity"] == 10000


def test_same_day_split_and_dividend_use_post_split_shares(make_data, targets, no_costs):
    actions = ledger(splits=(Split(DAYS[2], D(2)),), dividends=(Dividend(DAYS[2], DAYS[2], D(1)),))
    data = make_data([(100, 100), (100, 100), (49, 49)], actions=actions)
    result = run_backtest(data, targets({DAYS[0]: 10}), no_costs)
    assert result.metrics["dividend_income"] == 20
    assert result.equity[-1]["cash"] == 9020
    assert result.equity[-1]["dividend_receivable"] == 0
    assert result.metrics["final_equity"] == 10000


def test_real_prices_require_raw_basis_and_complete_action_coverage(make_snapshot):
    prices = [(100, 100)] * 2
    store, snapshot = make_snapshot(prices, basis="vendor_adjustment_unspecified", synthetic=False)
    with pytest.raises(ValueError, match="unadjusted"):
        DailyData.from_snapshot(store, snapshot, ledger())
    store, snapshot = make_snapshot(prices, basis="unadjusted", synthetic=False)
    with pytest.raises(ValueError, match="complete corporate-action"):
        DailyData.from_snapshot(store, snapshot)
    assert DailyData.from_snapshot(store, snapshot, ledger()).instrument.symbol == "SYNTH"
    with pytest.raises(ValueError, match="cover"):
        DailyData.from_snapshot(store, snapshot, replace(ledger(), symbol="OTHER"))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Split(DAYS[1], D(0)),
        lambda: Split(DAYS[1], D("NaN")),
        lambda: Dividend(DAYS[2], DAYS[1], D(1)),
        lambda: Dividend(DAYS[1], DAYS[2], D(-1)),
        lambda: ledger(splits=(Split(DAYS[1], D(2)), Split(DAYS[1], D(2)))),
        lambda: CorporateActions("SYNTH", DAYS[0], DAYS[2], "test", complete=False),
    ],
)
def test_invalid_action_ledgers(factory):
    with pytest.raises(ValueError):
        factory()


def test_json_action_ledger(tmp_path):
    path = tmp_path / "actions.json"
    path.write_text(
        json.dumps(
            {
                "symbol": "SYNTH",
                "coverage_start": "2024-01-02",
                "coverage_end": "2024-01-08",
                "source": "synthetic test ledger",
                "complete": True,
                "splits": [{"date": "2024-01-04", "ratio": "2"}],
                "dividends": [
                    {"ex_date": "2024-01-05", "pay_date": "2024-01-08", "amount": "0.25"}
                ],
            }
        )
    )
    actions = CorporateActions.load(path)
    assert actions.splits[0].ratio == 2
    assert actions.dividends[0].amount == D("0.25")
    path.write_text('{"symbol": "SYNTH"}')
    with pytest.raises(ValueError, match="exactly"):
        CorporateActions.load(path)
