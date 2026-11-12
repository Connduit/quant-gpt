"""Run explicitly: QUANTLAB_LIVE_PROVIDERS=1 pytest -m live -q."""

import os
from datetime import date

import pytest

from quantlab.data.ingestion import ingest
from quantlab.data.providers.base import DataRequest, ProviderHTTPError, ProviderNetworkError
from quantlab.data.providers.lean import LeanProvider
from quantlab.data.providers.stooq import StooqProvider
from quantlab.data.storage import SnapshotStore

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("QUANTLAB_LIVE_PROVIDERS") != "1", reason="live HTTPS opt-in"),
]


@pytest.mark.parametrize("symbol", ["SPY", "AAPL", "IBM"])
def test_live_historical_roundtrip(tmp_path, symbol):
    name = os.getenv("QUANTLAB_LIVE_PROVIDER", "lean")
    if name not in ("lean", "stooq"):
        pytest.fail("QUANTLAB_LIVE_PROVIDER must be lean or stooq")
    provider = LeanProvider() if name == "lean" else StooqProvider()
    request = DataRequest(symbol, date(2018, 1, 2), date(2018, 1, 10))
    try:
        identifier, cached = ingest(provider, request, SnapshotStore(tmp_path))
    except (ProviderNetworkError, ProviderHTTPError) as exc:
        pytest.fail(f"LIVE_NETWORK_OR_HTTP_FAILURE: {exc}")
    # Validation errors deliberately propagate as application/data failures.
    store = SnapshotStore(tmp_path)
    frame = store.read(identifier)
    assert not cached
    assert frame.height == 7
    assert frame["symbol"].unique().to_list() == [symbol]
    assert frame["session_date"].min() == request.start
    assert frame["session_date"].max() == request.end
    assert (frame["volume"] >= 0).all()
    assert store.manifest(identifier)["synthetic"] is False
    assert ingest(provider, request, store) == (identifier, True)
