"""Explicit cross-asset information-interval validation."""

import polars as pl


def validate_intervals(frame):
    required = {
        "session_date",
        "symbol",
        "prediction_at",
        "execution_at",
        "label_end_at",
        "label_known_at",
    }
    if required - set(frame.columns) or frame.is_empty():
        raise ValueError("Missing sample information intervals")
    if any(frame[c].null_count() for c in required):
        raise ValueError("Null information timestamp")
    for name in ("prediction_at", "execution_at", "label_end_at", "label_known_at"):
        dtype = frame.schema[name]
        if not isinstance(dtype, pl.Datetime) or dtype.time_zone is None:
            raise ValueError("Information timestamps must be timezone aware")
    if not frame.select(
        (
            (pl.col("prediction_at") < pl.col("execution_at"))
            & (pl.col("execution_at") < pl.col("label_end_at"))
            & (pl.col("label_end_at") <= pl.col("label_known_at"))
        ).all()
    ).item():
        raise ValueError("Misaligned information interval")
    if frame.select(pl.struct("symbol", "session_date").is_duplicated().any()).item():
        raise ValueError("Duplicate asset/session labels")


def purge_overlaps(training, evaluation, *, cutoff=None):
    """Use a global cross-asset cutoff, not independent per-ticker splits."""
    validate_intervals(training)
    validate_intervals(evaluation)
    start = evaluation["prediction_at"].min()
    if cutoff is not None:
        start = min(start, cutoff)
    # In chronological validation, matured-before-start strictly dominates interval overlap.
    clean = training.filter((pl.col("label_known_at") < start) & (pl.col("prediction_at") < start))
    return clean
