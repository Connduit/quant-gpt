"""Explicit selection; no fallback to another provider, feed or synthetic data."""

import os

from quantlab.data.providers.equity_api import AlpacaHistoricalProvider, DatabentoEquityProvider


def create_provider(
    name, *, timeout=30, alpaca_feed="sip", databento_dataset="XNAS.ITCH", maximum_download_cost=0
):
    if name == "alpaca":
        return AlpacaHistoricalProvider(feed=alpaca_feed, timeout=timeout)
    if name == "databento":
        return DatabentoEquityProvider(
            dataset=databento_dataset, maximum_download_cost=maximum_download_cost
        )
    if name == "stooq":
        from quantlab.data.providers.stooq import StooqProvider

        return StooqProvider(timeout)
    if name == "lean":
        from quantlab.data.providers.lean import LeanProvider

        return LeanProvider(timeout=timeout)
    if name == "fixture":
        from quantlab.data.providers.fixture import FixtureProvider

        return FixtureProvider()
    raise ValueError("Unsupported historical provider")


def provider_status(credentials=None):
    credentials = os.environ if credentials is None else credentials
    return {
        "items": [
            {
                "id": "alpaca",
                "configured": bool(
                    credentials.get("APCA_API_KEY_ID") and credentials.get("APCA_API_SECRET_KEY")
                ),
                "required_secrets": ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"],
                "host": "data.alpaca.markets",
                "feeds": ["sip", "iex"],
            },
            {
                "id": "databento",
                "configured": bool(credentials.get("DATABENTO_API_KEY")),
                "required_secrets": ["DATABENTO_API_KEY"],
                "host": "hist.databento.com",
                "datasets": ["XNAS.ITCH", "DBEQ.BASIC"],
            },
        ],
        "connectivity_verified": False,
    }
