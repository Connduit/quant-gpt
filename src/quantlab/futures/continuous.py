"""Causal forward contract selection; chart adjustments are never execution prices."""

from datetime import timedelta

import polars as pl


def select_contract(
    frame, contracts, as_of, *, method="calendar", roll_days=5, minimum_expiry=None
):
    if len({c.product for c in contracts.values()}) != 1:
        raise ValueError("Select one product before building or rolling a contract chain")
    if method not in ("calendar", "volume") or type(roll_days) is not int or roll_days < 0:
        raise ValueError("Use bounded calendar/volume roll criteria")
    eligible = sorted(
        (
            c
            for c in contracts.values()
            if c.last_trade > as_of and (minimum_expiry is None or c.last_trade >= minimum_expiry)
        ),
        key=lambda c: c.last_trade,
    )
    if not eligible:
        raise ValueError("No unexpired forward contract")
    while len(eligible) > 1 and eligible[0].last_trade - as_of <= timedelta(days=roll_days):
        eligible.pop(0)
    front = eligible[0]
    if method == "volume":
        known = frame.filter(pl.col("available_at") <= as_of)
        if not known.is_empty():
            known = known.filter(pl.col("session_date") == known["session_date"].max())
            volumes = dict(known.group_by("contract").agg(pl.col("volume").sum()).iter_rows())
            front = max(
                eligible, key=lambda c: (volumes.get(c.identifier, 0), -c.last_trade.timestamp())
            )
    return front.identifier


def continuous_series(frame, contracts, *, method="calendar", roll_days=5, back_adjust=False):
    rows = []
    rolls = []
    previous = None
    for timestamp in sorted(frame["timestamp"].unique().to_list()):
        identifier = select_contract(
            frame,
            contracts,
            timestamp,
            method=method,
            roll_days=roll_days,
            minimum_expiry=contracts[previous].last_trade if previous else None,
        )
        selected = frame.filter(
            (pl.col("timestamp") == timestamp) & (pl.col("contract") == identifier)
        )
        if selected.is_empty():
            continue
        row = selected.row(0, named=True)
        if previous is not None and identifier != previous:
            old = frame.filter(
                (pl.col("timestamp") == timestamp) & (pl.col("contract") == previous)
            )
            if old.is_empty():
                raise ValueError("Roll requires observed actual prices for both contracts")
            gap = float(row["open"]) - float(old["open"][0])
            rolls.append({"at": timestamp, "old": previous, "new": identifier, "gap": gap})
        rows.append(row)
        previous = identifier
    if not rows:
        raise ValueError("No observed selected contract prices")
    result = pl.DataFrame(rows)
    if back_adjust:
        shifts = pl.Series(
            [sum(r["gap"] for r in rolls if row["timestamp"] < r["at"]) for row in rows]
        )
        result = result.with_columns(
            *[(pl.col(k) + shifts).alias(k) for k in ("open", "high", "low", "close")]
        )
    return result, {
        "tradable": False,
        "price_basis": "back_adjusted_chart_only"
        if back_adjust
        else "continuous_selected_contract_research",
        "feature_safe": not back_adjust,
        "rolls": rolls,
        "warning": (
            "Actual contract fills and roll orders "
            "required; back-adjustment is ex-post charting only"
        ),
    }
