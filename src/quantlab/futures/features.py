"""Causal minute features; no finished-session statistics before they are observed."""

import math
import statistics
from datetime import timedelta
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

CT = ZoneInfo("America/Chicago")
FEATURE_GROUPS = {
    "momentum": (
        "return_1m",
        "return_5m",
        "return_15m",
        "intraday_momentum",
        "distance_session_open",
        "volume_weighted_momentum",
    ),
    "volatility": (
        "realized_volatility",
        "rolling_range",
        "atr",
        "volatility_expansion",
        "volatility_regime",
    ),
    "volume": ("relative_volume", "volume_spike", "vwap_deviation", "volume_acceleration"),
    "context": (
        "time_sin",
        "time_cos",
        "session_type",
        "overnight_return_so_far",
        "previous_session_return",
        "distance_previous_high",
        "distance_previous_low",
        "market_trend",
    ),
    "opening_range": ("opening_range_width", "breakout_strength", "opening_range_ready"),
}


def intraday_features(frame, *, opening_range_minutes=30, annual_minutes_per_session=390):
    if not 1 <= opening_range_minutes <= 120:
        raise ValueError("Bound opening range to 1–120 minutes")
    result = []
    for identifier in frame["contract"].unique(maintain_order=True):
        rows = frame.filter(pl.col("contract") == identifier).sort("timestamp").to_dicts()
        current = []
        all_history = []
        session = None
        previous = None
        past_volume = {}
        for row in rows:
            if row["session_date"] != session:
                if current:
                    previous = {
                        "high": max(r["high"] for r in current),
                        "low": min(r["low"] for r in current),
                        "open": current[0]["open"],
                        "close": current[-1]["close"],
                    }
                    for r in current:
                        local = r["timestamp"].astimezone(CT)
                        minute = local.hour * 60 + local.minute
                        past_volume.setdefault(minute, []).append(r["volume"])
                current = []
                session = row["session_date"]
            current.append(row)
            all_history.append(row)
            history = current
            start = len(history) - 1
            while start > 0 and history[start]["timestamp"] - history[start - 1][
                "timestamp"
            ] == timedelta(minutes=1):
                start -= 1
            history = history[start:]
            close = float(row["close"])
            closes = [float(r["close"]) for r in history]
            returns = np.diff(np.log(closes)) if len(closes) > 1 else np.array([])
            values = {}
            for length in (1, 5, 15):
                values[f"return_{length}m"] = (
                    close / closes[-length - 1] - 1 if len(closes) > length else None
                )
            values["distance_session_open"] = close / float(current[0]["open"]) - 1
            values["intraday_momentum"] = values["distance_session_open"]
            values["realized_volatility_per_minute"] = (
                float(np.std(returns[-30:], ddof=1)) if len(returns) >= 15 else None
            )
            values["realized_volatility"] = (
                float(np.std(returns[-30:], ddof=1) * math.sqrt(252 * annual_minutes_per_session))
                if len(returns) >= 15
                else None
            )
            values["rolling_range"] = (
                float(max(r["high"] for r in history[-15:]) - min(r["low"] for r in history[-15:]))
                if len(history) >= 15
                else None
            )
            tr = (
                [
                    max(
                        float(b["high"] - b["low"]),
                        abs(float(b["high"]) - float(a["close"])),
                        abs(float(b["low"]) - float(a["close"])),
                    )
                    for a, b in zip(history[-16:], history[-15:], strict=False)
                ]
                if len(history) >= 16
                else []
            )
            values["atr"] = statistics.mean(tr) if tr else None
            short = float(np.std(returns[-5:], ddof=1)) if len(returns) >= 5 else None
            long = float(np.std(returns[-30:], ddof=1)) if len(returns) >= 15 else None
            values["volatility_expansion"] = (
                short / long if short is not None and long and long > 0 else None
            )
            values["volatility_regime"] = (
                int(values["realized_volatility"] > 0.2)
                if values["realized_volatility"] is not None
                else None
            )
            volume = sum(float(r["volume"]) for r in current)
            # Typical-price bar proxy unless authoritative per-bar trade VWAP is supplied.
            vwap = (
                sum(
                    float(r.get("trade_vwap") or (r["high"] + r["low"] + r["close"]) / 3)
                    * float(r["volume"])
                    for r in current
                )
                / volume
                if volume
                else None
            )
            values["vwap_deviation"] = close / vwap - 1 if vwap else None
            local = row["timestamp"].astimezone(CT)
            minute = local.hour * 60 + local.minute
            typical = past_volume.get(minute, [])[-20:]
            baseline = (
                statistics.mean(typical)
                if typical
                else statistics.mean(float(r["volume"]) for r in history[-21:-1])
                if len(history) > 1
                else None
            )
            values["relative_volume"] = (
                float(row["volume"]) / baseline if baseline and baseline > 0 else None
            )
            values["volume_spike"] = (
                int(values["relative_volume"] > 2)
                if values["relative_volume"] is not None
                else None
            )
            values["volume_acceleration"] = (
                float(row["volume"]) / max(float(history[-2]["volume"]), 1) - 1
                if len(history) > 1
                else None
            )
            values["volume_weighted_momentum"] = sum(
                float(r["close"] / r["open"] - 1) * float(r["volume"]) for r in history[-15:]
            ) / max(sum(float(r["volume"]) for r in history[-15:]), 1)
            values["time_sin"] = math.sin(2 * math.pi * minute / 1440)
            values["time_cos"] = math.cos(2 * math.pi * minute / 1440)
            values["session_type"] = int(local.date() == session and 510 <= minute < 900)
            rth = [
                r
                for r in current
                if r["timestamp"].astimezone(CT).date() == session
                and 510
                <= r["timestamp"].astimezone(CT).hour * 60 + r["timestamp"].astimezone(CT).minute
                < 510 + opening_range_minutes
            ]
            ready = (
                len(rth) == opening_range_minutes
                and local.date() == session
                and minute >= 510 + opening_range_minutes
            )
            values["opening_range_ready"] = int(ready)
            hi = max(float(r["high"]) for r in rth) if rth else None
            lo = min(float(r["low"]) for r in rth) if rth else None
            values["opening_range_width"] = (hi - lo) / float(current[0]["open"]) if ready else None
            values["breakout_strength"] = (
                (close - hi) / max(hi - lo, 0.25)
                if ready and close > hi
                else (close - lo) / max(hi - lo, 0.25)
                if ready and close < lo
                else 0.0
                if ready
                else None
            )
            values["overnight_return_so_far"] = (
                float((rth[0]["open"] if rth else row["close"]) / previous["close"] - 1)
                if previous
                else None
            )
            values["previous_session_return"] = (
                float(previous["close"] / previous["open"] - 1) if previous else None
            )
            values["distance_previous_high"] = (
                close / float(previous["high"]) - 1 if previous else None
            )
            values["distance_previous_low"] = (
                close / float(previous["low"]) - 1 if previous else None
            )
            values["market_trend"] = (
                float(np.mean(closes[-5:]) / np.mean(closes[-30:]) - 1)
                if len(closes) >= 30
                else None
            )
            result.append(
                {**row, **values, "vwap_proxy": vwap, "feature_available_at": row["available_at"]}
            )
    output = pl.DataFrame(result, infer_schema_length=None).sort("available_at", "contract")
    # Relative strength only when both products have synchronized known observations.
    if {"ES", "NQ"} <= set(frame["symbol"].unique()):
        es = (
            output.filter(pl.col("symbol") == "ES")
            .sort(["available_at", "volume", "contract"], descending=[False, True, False])
            .unique("available_at", keep="first")
            .select("available_at", pl.col("return_5m").alias("es_return"))
        )
        nq = (
            output.filter(pl.col("symbol") == "NQ")
            .sort(["available_at", "volume", "contract"], descending=[False, True, False])
            .unique("available_at", keep="first")
            .select("available_at", pl.col("return_5m").alias("nq_return"))
        )
        joined = es.join(nq, on="available_at", how="inner").unique("available_at")
        output = output.join(joined, on="available_at", how="left").with_columns(
            (pl.col("es_return") - pl.col("nq_return")).alias("es_nq_relative_strength")
        )
    return output


