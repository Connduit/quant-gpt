"""Optional real latest quotes, never order submission."""

import os
from datetime import UTC, datetime

import pytest

from quantlab.paper.feeds import AlpacaQuotes


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("QUANTLAB_LIVE_STREAMING") != "1", reason="opt-in external authenticated quotes"
)
def test_alpaca_real_latest_quotes():
    if not os.getenv("APCA_API_KEY_ID") or not os.getenv("APCA_API_SECRET_KEY"):
        pytest.skip("Alpaca market-data credentials unavailable")
    feed = AlpacaQuotes(["SPY", "AAPL"])
    try:
        events = feed.poll()
        assert len(events) == 2
        assert all(
            e.received_at <= datetime.now(UTC) and e.provider == "alpaca:iex" for e in events
        )
    finally:
        feed.close()
