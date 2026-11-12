from datetime import UTC, datetime, timedelta

import pytest

from quantlab.futures.contracts import contract_from_dict
from quantlab.paper.events import MarketEvent
from quantlab.paper.runtime import PaperRuntime

T = datetime(2024, 6, 3, 13, 30, tzinfo=UTC)


def quote(
    n=0, *, symbol="SPY", bid="100", ask="100.02", size=100, sequence=None, mode="replay", at=None
):
    at = at or T + timedelta(seconds=n)
    return MarketEvent(
        symbol,
        "test",
        at,
        at,
        "quote",
        mode,
        str(sequence if sequence is not None else n),
        bid,
        ask,
        size,
        size,
    )


@pytest.fixture
def contract():
    return contract_from_dict(
        {
            "identifier": "MESM24",
            "product": "MES",
            "month": 6,
            "year": 2024,
            "expiration": "2024-06-21T13:30:00+00:00",
            "last_trade": "2024-06-21T13:30:00+00:00",
            "metadata_source": "test contract rule",
            "initial_margin": "1500",
            "maintenance_margin": "1200",
            "margin_as_of": "2024-06-01",
            "margin_source": "test assumption",
        }
    )


@pytest.fixture
def runtime(tmp_path, contract):
    r = PaperRuntime(tmp_path / "paper.sqlite", contracts={"MESM24": contract}, symbols=["SPY"])
    r.register("s", capital=50000, experimental=True)
    r.ingest(quote(), now=T)
    r.control("connect", reason="test feed verified")
    r.control("resume", strategy="s", reason="test replay")
    yield r
    r.close()