def build_futures_dataset(
    frame,
    *,
    holdout_start,
    horizon=5,
    groups=("momentum", "volatility", "volume"),
    target="forward_return",
    precomputed_features=None,
):
    if type(horizon) is not int or horizon not in (5, 15, 60):
        raise ValueError("Use 5/15/60-minute horizons")
    if any(g not in FEATURE_GROUPS for g in groups) or not groups:
        raise ValueError("Unknown future feature groups")
    if target not in (
        "forward_return",
        "direction",
        "volatility_adjusted",
        "breakout_continuation",
    ):
        raise ValueError("Unknown future target")
    if frame["available_at"].max() >= holdout_start:
        raise ValueError("Futures input must physically exclude the protected holdout")
    features = intraday_features(frame) if precomputed_features is None else precomputed_features
    if features["available_at"].max() >= holdout_start:
        raise ValueError("Feature cache includes protected timestamps")
    names = tuple(dict.fromkeys(n for group in groups for n in FEATURE_GROUPS[group]))
    result = []
    for identifier in features["contract"].unique():
        rows = features.filter(pl.col("contract") == identifier).sort("timestamp").to_dicts()
        for i, row in enumerate(rows):
            entry_index = i + 2
            exit_index = entry_index + horizon
            if exit_index >= len(rows):
                continue
            entry, exit_row = rows[entry_index], rows[exit_index]
            if (
                entry["session_date"] != row["session_date"]
                or exit_row["session_date"] != row["session_date"]
            ):
                continue
            if any(
                rows[j + 1]["timestamp"] - rows[j]["timestamp"] != timedelta(minutes=1)
                for j in range(i, exit_index)
            ):
                continue
            if any(row[n] is None or not math.isfinite(float(row[n])) for n in names):
                continue
            y = float(exit_row["open"] / entry["open"] - 1)
            label = int(y > 0)
            if target == "volatility_adjusted":
                vol = row["realized_volatility_per_minute"]
                if not vol:
                    continue
                y /= max(vol, 1e-8)
            if target == "breakout_continuation":
                strength = row["breakout_strength"]
                if strength is None or not strength:
                    continue
                label = int((y > 0) == (strength > 0))
            result.append(
                {
                    **{n: row[n] for n in names},
                    "contract": identifier,
                    "symbol": row["symbol"],
                    "session_date": row["session_date"],
                    "prediction_at": row["available_at"],
                    "execution_at": entry["timestamp"],
                    "label_end_at": exit_row["timestamp"],
                    "label_known_at": exit_row["available_at"],
                    "feature_available_at": row["feature_available_at"],
                    "target": y,
                    "target_class": label,
                }
            )
    if not result:
        raise ValueError("No mature contiguous pre-holdout futures labels")
    return (
        pl.DataFrame(result, infer_schema_length=None).sort("prediction_at", "contract"),
        names,
        features,
    )


