from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from quantlab.futures.calendar import FuturesCalendar
from quantlab.futures.features import build_futures_dataset, futures_folds, intraday_features


def history(contract):
    calendar = FuturesCalendar()
    rows = []
    rng = np.random.default_rng(42)
    price = 100.0
    for day in ("2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13", "2024-06-14"):
        for i, t in enumerate(calendar.expected(day)):
            price += int(rng.choice([-2, -1, 1, 2])) * 0.25
            rows.append(
                {
                    "timestamp": t,
                    "available_at": t + timedelta(minutes=1),
                    "open": price,
                    "high": price + 0.5,
                    "low": price - 0.5,
                    "close": price,
                    "volume": 1000 + i,
                    "contract": contract.identifier,
                    "symbol": contract.product,
                    "session_date": t.date(),
                }
            )
    return pl.DataFrame(rows)


def test_prior_session_nulls_and_future_changes_do_not_leak(contract):
    frame = history(contract)
    features = intraday_features(frame)
    assert features.height == frame.height
    first = frame["session_date"][0]
    assert (
        features.filter(pl.col("session_date") == first)["previous_session_return"].null_count()
        == 390
    )
    assert (
        features.filter(pl.col("session_date") != first)["previous_session_return"].null_count()
        == 0
    )
    cutoff = frame["timestamp"][100]
    changed = frame.with_columns(
        pl.when(pl.col("timestamp") > cutoff)
        .then(pl.col("high") + 50)
        .otherwise(pl.col("high"))
        .alias("high")
    )
    other = intraday_features(changed)
    assert features.filter(pl.col("timestamp") <= cutoff).equals(
        other.filter(pl.col("timestamp") <= cutoff)
    )
    assert features["opening_range_ready"][:30].to_list() == [0] * 30
    assert features["opening_range_ready"][30] == 1
    # Opening-range high/low freezes once observed; later highs cannot revise it.
    assert features["opening_range_width"][30] == features["opening_range_width"][100]


@pytest.mark.parametrize("horizon", [5, 15, 60])
def test_targets_use_next_strictly_later_open_and_do_not_cross_sessions(contract, horizon):
    frame = history(contract)
    cutoff = datetime(2024, 6, 17, tzinfo=UTC)
    dataset, names, _ = build_futures_dataset(frame, holdout_start=cutoff, horizon=horizon)
    row = dataset.row(0, named=True)
    assert row["prediction_at"] < row["execution_at"] < row["label_end_at"] <= row["label_known_at"]
    assert row["label_end_at"] - row["execution_at"] == timedelta(minutes=horizon)
    assert row["execution_at"].date() == row["label_end_at"].date()
    bars = {r["timestamp"]: r for r in frame.to_dicts()}
    assert row["target"] == pytest.approx(
        bars[row["label_end_at"]]["open"] / bars[row["execution_at"]]["open"] - 1
    )
    assert not {"target", "target_class", "label_end_at"} & set(names)
    with pytest.raises(ValueError, match="physically exclude"):
        build_futures_dataset(frame, holdout_start=frame["available_at"].max(), horizon=horizon)


def test_global_purge_and_rolling_folds(contract):
    frame = history(contract)
    cutoff = datetime(2024, 6, 17, tzinfo=UTC)
    dataset, _, _ = build_futures_dataset(frame, holdout_start=cutoff)
    clone = dataset.with_columns(pl.lit("OTHER").alias("contract"))
    second_day = sorted(dataset["session_date"].unique())[1]
    clone = clone.with_columns(
        pl.when(pl.col("session_date") < second_day)
        .then(pl.lit(datetime(2024, 6, 12, 18, tzinfo=UTC)))
        .otherwise(pl.col("label_known_at"))
        .alias("label_known_at")
    )
    combined = pl.concat([dataset, clone])
    folds = list(
        futures_folds(combined, expanding=False, minute_grid=frame["available_at"].to_list())
    )
    assert folds
    for f in folds:
        assert f["train"]["label_known_at"].max() < f["validation"]["prediction_at"].min()
        assert f["validation"]["label_known_at"].max() < f["test"]["prediction_at"].min()
    assert folds[0]["train"]["contract"].unique().to_list() == [contract.identifier]


def test_sparse_gaps_reset_minute_features_and_incomplete_opening_range(contract):
    frame = history(contract)
    missing = frame["timestamp"][10]
    features = intraday_features(frame.filter(pl.col("timestamp") != missing))
    first_day = frame["session_date"][0]
    assert features.filter(pl.col("session_date") == first_day)["opening_range_ready"].sum() == 0
    next_bar = features.filter(pl.col("timestamp") == missing + timedelta(minutes=1)).row(
        0, named=True
    )
    assert next_bar["return_1m"] is None


def test_missing_entire_session_is_rejected(contract):
    from quantlab.futures.storage import normalize

    frame = history(contract).filter(pl.col("session_date") != datetime(2024, 6, 12).date())
    raw = (
        frame.select("timestamp", "open", "high", "low", "close", "volume", "contract")
        .write_csv()
        .encode()
    )
    with pytest.raises(ValueError, match="Missing minute"):
        normalize(raw, contract)
