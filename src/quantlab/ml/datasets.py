from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import date

import polars as pl

from quantlab.backtesting.data import DailyData, MarketData
from quantlab.features import FeatureConfig, calculate, definitions


@dataclass(frozen=True)
class Dataset:
    frame: pl.DataFrame
    feature_names: tuple[str, ...]
    metadata: dict


def available_history(feed: DailyData, index: int, prediction_at):
    if feed.bars[index].available_at > prediction_at:
        raise ValueError("Unavailable bar in feature history")
    history = []
    splits = [
        s
        for s in feed.actions.splits
        if s.date <= prediction_at.astimezone(feed.bars[0].open_time.tzinfo).date()
        and any(b.session_date == s.date and b.open_time <= prediction_at for b in feed.bars)
    ]
    if not splits:
        return feed.bars[: index + 1]
    for bar in feed.bars[: index + 1]:
        if bar.available_at > prediction_at:
            raise ValueError("Unavailable bar in feature history")
        ratio = 1
        for split in splits:
            if split.date > bar.session_date:
                ratio *= split.ratio
        history.append(
            bar
            if ratio == 1
            else replace(
                bar,
                open=bar.open / ratio,
                high=bar.high / ratio,
                low=bar.low / ratio,
                close=bar.close / ratio,
                volume=bar.volume * ratio,
            )
        )
    return tuple(history)


def forward_return(feed: DailyData, entry: int, exit_index: int) -> float:
    """Cost-free raw open-to-open total return, including dividend receivables."""
    shares, dividends = 1, 0
    for bar in feed.bars[entry + 1 : exit_index + 1]:
        for split in feed.actions.splits:
            if split.date == bar.session_date:
                shares *= split.ratio
        for dividend in feed.actions.dividends:
            if dividend.ex_date == bar.session_date:
                dividends += shares * dividend.amount
    return float((shares * feed.bars[exit_index].open + dividends) / feed.bars[entry].open - 1)


def build_dataset(
    feeds: dict[str, DailyData],
    universe: tuple[str, ...],
    benchmark: str,
    holdout_start: date,
    horizon: int = 5,
    features: FeatureConfig | None = None,
    sectors: dict[str, str] | None = None,
    *,
    development_only: bool = False,
    feature_cache: dict | None = None,
) -> Dataset:
    features = features or FeatureConfig()
    if type(horizon) is not int or horizon not in (1, 5, 10):
        raise ValueError("Supported horizons are 1, 5 and 10 sessions")
    if (
        benchmark not in feeds
        or benchmark in universe
        or not universe
        or len(set(universe)) != len(universe)
    ):
        raise ValueError("Provide a unique stock universe and separate benchmark feed")
    MarketData(tuple(feeds.values()))  # enforces aligned calendar and data origin
    if set(universe) - set(feeds):
        raise ValueError("Universe is missing input snapshots")
    sectors = sectors or {}
    if sectors and (set(sectors) != set(universe) or set(sectors.values()) - set(feeds)):
        raise ValueError("Sector context must cover every ticker with supplied ETF snapshots")
    reference = feeds[benchmark].bars
    if development_only:
        if reference[-1].session_date >= holdout_start or any(
            d.manifest["provider"] != "discovery-development" for d in feeds.values()
        ):
            raise ValueError("Discovery requires sealed pre-holdout development prefixes")
    elif not reference[0].session_date < holdout_start <= reference[-1].session_date:
        raise ValueError("Reserve a final holdout inside the supplied history")
    names = tuple(definitions(features, bool(sectors)))
    opens = [bar.open_time for bar in reference]
    rows = []
    missing, holdout_purged = 0, 0
    for i in range(features.warmup - 1, len(reference)):
        if reference[i].session_date >= holdout_start:
            break  # never calculate holdout features or labels
        prediction_at = max(feed.bars[i].available_at for feed in feeds.values())
        entry = bisect_right(opens, prediction_at)
        end = entry + horizon
        if end >= len(reference) or reference[end].session_date >= holdout_start:
            holdout_purged += 1
            continue
        histories = None
        benchmark_return = forward_return(feeds[benchmark], entry, end)
        for symbol in universe:
            key = (symbol, reference[i].session_date, prediction_at)
            values = feature_cache.get(key) if feature_cache is not None else None
            if values is None:
                if histories is None:
                    histories = {
                        s: available_history(d, i, prediction_at) for s, d in feeds.items()
                    }
                values = calculate(
                    histories[symbol],
                    histories[benchmark],
                    features,
                    histories[sectors[symbol]] if sectors else None,
                )
                if feature_cache is not None:
                    feature_cache[key] = values
            if any(value is None for value in values.values()):
                missing += 1
                continue
            stock_return = forward_return(feeds[symbol], entry, end)
            excess = stock_return - benchmark_return
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": reference[i].session_date,
                    "prediction_at": prediction_at,
                    "execution_at": reference[entry].open_time,
                    "label_end_at": reference[end].open_time,
                    "label_known_at": max(
                        feeds[symbol].bars[end].available_at,
                        feeds[benchmark].bars[end].available_at,
                    ),
                    "forward_return": stock_return,
                    "benchmark_forward_return": benchmark_return,
                    "target": excess,
                    "target_class": int(excess > 0),
                    **values,
                }
            )
    if not rows:
        raise ValueError("No complete pre-holdout samples; supply more history or shorter windows")
    frame = pl.DataFrame(rows).sort("prediction_at", "symbol")
    return Dataset(
        frame,
        names,
        {
            "horizon": horizon,
            "target": "cost_free_next_eligible_open_to_horizon_open_excess_total_return",
            "label_availability": "both required exit daily bars must have been published",
            "benchmark": benchmark,
            "universe": universe,
            "universe_bias": "fixed supplied universe; survivorship bias possible",
            "point_in_time_certified": False,
            "holdout_start": holdout_start,
            "holdout_status": "not_evaluated",
            "reserved_holdout_sessions": sum(b.session_date >= holdout_start for b in reference),
            "holdout_boundary_purged_sessions": holdout_purged,
            "missing_feature_rows_dropped": missing,
            "feature_definitions": definitions(features, bool(sectors)),
            "snapshot_ids": {s: d.snapshot_id for s, d in feeds.items()},
        },
    )
