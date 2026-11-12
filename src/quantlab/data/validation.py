"""Strict daily OHLCV validation. Reject bad data instead of silently filling it."""

from datetime import date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import polars as pl

from quantlab.data.providers.base import DataRequest


class ValidationError(ValueError):
    pass


def normalize_daily(raw: bytes, request: DataRequest) -> pl.DataFrame:
    try:
        frame = (
            pl.read_csv(
                BytesIO(raw),
                schema_overrides={
                    "Date": pl.String,
                    "Open": pl.Float64,
                    "High": pl.Float64,
                    "Low": pl.Float64,
                    "Close": pl.Float64,
                    "Volume": pl.Int64,
                },
            )
            .rename(
                {
                    "Date": "session_date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            .select("session_date", "open", "high", "low", "close", "volume")
        )
        frame = frame.with_columns(pl.col("session_date").str.to_date("%Y-%m-%d"))
    except (pl.exceptions.PolarsError, UnicodeError) as exc:
        raise ValidationError("Malformed OHLCV CSV or missing required columns") from exc
    if frame.is_empty() or frame.null_count().row(0) != (0,) * 6:
        raise ValidationError("Data is empty or contains missing values")
    if frame["session_date"].n_unique() != frame.height:
        raise ValidationError("Duplicate sessions are not allowed")
    numeric = ["open", "high", "low", "close", "volume"]
    if frame.select(pl.any_horizontal([~pl.col(c).is_finite() for c in numeric]).any()).item():
        raise ValidationError("OHLCV contains nonfinite numbers")
    invalid = (
        (pl.min_horizontal("open", "high", "low", "close") <= 0)
        | (pl.col("volume") < 0)
        | (pl.col("volume") != pl.col("volume").floor())
        | (pl.col("high") < pl.max_horizontal("open", "low", "close"))
        | (pl.col("low") > pl.min_horizontal("open", "high", "close"))
    )
    if frame.filter(invalid).height:
        raise ValidationError("Invalid OHLC price relationships, prices or volume")
    frame = frame.filter(pl.col("session_date").is_between(request.start, request.end)).sort(
        "session_date"
    )
    if frame.is_empty():
        raise ValidationError("No data within requested dates")
    try:
        calendar = xcals.get_calendar(
            "XNYS", start=request.start - timedelta(days=7), end=request.end + timedelta(days=7)
        )
        sessions = calendar.sessions_in_range(str(request.start), str(request.end))
        closes = {s.date(): calendar.session_close(s).to_pydatetime() for s in sessions}
    except (ValueError, OverflowError) as exc:
        raise ValidationError("Requested dates are outside supported XNYS calendar range") from exc
    dates: list[date] = frame["session_date"].to_list()
    if any(day not in closes for day in dates):
        raise ValidationError("Daily bars include a non-XNYS trading session")
    missing = sorted(set(closes) - set(dates))
    if missing:
        raise ValidationError(f"Missing XNYS sessions: {', '.join(map(str, missing[:10]))}")
    timestamps = [closes[day] for day in dates]
    return frame.with_columns(
        pl.lit(request.symbol).alias("symbol"),
        pl.Series("timestamp", timestamps, dtype=pl.Datetime("us", "UTC")),
        # Availability is deliberately a conservative bound, not historical vendor knowledge.
        pl.Series(
            "available_at",
            [
                datetime.combine(
                    day + timedelta(days=1),
                    time(),
                    tzinfo=ZoneInfo("America/New_York"),
                )
                for day in dates
            ],
            dtype=pl.Datetime("us", "UTC"),
        ),
        pl.lit("America/New_York").alias("exchange_timezone"),
    )
