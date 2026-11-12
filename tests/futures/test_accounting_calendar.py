from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from quantlab.backtesting.models import decimal
from quantlab.futures.accounting import FuturesLedger
from quantlab.futures.calendar import FuturesCalendar


@pytest.mark.parametrize(
    "product,multiplier,tick", [("ES", 50, 12.5), ("MES", 5, 1.25), ("NQ", 20, 5), ("MNQ", 2, 0.5)]
)
@pytest.mark.parametrize("direction", [1, -1])
def test_hand_calculated_contract_pnl(contract, product, multiplier, tick, direction):
    c = replace(contract, product=product)
    assert c.spec.multiplier == multiplier and float(c.spec.tick_value) == tick
    ledger = FuturesLedger(100000, {c.identifier: c})
    ledger.fill(c.identifier, 2 * direction, 100, fee=4)
    ledger.fill(c.identifier, -2 * direction, 101, fee=4)
    assert (
        ledger.view({c.identifier: decimal(101)})["equity"]
        == decimal(100000) + decimal(multiplier * 2 * direction) - 8
    )
    assert ledger.positions[c.identifier].quantity == 0


def test_daily_settlement_does_not_double_count_trade_profit(contract):
    ledger = FuturesLedger(100000, {contract.identifier: contract})
    ledger.fill(contract.identifier, 2, 100)
    ledger.settle(
        contract.identifier,
        110,
        timestamp=datetime(2024, 6, 20, 20, tzinfo=UTC),
        source="synthetic hand settlement",
    )
    assert ledger.cash == 101000
    assert ledger.view({contract.identifier: decimal(115)})["equity"] == 101500
    ledger.fill(contract.identifier, -2, 115)
    assert ledger.cash == 101500 and ledger.realized_gross == 1500
    assert ledger.trades[-1]["closed_net_pnl"] == 1500


def test_short_settlement_reversal_and_tick_validation(contract):
    ledger = FuturesLedger(100000, {contract.identifier: contract})
    ledger.fill(contract.identifier, -1, 100)
    ledger.settle(
        contract.identifier, 95, timestamp=datetime(2024, 6, 20, 20, tzinfo=UTC), source="test"
    )
    ledger.fill(contract.identifier, 2, 90)
    assert ledger.positions[contract.identifier].quantity == 1
    assert ledger.realized_gross == 500
    assert ledger.view({contract.identifier: decimal(90)})["equity"] == 100500
    with pytest.raises(ValueError, match="tick"):
        ledger.fill(contract.identifier, 1, 90.1)
    with pytest.raises(ValueError, match="Whole"):
        ledger.fill(contract.identifier, 0.5, 90)


def test_sessions_dst_weekends_maintenance_and_early_close():
    calendar = FuturesCalendar(mode="eth")
    before = calendar.calendar.session_open("2024-03-04").to_pydatetime()
    after = calendar.calendar.session_open("2024-03-11").to_pydatetime()
    assert before.hour != after.hour
    assert calendar.session(before) == date(2024, 3, 4)
    assert calendar.session(after) == date(2024, 3, 11)
    assert calendar.session(datetime(2024, 3, 9, 18, tzinfo=UTC)) is None
    assert calendar.session(datetime(2024, 3, 11, 21, 30, tzinfo=UTC)) is None
    early = FuturesCalendar(early_closes={date(2024, 6, 20): time(12)})
    assert early.session(datetime(2024, 6, 20, 16, 59, tzinfo=UTC)) == date(2024, 6, 20)
    assert early.session(datetime(2024, 6, 20, 17, tzinfo=UTC)) is None
    with pytest.raises(ValueError):
        calendar.session(datetime(2024, 1, 1))
