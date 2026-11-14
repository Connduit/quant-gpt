import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from quantlab.data.providers.base import DataRequest, ProviderError
from quantlab.data.providers.equity_api import (
    AlpacaHistoricalProvider,
    DatabentoEquityProvider,
    session_csv,
)
from quantlab.data.providers.factory import create_provider, provider_status
from quantlab.data.validation import normalize_daily
from quantlab.web.workflows import DownloadRequest


def request():
    return DataRequest("AAPL", date(2018, 11, 23), date(2018, 11, 23))


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_regular_session_aggregation_excludes_extended_hours_and_half_day_close():
    bars = [
        (stamp(at), values)
        for at, values in (
            ("2018-11-23T13:00:00Z", [500, 501, 499, 500, 100]),
            ("2018-11-23T14:30:00Z", [100, 102, 99, 101, 100]),
            ("2018-11-23T17:59:00Z", [101, 104, 100, 103, 200]),
            ("2018-11-23T18:00:00Z", [600, 601, 599, 600, 100]),
        )
    ]
    frame = normalize_daily(session_csv(bars, request()), request())
    assert frame.select("open", "high", "low", "close", "volume").row(0) == (100, 104, 99, 103, 300)
    with pytest.raises(ProviderError, match="Duplicate"):
        session_csv([bars[1], bars[1]], request())
    with pytest.raises(ProviderError, match="outside"):
        session_csv([(datetime(2019, 1, 2, 15, tzinfo=UTC), [1, 1, 1, 1, 1])], request())


def test_alpaca_pagination_raw_feed_and_credential_redaction(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "private-test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "private-test-secret")
    calls = []

    def respond(req):
        calls.append(req)
        assert req.headers["APCA-API-KEY-ID"] == "private-test-key"
        assert req.url.host == "data.alpaca.markets"
        assert req.url.params["adjustment"] == "raw"
        assert req.url.params["asof"] == str(request().end)
        assert req.url.params["feed"] == "sip"
        assert req.url.params["timeframe"] == "1Min"
        if len(calls) > 1:
            assert req.url.params["page_token"] == "page2"
        return httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "bars": [
                    {
                        "t": "2018-11-23T14:30:00Z" if len(calls) == 1 else "2018-11-23T17:59:00Z",
                        "o": 100,
                        "h": 102,
                        "l": 99,
                        "c": 101,
                        "v": 100,
                    }
                ],
                "next_page_token": "page2" if len(calls) == 1 else None,
            },
        )

    provider = AlpacaHistoricalProvider(transport=httpx.MockTransport(respond))
    download = provider.fetch(request())
    assert len(calls) == 2
    assert normalize_daily(download.raw, request())["volume"][0] == 200
    assert "private-test" not in download.source
    assert download.price_basis == "unadjusted"
    assert json.loads(download.source)["asof"] == str(request().end)
    assert "asof-end-v2" in provider.name
    assert create_provider("alpaca", alpaca_feed="iex").name != provider.name


@pytest.mark.parametrize("status", [401, 403, 429])
def test_alpaca_errors_do_not_retry_or_expose_secrets(monkeypatch, status):
    monkeypatch.setenv("APCA_API_KEY_ID", "secret-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-password")
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(status, text="secret-password echoed by remote")

    with pytest.raises(ProviderError, match=f"HTTP {status}") as exc:
        AlpacaHistoricalProvider(transport=httpx.MockTransport(respond)).fetch(request())
    assert len(calls) == 1 and "secret-password" not in str(exc.value)


def databento_client(cost=0, start="2018-01-01T00:00:00+00:00", instrument_ids=(1, 1)):
    calls = []
    frame = pd.DataFrame(
        {
            "open": [100, 101],
            "high": [102, 104],
            "low": [99, 100],
            "close": [101, 103],
            "volume": [100, 200],
            "instrument_id": instrument_ids,
        },
        index=pd.to_datetime(["2018-11-23T14:30:00Z", "2018-11-23T17:59:00Z"]),
    )

    def download(**params):
        calls.append(params)
        return SimpleNamespace(to_df=lambda **kw: frame)

    metadata = SimpleNamespace(
        get_dataset_range=lambda **kw: {"start": start, "end": "2019-01-01T00:00:00+00:00"},
        get_cost=lambda **kw: cost,
    )
    return SimpleNamespace(metadata=metadata, timeseries=SimpleNamespace(get_range=download)), calls


def test_databento_aggregate_and_total_budget():
    client, calls = databento_client(cost=0.25)
    provider = DatabentoEquityProvider(client=client, maximum_download_cost=0.3)
    download = provider.fetch(request())
    assert normalize_daily(download.raw, request())["volume"][0] == 300
    assert calls[0]["schema"] == "ohlcv-1m"
    assert calls[0]["stype_in"] == "raw_symbol"
    assert calls[0]["start"] == stamp("2018-11-23T05:00:00Z")
    assert calls[0]["end"] == stamp("2018-11-24T05:00:00Z")
    with pytest.raises(ProviderError, match="remaining authorized"):
        provider.fetch(request())
    assert len(calls) == 1 and provider.quoted_cost == 0.25


@pytest.mark.parametrize("cost", [0.01, float("nan"), -1])
def test_databento_zero_budget_prevents_stream(cost):
    client, calls = databento_client(cost=cost)
    with pytest.raises(ProviderError):
        DatabentoEquityProvider(client=client).fetch(request())
    assert calls == []


def test_databento_coverage_and_identifier_ambiguity_fail_closed():
    client, calls = databento_client(start="2023-01-01T00:00:00+00:00")
    with pytest.raises(ProviderError, match="coverage"):
        DatabentoEquityProvider(client=client).fetch(request())
    assert calls == []
    client, _ = databento_client(instrument_ids=(1, 2))
    with pytest.raises(ProviderError, match="multiple IDs"):
        DatabentoEquityProvider(client=client).fetch(request())


def test_missing_credentials_and_status_never_return_values(monkeypatch):
    for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "DATABENTO_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for provider in (AlpacaHistoricalProvider(), DatabentoEquityProvider()):
        with pytest.raises(ProviderError, match="server secrets"):
            provider.fetch(request())
    assert not any(p["configured"] for p in provider_status()["items"])
    monkeypatch.setenv("DATABENTO_API_KEY", "never-expose-me")
    assert "never-expose-me" not in json.dumps(provider_status())


def test_dashboard_rejects_stooq_and_unbounded_databento():
    payload = {"symbols": ["AAPL"], "start": "2018-01-02", "end": "2018-12-31", "confirmed": True}
    assert DownloadRequest.model_validate(payload).provider == "alpaca"
    with pytest.raises(ValueError, match="31 calendar days"):
        DownloadRequest.model_validate({**payload, "provider": "databento"})
    with pytest.raises(ValueError):
        DownloadRequest.model_validate({**payload, "provider": "stooq"})