def futures_folds(
    frame,
    *,
    training_sessions=1,
    validation_sessions=1,
    test_sessions=1,
    expanding=True,
    embargo_minutes=5,
    gap_minutes=1,
    minute_grid=None,
):
    if (
        min(training_sessions, validation_sessions, test_sessions) < 1
        or min(embargo_minutes, gap_minutes) < 0
    ):
        raise ValueError("Invalid futures split bounds")
    from quantlab.statistical.splits import validate_intervals

    validate_intervals(frame, observation_key=("contract", "prediction_at"))
    if not frame.select((pl.col("feature_available_at") <= pl.col("prediction_at")).all()).item():
        raise ValueError("Unavailable intraday feature reached a prediction")
    days = sorted(frame["session_date"].unique().to_list())
    for start in range(training_sessions + validation_sessions, len(days), test_sessions):
        val_start = start - validation_sessions
        train_start = 0 if expanding else val_start - training_sessions
        raw_train = frame.filter(pl.col("session_date").is_in(days[train_start:val_start]))
        raw_val = frame.filter(pl.col("session_date").is_in(days[val_start:start]))
        test = frame.filter(pl.col("session_date").is_in(days[start : start + test_sessions]))
        if raw_train.is_empty() or raw_val.is_empty() or test.is_empty():
            continue

        # Minute embargo uses the actually observed minute grid, not calendar days.
        def cutoff(next_frame):
            stamp = next_frame["prediction_at"].min()
            eligible = sorted(
                t
                for t in (
                    minute_grid
                    if minute_grid is not None
                    else frame["prediction_at"].unique().to_list()
                )
                if t < stamp
            )
            count = embargo_minutes + gap_minutes
            return eligible[-count] if count and len(eligible) >= count else stamp

        val_cut = cutoff(raw_val)
        test_cut = cutoff(test)
        train = raw_train.filter(
            (pl.col("label_known_at") < val_cut)
            & (pl.col("feature_available_at") <= pl.col("prediction_at"))
        )
        validation = raw_val.filter(pl.col("label_known_at") < test_cut)
        if train.height < 3 or validation.is_empty():
            raise ValueError("Purging leaves insufficient futures samples")
        yield {
            "train": train,
            "validation": validation,
            "test": test,
            "fitted_at": val_cut,
            "purged_train": raw_train.height - train.height,
            "purged_validation": raw_val.height - validation.height,
        }
