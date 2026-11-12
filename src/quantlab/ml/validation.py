from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class Fold:
    number: int
    train: pl.DataFrame
    validation: pl.DataFrame
    test: pl.DataFrame
    fitted_at: object
    purged_train: int
    purged_validation: int


def walk_forward(
    frame: pl.DataFrame,
    training_sessions: int,
    validation_sessions: int,
    test_sessions: int,
    expanding: bool = True,
    embargo_sessions: int = 0,
    *,
    retraining_sessions: int | None = None,
    gap_sessions: int = 0,
):
    if any(
        type(n) is not int or n < 1 for n in (training_sessions, validation_sessions, test_sessions)
    ):
        raise ValueError("Training/validation/test windows must be positive session counts")
    if type(embargo_sessions) is not int or embargo_sessions < 0:
        raise ValueError("Embargo must be a nonnegative session count")
    from quantlab.statistical.splits import validate_intervals

    validate_intervals(frame)
    step = test_sessions if retraining_sessions is None else retraining_sessions
    if type(step) is not int or step < 1 or type(gap_sessions) is not int or gap_sessions < 0:
        raise ValueError("Retraining must be positive and gap nonnegative session counts")
    dates = sorted(frame["session_date"].unique().to_list())
    first_test = training_sessions + validation_sessions
    if first_test >= len(dates):
        raise ValueError(
            "Not enough usable sessions for chronological training, validation and test"
        )
    number = 0
    for test_start in range(first_test, len(dates), step):
        val_start = test_start - validation_sessions
        train_start = 0 if expanding else val_start - training_sessions
        train_dates = dates[
            train_start : max(train_start, val_start - embargo_sessions - gap_sessions)
        ]
        val_dates = dates[val_start : max(val_start, test_start - embargo_sessions - gap_sessions)]
        test_dates = dates[test_start : test_start + min(test_sessions, step)]
        raw_train = frame.filter(pl.col("session_date").is_in(train_dates))
        raw_val = frame.filter(pl.col("session_date").is_in(val_dates))
        test = frame.filter(pl.col("session_date").is_in(test_dates))
        val_cutoff = frame.filter(pl.col("session_date") == dates[val_start])["prediction_at"].min()
        test_cutoff = test["prediction_at"].min()
        train = raw_train.filter(pl.col("label_known_at") < val_cutoff)
        validation = raw_val.filter(pl.col("label_known_at") < test_cutoff)
        if train.height < 2 or validation.is_empty():
            raise ValueError("Purging/embargo left insufficient training or validation samples")
        yield Fold(
            number,
            train,
            validation,
            test,
            val_cutoff,
            raw_train.height - train.height,
            raw_val.height - validation.height,
        )
        number += 1
