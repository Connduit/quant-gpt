from datetime import date, timedelta
from decimal import Decimal

import exchange_calendars as xcals
import pytest

from quantlab.backtesting.data import DailyData
from quantlab.backtesting.engine import BacktestConfig
from quantlab.backtesting.models import Costs
from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily
from quantlab.strategies.base import Signal


class Targets:
    def __init__(self, targets):
        self.targets = targets
        self.observations = []

    def on_bar(self, context):
        self.observations.append(context)
        target = self.targets.get(context.bar.session_date)
        return () if target is None else (Signal(context.bar.symbol, target),)


@pytest.fixture
def targets():
    return Targets


@pytest.fixture
def no_costs():
    return BacktestConfig(Decimal("10000"), Costs(0, 0, 0, 0, 0))


@pytest.fixture
def make_snapshot(tmp_path):
    def make(prices, *, actions=None, basis="synthetic", synthetic=True, availability=None):
        calendar = xcals.get_calendar("XNYS", start="2024-01-01", end="2024-03-01")
        dates = [s.date() for s in calendar.sessions[: len(prices)]]
        lines = ["Date,Open,High,Low,Close,Volume"]
        for day, (opening, closing) in zip(dates, prices, strict=True):
            opening, closing = Decimal(str(opening)), Decimal(str(closing))
            high, low = (
                max(opening, closing) * Decimal("1.1"),
                min(opening, closing) * Decimal("0.9"),
            )
            lines.append(f"{day},{opening},{high},{low},{closing},1000")
        raw = ("\n".join(lines) + "\n").encode()
        request = DataRequest("SYNTH", dates[0], dates[-1])
        frame = normalize_daily(raw, request)
        if availability:
            frame = availability(frame)
        store = SnapshotStore(tmp_path / "input")
        snapshot = store.write(
            "test-fixture",
            request,
            Download(raw, "synthetic test fixture", basis, synthetic),
            frame,
        )
        return store, snapshot

    return make


@pytest.fixture
def make_data(make_snapshot):
    def make(prices, *, actions=None, **kwargs):
        store, snapshot = make_snapshot(prices, **kwargs)
        return DailyData.from_snapshot(store, snapshot, actions)

    return make


DAYS = [date(2024, 1, 2) + timedelta(days=i) for i in range(4)]
