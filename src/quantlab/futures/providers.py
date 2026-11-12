"""Interchangeable contract-minute sources; no implicit paid or synthetic fallback."""

import csv
import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from quantlab.data.providers.base import (
    Download,
    ProviderError,
    ProviderHTTPError,
    ProviderNetworkError,
)
from quantlab.futures.calendar import FuturesCalendar

PIN = "655ac6d475ad8539ff54583a26327e63b59c5703"
BASE = f"https://raw.githubusercontent.com/QuantConnect/Lean/{PIN}"


@dataclass(frozen=True)
class FuturesRequest:
    contract: object
    start: datetime
    end: datetime
    minutes: int = 1

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or not self.start < self.end:
            raise ValueError("Aware, ordered half-open request interval required")
        if self.end > datetime.now(UTC) or self.end > self.contract.last_trade:
            raise ValueError("Historical range must precede current time and last trading time")
        if self.start.second or self.start.microsecond or self.end.second or self.end.microsecond:
            raise ValueError("One-minute request boundaries must be aligned")
        if self.minutes != 1:
            raise ValueError(
                "Initial provider supports one-minute bars; aggregate explicitly later"
            )


class LeanFuturesProvider:
    name = "quantconnect-lean-futures-archive"

    def __init__(self, *, transport=None, timeout=30, calendar=None, include_auxiliary=False):
        self.transport = transport
        self.timeout = timeout
        self.calendar = calendar or FuturesCalendar()
        self.include_auxiliary = include_auxiliary
        self.source_hashes = {}
        self.payloads = {}

    def _get(self, url):
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderHTTPError(f"LEAN futures HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ProviderNetworkError(
                f"LEAN futures network failure ({type(exc).__name__})"
            ) from exc
        raw = response.content
        self.source_hashes[url] = hashlib.sha256(raw).hexdigest()
        self.payloads[url] = raw
        return raw

    def fetch(self, request):
        contract = request.contract
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            ["timestamp", "open", "high", "low", "close", "volume", "contract"]
            + (
                ["bid_open", "ask_open", "bid", "ask", "open_interest"]
                if self.include_auxiliary
                else []
            )
        )
        day = request.start.astimezone(UTC).date()
        final = (request.end - timedelta(microseconds=1)).astimezone(UTC).date()
        while day <= final:
            # No weekend/holiday network attempts or hidden no-data substitutions.
            if day not in self.calendar.holidays and self.calendar.calendar.is_session(str(day)):
                code = day.strftime("%Y%m%d")
                product = contract.product.lower()
                url = f"{BASE}/Data/future/cme/minute/{product}/{code}_trade.zip"
                raw = self._get(url)
                quotes = {}
                oi = []
                if self.include_auxiliary:
                    for kind in ("quote", "openinterest"):
                        auxiliary = self._get(url.replace("_trade.zip", f"_{kind}.zip"))
                        name = (
                            f"{code}_{product}_minute_{kind}_"
                            f"{contract.year}{contract.month:02d}.csv"
                        )
                        try:
                            with zipfile.ZipFile(io.BytesIO(auxiliary)) as archive:
                                parsed = list(csv.reader(io.StringIO(archive.read(name).decode())))
                            if kind == "quote":
                                quotes = {int(r[0]): r for r in parsed}
                            else:
                                oi = sorted((int(r[0]), int(r[1])) for r in parsed)
                        except (zipfile.BadZipFile, KeyError, ValueError, UnicodeError) as exc:
                            raise ProviderError("Malformed auxiliary contract archive") from exc
                member = f"{code}_{product}_minute_trade_{contract.year}{contract.month:02d}.csv"
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                        info = archive.getinfo(member)
                        if info.file_size > 100_000_000:
                            raise ValueError("Oversized archive entry")
                        for row in csv.reader(io.StringIO(archive.read(member).decode())):
                            if len(row) != 6:
                                raise ValueError("Malformed minute row")
                            # Pinned market-hours database declares dataTimeZone UTC for CME ES.
                            stamp = datetime.combine(day, datetime.min.time(), UTC) + timedelta(
                                milliseconds=int(row[0])
                            )
                            if (
                                request.start <= stamp < request.end
                                and self.calendar.session(stamp) is not None
                            ):
                                values = [stamp.isoformat(), *row[1:], contract.identifier]
                                if self.include_auxiliary:
                                    quote = quotes.get(int(row[0]))
                                    known = [value for at, value in oi if at <= int(row[0])]
                                    values += (
                                        [quote[1], quote[6], quote[4], quote[9]]
                                        if quote
                                        else [None] * 4
                                    )
                                    values += [known[-1] if known else None]
                                writer.writerow(values)
                except (zipfile.BadZipFile, KeyError, ValueError, UnicodeError) as exc:
                    raise ProviderError(
                        "Malformed or missing actual-contract minute archive"
                    ) from exc
            day += timedelta(days=1)
        return Download(
            output.getvalue().encode(),
            f"{BASE}/Data/future/readme.md; UTC source timestamps; {contract.identifier}",
            "actual_contract_unadjusted",
            False,
        )


class DatabentoProvider:
    """SDK boundary with explicit billable-cost cap; no credentials required by offline tests."""

    name = "databento"

    def __init__(self, *, client=None, maximum_download_cost=0):
        import math

        if not math.isfinite(maximum_download_cost) or maximum_download_cost < 0:
            raise ValueError("Cost cap must be nonnegative")
        self.client = client
        self.maximum_download_cost = maximum_download_cost

    def fetch(self, request):
        client = self.client
        if client is None:
            if not os.getenv("DATABENTO_API_KEY"):
                raise ProviderError("DATABENTO_API_KEY not configured; no paid request made")
            try:
                import databento as db
            except ImportError as exc:
                raise ProviderError("Install futures extra for the Databento SDK") from exc
            client = db.Historical(os.environ["DATABENTO_API_KEY"])
        params = {
            "dataset": "GLBX.MDP3",
            "schema": "ohlcv-1m",
            "symbols": [
                request.contract.provider_symbols.get("databento", request.contract.identifier)
            ],
            "stype_in": "raw_symbol",
            "start": request.start,
            "end": request.end,
        }
        # No silent subscription/usage charge; quote first and compare explicit cap.
        quote = float(client.metadata.get_cost(**params))
        import math

        if not math.isfinite(quote) or quote < 0:
            raise ProviderError("Invalid billable cost quote; no data requested")
        if quote > self.maximum_download_cost:
            raise ProviderError(
                f"Databento quoted cost {quote:.4f} exceeds configured cap; no data requested"
            )
        try:
            frame = client.timeseries.get_range(**params).to_df()
        except Exception as exc:
            raise ProviderError(f"Databento request failed ({type(exc).__name__})") from exc
        required = {"open", "high", "low", "close", "volume"}
        if required - set(frame.columns):
            raise ProviderError("Databento response lacks OHLCV fields")
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "contract"])
        for timestamp, row in frame.iterrows():
            if timestamp.tzinfo is None:
                raise ProviderError("Databento timestamps must be timezone aware")
            writer.writerow(
                [
                    timestamp.isoformat(),
                    *[row[k] for k in ("open", "high", "low", "close", "volume")],
                    request.contract.identifier,
                ]
            )
        return Download(
            output.getvalue().encode(),
            "Databento GLBX.MDP3 raw_symbol ohlcv-1m; quoted billable source",
            "actual_contract_unadjusted",
            False,
        )
