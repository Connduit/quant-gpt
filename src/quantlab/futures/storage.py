"""Immutable futures-minute Parquet snapshots with safe DuckDB query compatibility."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import polars as pl

from quantlab.backtesting.report import dumps
from quantlab.data.storage import SnapshotStore
from quantlab.futures.calendar import FuturesCalendar, calendar_definition


def normalize(raw, contract, *, calendar=None, allow_sparse=False, minutes=1, request=None):
    calendar = calendar or FuturesCalendar()
    try:
        frame = pl.read_csv(raw, try_parse_dates=True, infer_schema_length=None)
    except Exception as exc:
        raise ValueError("Invalid futures CSV") from exc
    required = {"timestamp", "open", "high", "low", "close", "volume", "contract"}
    allowed = required | {
        "bid_open",
        "ask_open",
        "bid",
        "ask",
        "open_interest",
        "settlement_price",
        "settlement_known_at",
        "trade_vwap",
    }
    if set(frame.columns) - allowed:
        raise ValueError(
            "Unknown futures source fields; future labels cannot enter market observations"
        )
    if required - set(frame.columns) or frame.is_empty():
        raise ValueError("Missing futures OHLCV/contract fields")
    if frame["timestamp"].dtype == pl.String:
        frame = frame.with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC"))
    if (
        not isinstance(frame["timestamp"].dtype, pl.Datetime)
        or frame["timestamp"].dtype.time_zone is None
    ):
        raise ValueError("UTC-aware timestamps required")
    frame = frame.with_columns(pl.col("timestamp").dt.convert_time_zone("UTC")).sort("timestamp")
    if frame.select(pl.col("timestamp").is_duplicated().any()).item():
        raise ValueError("Duplicate contract bars")
    if frame["contract"].unique().to_list() != [contract.identifier]:
        raise ValueError("Wrong contract mapping")
    if any(frame[c].null_count() for c in required):
        raise ValueError("Null market observation")
    sessions = []
    for row in frame.iter_rows(named=True):
        t = row["timestamp"]
        if t >= contract.last_trade:
            raise ValueError("Observation after last trading time")
        if t.second or t.microsecond or t.minute % minutes:
            raise ValueError("Bar alignment error")
        session = calendar.session(t)
        if session is None:
            raise ValueError("Observation outside configured trading session")
        prices = [contract.validate_price(row[k]) for k in ("open", "high", "low", "close")]
        if (
            prices[1] < max(prices[0], prices[3])
            or prices[2] > min(prices[0], prices[3])
            or prices[2] > prices[1]
        ):
            raise ValueError("Inconsistent futures OHLC")
        v = row["volume"]
        if type(v) is bool or v < 0 or int(v) != v:
            raise ValueError("Invalid contract volume")
        for bid, ask in (("bid_open", "ask_open"), ("bid", "ask")):
            if bid in row and ask in row and row[bid] is not None and row[ask] is not None:
                if contract.validate_price(row[bid]) > contract.validate_price(row[ask]):
                    raise ValueError("Crossed futures quotes")
        if row.get("open_interest") is not None and row["open_interest"] < 0:
            raise ValueError("Negative open interest")
        sessions.append(session)
    frame = frame.with_columns(
        pl.Series("session_date", sessions),
        pl.lit(contract.product).alias("symbol"),
        (pl.col("timestamp") + pl.duration(minutes=minutes)).alias("available_at"),
    )
    missing = {}
    from datetime import timedelta

    if request is not None:
        if frame["timestamp"].min() < request.start or frame["available_at"].max() > request.end:
            raise ValueError("Market bars are outside requested completed-minute interval")
        first_day = request.start.astimezone(calendar.calendar.tz).date() - timedelta(days=1)
        last_day = request.end.astimezone(calendar.calendar.tz).date() + timedelta(days=1)
    else:
        first_day, last_day = min(sessions), max(sessions)
    day = first_day
    while day <= last_day:
        expected = {
            t
            for t in calendar.expected(day, minutes)
            if t < contract.last_trade
            and (
                request is None
                or request.start <= t
                and t + timedelta(minutes=minutes) <= request.end
            )
        }
        actual = set(frame.filter(pl.col("session_date") == day)["timestamp"].to_list())
        absent = expected - actual
        if absent:
            missing[str(day)] = len(absent)
        day += timedelta(days=1)
    frame = frame.with_columns(pl.col("volume").cast(pl.Int64))
    if missing and not allow_sparse:
        raise ValueError(f"Missing minute bars: {missing}; explicit sparse policy required")
    return frame, {
        "missing_minutes": missing,
        "sparse_policy": "explicit no-trade/missing gaps; never fill bars"
        if allow_sparse
        else "complete configured sessions",
        "calendar_source": calendar.overrides_source,
        "calendar_definition": calendar_definition(calendar),
        "session_mode": calendar.mode,
        "minutes": minutes,
        "coverage_scope": "full configured sessions between observed endpoints"
        if request is None
        else "requested completed-minute interval; partial sessions allowed",
        "requested_start": request.start.isoformat() if request is not None else None,
        "requested_end": request.end.isoformat() if request is not None else None,
    }


class FuturesStore:
    def __init__(self, root):
        self.root = Path(root)

    def write(self, frame, raw, contract, *, provider, source, synthetic, quality):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".pending-futures-", dir=self.root))
        try:
            frame.write_parquet(temporary / "bars.parquet")
            (temporary / "source.csv").write_bytes(raw)
            metadata = {
                "asset_class": "futures",
                "provider": provider,
                "source": source,
                "synthetic": synthetic,
                "price_basis": "actual_contract_unadjusted",
                "tradable": True,
                "contract": contract.as_dict(),
                "quality": quality,
                "row_count": frame.height,
                "start": str(frame["timestamp"].min()),
                "end": str(frame["timestamp"].max()),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "parquet_sha256": hashlib.sha256(
                    (temporary / "bars.parquet").read_bytes()
                ).hexdigest(),
            }
            serialized = dumps(metadata)
            identifier = hashlib.sha256(serialized.encode()).hexdigest()
            (temporary / "manifest.json").write_text(serialized + "\n")
            if (self.root / identifier).exists():
                self.manifest(identifier)
            else:
                temporary.rename(self.root / identifier)
            return identifier
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def manifest(self, identifier):
        if len(identifier) != 64 or any(c not in "0123456789abcdef" for c in identifier):
            raise ValueError("Invalid snapshot ID")
        path = self.root / identifier
        serialized = (path / "manifest.json").read_text().rstrip("\n")
        if hashlib.sha256(serialized.encode()).hexdigest() != identifier:
            raise ValueError("Futures manifest checksum mismatch")
        metadata = json.loads(serialized)
        for name, key in [("source.csv", "raw_sha256"), ("bars.parquet", "parquet_sha256")]:
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != metadata[key]:
                raise ValueError("Futures artifact checksum mismatch")
        return metadata

    def read(self, identifier):
        self.manifest(identifier)
        return pl.read_parquet(self.root / identifier / "bars.parquet")

    def query(self, identifier, sql):
        # Reuse the same SELECT-only external-access-disabled DuckDB query boundary.
        return SnapshotStore.query(self, identifier, sql)
