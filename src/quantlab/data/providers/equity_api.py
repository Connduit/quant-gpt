"""Read-only raw equity data; regular-session aggregation, no broker endpoints."""

import csv
import hashlib
import io
import json
import math
import os
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import httpx

from quantlab.data.providers.base import (
    Download,
    ProviderError,
    ProviderHTTPError,
    ProviderNetworkError,
)


def session_csv(records, request):
    """Aggregate unadjusted minute bars over XNYS regular hours, including half days."""
    calendar = xcals.get_calendar(
        "XNYS", start=request.start - timedelta(days=7), end=request.end + timedelta(days=7)
    )
    bounds = {
        s.date(): (
            calendar.session_open(s).to_pydatetime(),
            calendar.session_close(s).to_pydatetime(),
        )
        for s in calendar.sessions_in_range(str(request.start), str(request.end))
    }
    grouped, seen = {}, set()
    for stamp, values in records:
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ProviderError("Provider timestamps must be timezone aware")
        day = stamp.astimezone(ZoneInfo("America/New_York")).date()
        if not request.start <= day <= request.end:
            raise ProviderError("Provider returned dates outside the bounded request")
        if stamp in seen:
            raise ProviderError("Duplicate provider minute timestamps")
        seen.add(stamp)
        if day not in bounds or not bounds[day][0] <= stamp < bounds[day][1]:
            continue
        if len(values) != 5 or any(not math.isfinite(float(v)) for v in values):
            raise ProviderError("Malformed provider minute OHLCV")
        o, h, low, c, volume = map(float, values)
        if (
            min(o, h, low, c) <= 0
            or h < max(o, low, c)
            or low > min(o, h, c)
            or volume < 0
            or not volume.is_integer()
        ):
            raise ProviderError("Invalid provider minute OHLCV")
        grouped.setdefault(day, []).append((stamp, (o, h, low, c, int(volume))))
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
    for day, bars in sorted(grouped.items()):
        bars.sort(key=lambda b: b[0])
        writer.writerow(
            [
                day,
                bars[0][1][0],
                max(b[1][1] for b in bars),
                min(b[1][2] for b in bars),
                bars[-1][1][3],
                sum(b[1][4] for b in bars),
            ]
        )
    if not grouped:
        raise ProviderError("Provider supplied no regular-session bars for this range")
    return output.getvalue().encode()


class AlpacaHistoricalProvider:
    def __init__(self, *, feed="sip", transport=None, timeout=30):
        if feed not in ("sip", "iex"):
            raise ValueError("Alpaca feed must be sip or iex")
        self.feed, self.transport, self.timeout = feed, transport, timeout
        self.name = f"alpaca-{feed}-raw-rth-minute-asof-end-v2"

    def fetch(self, request):
        key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise ProviderError("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in server secrets")
        local = ZoneInfo("America/New_York")
        params = {
            "start": datetime.combine(request.start, time(), local).isoformat(),
            "end": datetime.combine(request.end, time(23, 59, 59), local).isoformat(),
            "timeframe": "1Min",
            "adjustment": "raw",
            "asof": str(request.end),
            "feed": self.feed,
            "sort": "asc",
            "limit": 10000,
        }
        url = f"https://data.alpaca.markets/v2/stocks/{request.symbol}/bars"
        records, tokens, hashes = [], set(), []
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                for _ in range(2000):
                    response = client.get(
                        url,
                        params=params,
                        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                    )
                    if response.status_code != 200:
                        raise ProviderHTTPError(
                            f"Alpaca HTTP {response.status_code}; check credentials and entitlement"
                            " and rate limits; no feed fallback or automatic retry"
                        )
                    hashes.append(hashlib.sha256(response.content).hexdigest())
                    document = response.json()
                    if document.get("symbol", request.symbol) != request.symbol:
                        raise ProviderError("Alpaca returned a different symbol")
                    bars = document.get("bars")
                    if not isinstance(bars, list):
                        raise ProviderError("Alpaca response lacks a bars array")
                    for bar in bars:
                        records.append(
                            (
                                datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                                [bar[k] for k in ("o", "h", "l", "c", "v")],
                            )
                        )
                    token = document.get("next_page_token")
                    if not token:
                        break
                    if not isinstance(token, str) or token in tokens:
                        raise ProviderError("Alpaca pagination repeated or invalid token")
                    tokens.add(token)
                    params["page_token"] = token
                else:
                    raise ProviderError("Alpaca pagination budget exhausted")
        except httpx.RequestError as exc:
            raise ProviderNetworkError(f"Alpaca transport failure ({type(exc).__name__})") from None
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("Malformed Alpaca historical response") from None
        return Download(
            session_csv(records, request),
            json.dumps(
                {
                    "url": url,
                    "feed": self.feed,
                    "adjustment": "raw",
                    "asof": str(request.end),
                    "schema": "1Min",
                    "aggregation": "XNYS regular-session first/max/min/last/sum v1",
                    "response_sha256": hashes,
                }
            ),
            "unadjusted",
            False,
        )


