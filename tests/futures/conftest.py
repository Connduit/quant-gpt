from datetime import UTC, datetime

import polars as pl
import pytest

from quantlab.futures.calendar import FuturesCalendar
from quantlab.futures.contracts import Contract
from quantlab.futures.storage import normalize


@pytest.fixture
def contract():
    return Contract(
        "ES",
        "ESM24",
        6,
        2024,
        datetime(2024, 6, 21, 13, 30, tzinfo=UTC),
        datetime(2024, 6, 21, 13, 30, tzinfo=UTC),
        "explicit synthetic metadata fixture",
        initial_margin="10000",
        maintenance_margin="8000",
        margin_as_of="2024-06-01",
        margin_source="synthetic research assumption",
    )


@pytest.fixture
def minute_frame(contract):
    calendar = FuturesCalendar()
    rows = []
    for i, t in enumerate(calendar.expected("2024-06-20")[:30]):
        price = 100 + i * 0.25
        rows.append(
            {
                "timestamp": t,
                "open": price,
                "high": price + 0.25,
                "low": price - 0.25,
                "close": price,
                "volume": 10000,
                "contract": contract.identifier,
            }
        )
    raw = pl.DataFrame(rows).write_csv().encode()
    frame, quality = normalize(raw, contract, allow_sparse=True)
    return frame, quality, raw
