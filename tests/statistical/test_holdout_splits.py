from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from quantlab.ml.validation import walk_forward
from quantlab.statistical.holdout import HoldoutVault
from quantlab.statistical.splits import purge_overlaps, validate_intervals


def samples():
    dates = []
    day = date(2020, 1, 2)
    while len(dates) < 70:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)
    rows = []
    for i, d in enumerate(dates[:-5]):
        for symbol in ("AAA", "BBB"):
            rows.append(
                {
                    "session_date": d,
                    "symbol": symbol,
                    "prediction_at": datetime.combine(d, datetime.min.time(), UTC),
                    "execution_at": datetime.combine(dates[i + 1], datetime.min.time(), UTC),
                    "label_end_at": datetime.combine(dates[i + 4], datetime.min.time(), UTC),
                    "label_known_at": datetime.combine(dates[i + 4], datetime.min.time(), UTC)
                    + timedelta(hours=12),
                }
            )
    return pl.DataFrame(rows)


@pytest.mark.parametrize("expanding", [False, True])
def test_rolling_expanding_retraining_and_session_gap(expanding):
    frame = samples()
    folds = list(
        walk_forward(frame, 20, 10, 10, expanding, 2, gap_sessions=2, retraining_sessions=5)
    )
    dates = sorted(frame["session_date"].unique())
    used = []
    for f in folds:
        assert f.train["label_known_at"].max() < f.validation["prediction_at"].min()
        assert f.validation["label_known_at"].max() < f.test["prediction_at"].min()
        assert f.test["session_date"].n_unique() <= 5
        assert (
            dates.index(f.test["session_date"].min())
            - dates.index(f.validation["session_date"].max())
            >= 5
        )
        used.extend(f.test["session_date"].unique().to_list())
    assert len(used) == len(set(used))
    if expanding:
        assert folds[-1].train.height > folds[0].train.height
    else:
        assert folds[-1].train.height == folds[0].train.height


def test_cross_asset_long_label_is_globally_purged():
    frame = samples()
    train = frame.head(40)
    test = frame.slice(60, 10)
    train = train.with_columns(
        pl.when(pl.col("symbol") == "BBB")
        .then(pl.lit(test["label_known_at"].max()))
        .otherwise(pl.col("label_known_at"))
        .alias("label_known_at")
    )
    purged = purge_overlaps(train, test)
    assert purged["symbol"].unique().to_list() == ["AAA"]
    assert purged["label_known_at"].max() < test["prediction_at"].min()


def test_timestamp_alignment_rejected():
    frame = samples()
    with pytest.raises(ValueError, match="Misaligned"):
        validate_intervals(frame.with_columns(pl.col("prediction_at").alias("label_known_at")))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_intervals(pl.concat([frame, frame]))
    with pytest.raises(ValueError, match="Retraining"):
        list(walk_forward(frame, 20, 10, 10, retraining_sessions=0))
    with pytest.raises(ValueError, match="timezone"):
        validate_intervals(frame.with_columns(pl.col("prediction_at").dt.replace_time_zone(None)))


def manifest():
    return {
        "sources": {"SPY": "stable-source-hash"},
        "start": "2019-01-02",
        "end": "2019-12-31",
        "purpose": "untouched final",
    }


def test_holdout_one_use_and_explicit_release(tmp_path):
    vault = HoldoutVault(tmp_path / "vault.sqlite")
    m = manifest()
    identifier = vault.register(m)
    assert vault.register(m) == identifier
    with pytest.raises(ValueError, match="immutable"):
        vault.register({**m, "purpose": "new purpose"})
    called = []
    with pytest.raises(PermissionError):
        vault.evaluate(identifier, "invalid", lambda m: called.append(m))
    assert not called
    with pytest.raises(PermissionError):
        vault.authorize(identifier, actor="user", reason="test", confirmation="")
    token = vault.authorize(
        identifier,
        actor="test user",
        reason="synthetic test only",
        confirmation="AUTHORIZE_ONE_FINAL_EVALUATION",
    )
    result = vault.evaluate(identifier, token, lambda m: {"statistic": 1})
    assert result["results_released"] is False
    assert vault.status(identifier)["state"] == "CONSUMED"
    with pytest.raises(PermissionError):
        vault.evaluate(identifier, token, lambda m: 1)
    with pytest.raises(PermissionError):
        vault.release(identifier, actor="user", confirmation="")
    assert vault.release(
        identifier, actor="test user", confirmation="AUTHORIZE_RELEASE_FINAL_RESULTS"
    ) == {"statistic": 1}
    with pytest.raises(PermissionError):
        vault.authorize(
            identifier, actor="u", reason="r", confirmation="AUTHORIZE_ONE_FINAL_EVALUATION"
        )


def test_holdout_failure_remains_consumed(tmp_path):
    vault = HoldoutVault(tmp_path / "vault.sqlite")
    identifier = vault.register(manifest())
    token = vault.authorize(
        identifier, actor="test", reason="test", confirmation="AUTHORIZE_ONE_FINAL_EVALUATION"
    )

    def fail(m):
        raise RuntimeError("test failure")

    with pytest.raises(RuntimeError):
        vault.evaluate(identifier, token, fail)
    assert vault.status(identifier)["state"] == "CONSUMED"
    assert vault.status(identifier)["events"][-1]["event"] == "EVALUATION_FAILED_CONSUMED"


def test_overlapping_manifest_cannot_be_renamed_as_fresh(tmp_path):
    vault = HoldoutVault(tmp_path / "vault.sqlite")
    m = manifest()
    vault.register(m)
    with pytest.raises(ValueError, match="Overlapping"):
        vault.register({**m, "start": "2019-02-01"})