class DatabentoEquityProvider:
    def __init__(self, *, dataset="XNAS.ITCH", maximum_download_cost=0, client=None):
        if dataset not in ("XNAS.ITCH", "DBEQ.BASIC"):
            raise ValueError("Unsupported Databento equity dataset")
        if not math.isfinite(maximum_download_cost) or not 0 <= maximum_download_cost <= 100:
            raise ValueError("Databento budget must be between 0 and 100 USD")
        self.dataset, self.remaining = dataset, maximum_download_cost
        self.client = client
        self.name = f"databento-{dataset.lower()}-raw-rth-minute-v1"
        self.quoted_cost = 0.0

    def fetch(self, request):
        if (request.end - request.start).days > 30:
            raise ProviderError(
                "Databento equity downloads are limited to 31 calendar days per job"
            )
        if self.client is None:
            if not os.getenv("DATABENTO_API_KEY"):
                raise ProviderError("Set DATABENTO_API_KEY in server secrets; no data requested")
            try:
                import databento as db
            except ImportError:
                raise ProviderError("Install the market-data extra for Databento") from None
            try:
                self.client = db.Historical(os.environ["DATABENTO_API_KEY"])
            except Exception:
                raise ProviderError(
                    "Databento client configuration failed; check server secret"
                ) from None
        local = ZoneInfo("America/New_York")
        params = {
            "dataset": self.dataset,
            "schema": "ohlcv-1m",
            "symbols": [request.symbol],
            "stype_in": "raw_symbol",
            "start": datetime.combine(request.start, time(), local).astimezone(UTC),
            "end": datetime.combine(request.end + timedelta(days=1), time(), local).astimezone(UTC),
        }
        try:
            available = self.client.metadata.get_dataset_range(dataset=self.dataset)
            available = available.get("schema", {}).get("ohlcv-1m", available)
            start = datetime.fromisoformat(available["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(available["end"].replace("Z", "+00:00"))
            if start > params["start"] or end < params["end"]:
                raise ProviderError("Requested dates are outside Databento dataset coverage")
            quote = float(self.client.metadata.get_cost(**params))
            if not math.isfinite(quote) or quote < 0:
                raise ProviderError("Databento returned an invalid cost estimate")
            if quote > self.remaining:
                raise ProviderError(
                    f"Databento estimate ${quote:.6f} exceeds remaining authorized "
                    f"budget ${self.remaining:.6f}; no data requested"
                )
            # Reserve the estimate even if the billed stream subsequently fails.
            self.remaining -= quote
            self.quoted_cost += quote
            frame = self.client.timeseries.get_range(**params).to_df(price_type="float")
            if "instrument_id" not in frame or frame["instrument_id"].nunique() != 1:
                raise ProviderError("Databento symbol resolution is empty or spans multiple IDs")
            records = [
                (
                    stamp.to_pydatetime(),
                    [row[k] for k in ("open", "high", "low", "close", "volume")],
                )
                for stamp, row in frame.iterrows()
            ]
            raw = session_csv(records, request)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Databento historical failure ({type(exc).__name__}); "
                "check network, entitlement and SDK; no automatic retry"
            ) from None
        return Download(
            raw,
            json.dumps(
                {
                    "host": "hist.databento.com",
                    "dataset": self.dataset,
                    "schema": "ohlcv-1m",
                    "stype_in": "raw_symbol",
                    "symbol": request.symbol,
                    "start": params["start"].isoformat(),
                    "end": params["end"].isoformat(),
                    "estimated_cost_usd": quote,
                    "aggregation": "XNYS regular-session first/max/min/last/sum v1",
                    "coverage": "dataset venues only; not assumed consolidated SIP",
                }
            ),
            "unadjusted",
            False,
        )
