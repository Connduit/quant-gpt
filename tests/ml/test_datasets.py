from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from quantlab.backtesting.actions import CorporateActions, Dividend, Split
from quantlab.ml.datasets import available_history, build_dataset, forward_return
from quantlab.ml.validation import walk_forward


@pytest.mark.parametrize("horizon", [1, 5, 10])
def test_targets_are_next_open_excess_and_have_explicit_maturity(ml_feeds, small_features, horizon):
    feeds, _, dates, _ = ml_feeds
    dataset = build_dataset(
        feeds, ("AAA", "BBB", "CCC"), "SPY", dates[-25], horizon, small_features
    )
    row = dataset.frame.row(0, named=True)
    i = next(i for i, b in enumerate(feeds["AAA"].bars) if b.session_date == row["session_date"])
    stock = feeds[row["symbol"]].bars
    spy = feeds["SPY"].bars
    entry, end = i + 1, i + 1 + horizon
    expected = float(stock[end].open / stock[entry].open - spy[end].open / spy[entry].open)
    assert row["target"] == pytest.approx(expected)
    assert row["target_class"] == int(expected > 0)
    assert row["prediction_at"] < row["execution_at"] < row["label_known_at"]
    assert row["label_end_at"] == spy[end].open_time
    assert row["label_known_at"] == max(stock[end].available_at, spy[end].available_at)
    assert set(dataset.feature_names).isdisjoint(
        {"target", "target_class", "forward_return", "label_known_at"}
    )
    assert dataset.frame["label_end_at"].max().date() < dates[-25]


def test_future_holdout_mutation_does_not_change_development_dataset(ml_feeds, small_features):
    feeds, _, dates, _ = ml_feeds
    cutoff = dates[-25]
    original = build_dataset(feeds, ("AAA", "BBB"), "SPY", cutoff, 5, small_features)
    changed = {}
    for symbol, data in feeds.items():
        bars = tuple(
            replace(b, open=b.open * 10, high=b.high * 10, low=b.low * 10, close=b.close * 10)
            if b.session_date >= cutoff
            else b
            for b in data.bars
        )
        changed[symbol] = replace(data, bars=bars)
    mutated = build_dataset(changed, ("AAA", "BBB"), "SPY", cutoff, 5, small_features)
    assert_frame_equal(original.frame, mutated.frame)
    assert original.metadata["holdout_status"] == "not_evaluated"


def test_future_nonholdout_prices_do_not_change_earlier_features(ml_feeds, small_features):
    feeds, _, dates, _ = ml_feeds
    cutoff = dates[80]
    one = build_dataset(feeds, ("AAA", "BBB"), "SPY", dates[-25], 5, small_features)
    changed = {
        s: replace(
            d,
            bars=tuple(
                replace(b, open=b.open * 2, close=b.close * 2, high=b.high * 2, low=b.low * 2)
                if b.session_date >= cutoff
                else b
                for b in d.bars
            ),
        )
        for s, d in feeds.items()
    }
    two = build_dataset(changed, ("AAA", "BBB"), "SPY", dates[-25], 5, small_features)
    columns = ["symbol", "session_date", "prediction_at", *one.feature_names]
    assert_frame_equal(
        one.frame.filter(pl.col("session_date") < cutoff).select(columns),
        two.frame.filter(pl.col("session_date") < cutoff).select(columns),
    )


def test_purged_chronological_walk_forward(ml_feeds, small_features):
    feeds, _, dates, _ = ml_feeds
    dataset = build_dataset(feeds, ("AAA", "BBB", "CCC"), "SPY", dates[-25], 5, small_features)
    folds = list(walk_forward(dataset.frame, 40, 15, 20, embargo_sessions=2))
    seen = set()
    for fold in folds:
        assert fold.train["label_known_at"].max() < fold.fitted_at
        assert fold.validation["label_known_at"].max() < fold.test["prediction_at"].min()
        assert fold.train["session_date"].max() < fold.validation["session_date"].min()
        assert fold.validation["session_date"].max() < fold.test["session_date"].min()
        assert fold.purged_train > 0 and fold.purged_validation > 0
        test_dates = set(fold.test["session_date"].to_list())
        assert not seen & test_dates
        seen |= test_dates
    rolling = list(walk_forward(dataset.frame, 40, 15, 20, expanding=False))
    assert rolling[-1].train["session_date"].min() > rolling[0].train["session_date"].min()


def test_split_and_dividend_labels_match_economic_ownership(ml_feeds):
    feeds, _, dates, _ = ml_feeds
    source = feeds["AAA"]
    bars = tuple(
        replace(
            b,
            open=D(100 if i < 2 else 50),
            close=D(100 if i < 2 else 50),
            high=D(101 if i < 2 else 51),
            low=D(99 if i < 2 else 49),
            volume=1000,
        )
        for i, b in enumerate(source.bars)
    )
    actions = CorporateActions(
        "AAA",
        dates[0],
        dates[-1],
        "synthetic actions",
        (Split(dates[2], D(2)),),
        (Dividend(dates[3], dates[4], D(1)),),
    )
    data = replace(source, bars=bars, actions=actions)
    assert forward_return(data, 1, 3) == pytest.approx(0.02)
    before = available_history(data, 0, bars[0].available_at)
    after = available_history(data, 3, bars[3].available_at)
    assert before[0].close == 100
    assert after[0].close == 50
    assert after[0].volume == 2000
    assert after[0].close * after[0].volume == before[0].close * before[0].volume


def test_late_prediction_changes_execution_not_feature_cutoff(ml_feeds, small_features):
    feeds, _, dates, _ = ml_feeds
    modified = dict(feeds)
    source = feeds["AAA"]
    bars = list(source.bars)
    bars[30] = replace(bars[30], available_at=bars[31].open_time + timedelta(minutes=1))
    modified["AAA"] = replace(source, bars=tuple(bars))
    result = build_dataset(modified, ("AAA",), "SPY", dates[-25], 1, small_features)
    row = result.frame.filter(pl.col("session_date") == dates[30]).row(0, named=True)
    assert row["execution_at"] == bars[32].open_time


def test_optional_sector_context_and_missing_snapshots(ml_feeds, small_features):
    feeds, _, dates, _ = ml_feeds
    result = build_dataset(
        feeds,
        ("AAA", "BBB"),
        "SPY",
        dates[-25],
        features=small_features,
        sectors={"AAA": "CCC", "BBB": "CCC"},
    )
    assert "sector_relative_strength" in result.feature_names
    with pytest.raises(ValueError, match="Sector"):
        build_dataset(
            feeds,
            ("AAA", "BBB"),
            "SPY",
            dates[-25],
            features=small_features,
            sectors={"AAA": "CCC"},
        )
