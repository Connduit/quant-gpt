"""A daily-equity adapter: source storage does not know about simulation events."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta

import exchange_calendars as xcals
import polars as pl

from quantlab.backtesting.actions import CorporateActions
from quantlab.backtesting.models import Bar, EquityInstrument, decimal
from quantlab.data.providers.base import DataRequest
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily


@dataclass(frozen=True)
class DailyData:
    instrument: EquityInstrument
    bars: tuple[Bar, ...]
    snapshot_id: str
    manifest: dict
    actions: CorporateActions

    def __post_init__(self) -> None:
        if not self.bars:
            raise ValueError("Daily replay requires at least one bar")
        previous = None
        for bar in self.bars:
            if bar.symbol != self.instrument.symbol:
                raise ValueError("DailyData contains a different instrument")
            timestamps = (bar.open_time, bar.close_time, bar.available_at)
            if any(t.tzinfo is None or t.utcoffset() != timedelta(0) for t in timestamps):
                raise ValueError("Replay timestamps must be UTC")
            if not bar.open_time < bar.close_time <= bar.available_at:
                raise ValueError("Bar availability must be on/after the session close")
            if previous and (
                bar.session_date <= previous.session_date
                or bar.open_time <= previous.close_time
                or bar.available_at < previous.available_at
            ):
                raise ValueError("Replay bars must have chronological sessions and availability")
            prices = (bar.open, bar.high, bar.low, bar.close)
            if (
                any(not p.is_finite() or p <= 0 for p in prices)
                or bar.high < max(prices)
                or bar.low > min(prices)
                or bar.volume < 0
            ):
                raise ValueError("Invalid replay OHLCV")
            previous = bar
        if (
            self.actions.symbol != self.instrument.symbol
            or self.actions.coverage_start > self.bars[0].session_date
            or self.actions.coverage_end < self.bars[-1].session_date
        ):
            raise ValueError("Corporate-action coverage does not match replay data")
        synthetic, basis = self.manifest["synthetic"], self.manifest["price_basis"]
        if not (
            (synthetic is True and basis == "synthetic")
            or (synthetic is False and basis == "unadjusted")
        ):
            raise ValueError("Replay needs synthetic or unadjusted prices")

    @classmethod
    def from_snapshot(
        cls,
        store: SnapshotStore,
        snapshot_id: str,
        actions: CorporateActions | None = None,
        *,
        allow_unverified_actions: bool = False,
    ) -> "DailyData":
        if store.inspect(snapshot_id).get("dataset_role") == "protected_test":
            raise ValueError("Protected test snapshots cannot be opened for routine simulation")
        metadata = store.manifest(snapshot_id)
        frame = store.read(snapshot_id)
        request = metadata["request"]
        from datetime import date

        start, end = date.fromisoformat(request["start"]), date.fromisoformat(request["end"])
        synthetic = metadata["synthetic"] is True
        basis = metadata["price_basis"]
        if not ((synthetic and basis == "synthetic") or (not synthetic and basis == "unadjusted")):
            raise ValueError(
                "Backtesting requires synthetic or explicitly unadjusted prices; "
                "unknown/adjusted vendor prices cannot be execution prices"
            )
        if metadata["calendar"] != "XNYS" or metadata["interval"] != "1d":
            raise ValueError("This adapter supports XNYS daily-equity snapshots only")
        if actions is None:
            if not synthetic:
                raise ValueError("Unadjusted real data requires a complete corporate-action ledger")
            actions = CorporateActions(
                request["symbol"], start, end, "synthetic assumption: no corporate actions"
            )
        if actions.coverage_method == "unverified_events" and not allow_unverified_actions:
            raise ValueError("Unverified actions require explicit exploratory simulation")
        if (
            actions.symbol != request["symbol"]
            or actions.coverage_start > start
            or actions.coverage_end < end
        ):
            raise ValueError("Corporate-action ledger does not cover this symbol and date range")
        # Revalidate the normalized input, including completeness; never trust a file suffix.
        csv = (
            frame.select(
                pl.col("session_date").alias("Date"),
                *[
                    pl.col(name.lower()).alias(name)
                    for name in ("Open", "High", "Low", "Close", "Volume")
                ],
            )
            .write_csv()
            .encode()
        )
        normalized = normalize_daily(csv, DataRequest(request["symbol"], start, end))
        if frame.height != metadata["row_count"] or frame["symbol"].unique().to_list() != [
            request["symbol"]
        ]:
            raise ValueError("Snapshot row count or instrument does not match its manifest")
        if not frame["session_date"].equals(normalized["session_date"]):
            raise ValueError("Snapshot bars must be in chronological session order")
        if not frame["timestamp"].equals(normalized["timestamp"]):
            raise ValueError("Bar timestamps must match XNYS session closes")
        for name in ("timestamp", "available_at"):
            if (
                not isinstance(frame.schema[name], pl.Datetime)
                or frame.schema[name].time_zone != "UTC"
            ):
                raise ValueError("Simulation timestamps must be timezone-aware UTC")
            if frame[name].null_count():
                raise ValueError("Simulation timestamps cannot be missing")
        if (frame["available_at"] < frame["timestamp"]).any():
            raise ValueError("Daily bars cannot be available before their closing timestamp")
        if not frame["available_at"].is_sorted():
            raise ValueError("Out-of-order bar availability requires a revision-aware adapter")
        calendar = xcals.get_calendar(
            "XNYS", start=start - timedelta(days=7), end=end + timedelta(days=7)
        )
        bars = tuple(
            Bar(
                row["symbol"],
                row["session_date"],
                calendar.session_open(str(row["session_date"])).to_pydatetime(),
                row["timestamp"],
                row["available_at"],
                *[decimal(row[name]) for name in ("open", "high", "low", "close")],
                row["volume"],
            )
            for row in frame.iter_rows(named=True)
        )
        return cls(EquityInstrument(request["symbol"]), bars, snapshot_id, metadata, actions)


@dataclass(frozen=True)
class MarketData:
    """Synchronized daily-equity feeds sharing one cash account and session clock."""

    feeds: tuple[DailyData, ...]

    def __post_init__(self) -> None:
        if not self.feeds or len({d.instrument.symbol for d in self.feeds}) != len(self.feeds):
            raise ValueError("MarketData requires nonempty, unique instrument feeds")
        reference = [(b.session_date, b.open_time, b.close_time) for b in self.feeds[0].bars]
        if any(
            [(b.session_date, b.open_time, b.close_time) for b in d.bars] != reference
            for d in self.feeds
        ):
            raise ValueError("MarketData feeds must have identical trading sessions")
        if len({d.manifest["synthetic"] for d in self.feeds}) != 1:
            raise ValueError("Do not mix synthetic and real inputs")

    @property
    def snapshot_id(self) -> str:
        content = "|".join(
            f"{d.instrument.symbol}:{d.snapshot_id}"
            for d in sorted(self.feeds, key=lambda d: d.instrument.symbol)
        )
        return hashlib.sha256(content.encode()).hexdigest()

    @property
    def manifest(self) -> dict:
        return {
            "synthetic": self.feeds[0].manifest["synthetic"],
            "snapshots": {d.instrument.symbol: d.manifest for d in self.feeds},
        }
