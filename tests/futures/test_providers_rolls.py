import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pandas as pd
import polars as pl
import pytest

from quantlab.data.providers.base import ProviderError, ProviderNetworkError
from quantlab.futures.continuous import continuous_series, select_contract
from quantlab.futures.providers import DatabentoProvider, FuturesRequest, LeanFuturesProvider


def test_lean_actual_contract_member_and_utc_mapping(contract):
    c = replace(
        contract,
        year=2013,
        month=12,
        identifier="ESZ13",
        last_trade=datetime(2013, 12, 20, 14, 30, tzinfo=UTC),
        expiration=datetime(2013, 12, 20, 14, 30, tzinfo=UTC),
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr(
            "20131008_es_minute_trade_201312.csv", "48600000,1667.5,1667.75,1667.25,1667.5,48\n"
        )

    def respond(request):
        assert request.url.path.endswith("/es/20131008_trade.zip")
        return httpx.Response(200, content=payload.getvalue())

    req = FuturesRequest(
        c, datetime(2013, 10, 8, 13, 30, tzinfo=UTC), datetime(2013, 10, 8, 20, tzinfo=UTC)
    )
    provider = LeanFuturesProvider(transport=httpx.MockTransport(respond))
    result = provider.fetch(req)
    assert b"2013-10-08T13:30:00+00:00,1667.5" in result.raw
    assert b"ESZ13" in result.raw and not result.synthetic
    assert provider.source_hashes

    def fail(request):
        raise httpx.ProxyError("403 Forbidden")

    with pytest.raises(ProviderNetworkError):
        LeanFuturesProvider(transport=httpx.MockTransport(fail)).fetch(req)


def test_databento_cost_gate_and_raw_symbol(contract):
    c = replace(contract, provider_symbols={"databento": "ESM4"})
    req = FuturesRequest(
        c, datetime(2024, 6, 20, 13, 30, tzinfo=UTC), datetime(2024, 6, 20, 14, tzinfo=UTC)
    )
    calls = []
    df = pd.DataFrame(
        {"open": [100.0], "high": [100.25], "low": [99.75], "close": [100.0], "volume": [1000]},
        index=pd.DatetimeIndex(["2024-06-20T13:30:00Z"]),
    )

    def get(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(to_df=lambda: df)

    client = SimpleNamespace(
        metadata=SimpleNamespace(get_cost=lambda **kwargs: 1.0),
        timeseries=SimpleNamespace(get_range=get),
    )
    with pytest.raises(ProviderError, match="exceeds"):
        DatabentoProvider(client=client).fetch(req)
    assert calls == []
    result = DatabentoProvider(client=client, maximum_download_cost=1).fetch(req)
    assert calls[0]["symbols"] == ["ESM4"] and calls[0]["schema"] == "ohlcv-1m"
    assert result.synthetic is False
    with pytest.raises(ValueError):
        DatabentoProvider(maximum_download_cost=float("nan"))


def test_no_databento_credentials_means_no_request(contract, monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    req = FuturesRequest(
        contract, datetime(2024, 6, 20, 13, 30, tzinfo=UTC), datetime(2024, 6, 20, 14, tzinfo=UTC)
    )
    with pytest.raises(ProviderError, match="not configured"):
        DatabentoProvider().fetch(req)


def test_causal_forward_roll_and_nontradable_back_adjustment(contract):
    back = replace(
        contract,
        identifier="ESU24",
        month=9,
        expiration=datetime(2024, 9, 20, 13, 30, tzinfo=UTC),
        last_trade=datetime(2024, 9, 20, 13, 30, tzinfo=UTC),
    )
    contracts = {contract.identifier: contract, back.identifier: back}
    rows = []
    for day in (13, 17):
        t = datetime(2024, 6, day, 13, 30, tzinfo=UTC)
        for c, price in ((contract, 100), (back, 110)):
            rows.append(
                {
                    "timestamp": t,
                    "available_at": t + timedelta(minutes=1),
                    "session_date": t.date(),
                    "contract": c.identifier,
                    "open": price,
                    "high": price + 0.25,
                    "low": price - 0.25,
                    "close": price,
                    "volume": 100,
                }
            )
    frame = pl.DataFrame(rows)
    series, meta = continuous_series(frame, contracts, roll_days=5, back_adjust=True)
    assert len(meta["rolls"]) == 1 and meta["rolls"][0]["gap"] == 10
    assert series["close"].to_list() == [110, 110]
    assert meta["tradable"] is False and meta["feature_safe"] is False
    as_of = frame["timestamp"][0] + timedelta(minutes=2)
    changed = frame.with_columns(
        pl.when(pl.col("timestamp") > as_of)
        .then(pl.lit(1000000))
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    assert select_contract(
        frame, contracts, as_of, method="volume", roll_days=0
    ) == select_contract(changed, contracts, as_of, method="volume", roll_days=0)
