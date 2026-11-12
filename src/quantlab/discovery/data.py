"""Materialize immutable development prefixes; optimization receives no holdout rows."""

import fcntl
import hashlib
import math
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import polars as pl

from quantlab.backtesting.actions import CorporateActions
from quantlab.backtesting.data import DailyData
from quantlab.backtesting.report import dumps
from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore
from quantlab.discovery.common import code_version, fingerprint, read_json, write_json
from quantlab.ml.datasets import build_dataset, forward_return
from quantlab.research.config import load_experiment


def load_feeds(config, directory):
    store = SnapshotStore(config.data_dir)
    feeds = {}
    for symbol, value in config.snapshots.items():
        actions = None
        if isinstance(value, dict):
            actions = CorporateActions.load((directory / value["actions"]).resolve())
            value = value["snapshot_id"]
        feeds[symbol] = DailyData.from_snapshot(store, value, actions)
        if feeds[symbol].instrument.symbol != symbol:
            raise ValueError("Snapshot symbol differs from declared universe")
    return feeds


def prepare(config, root: Path, *, prefix_only=False) -> dict:
    experiment = load_experiment(config.experiment)
    version = code_version()
    if prefix_only:
        # This path must never open an original archive containing protected rows.
        for value in experiment.snapshots.values():
            sid = value["snapshot_id"] if isinstance(value, dict) else value
            SnapshotStore(experiment.data_dir).prefix_manifest(sid, experiment.holdout_start)
    source_feeds = load_feeds(experiment, config.experiment.parent)
    cutoff = experiment.holdout_start
    if not prefix_only and any(
        not d.bars[0].session_date < cutoff <= d.bars[-1].session_date
        for d in source_feeds.values()
    ):
        raise ValueError("A real reserved holdout range is required in every original input")
    if prefix_only and any(d.bars[-1].session_date >= cutoff for d in source_feeds.values()):
        raise ValueError("Protected rows found in a declared development prefix")
    identity = {
        "sources": {s: d.snapshot_id for s, d in source_feeds.items()},
        "actions": {s: asdict(d.actions) for s, d in source_feeds.items()},
        "holdout_start": cutoff,
        "source_sha256": version["source_sha256"],
        "features": asdict(experiment.features),
        "universe": experiment.universe,
        "sectors": experiment.sectors,
        "horizons": config.horizons,
        **({"prefix_only": True} if prefix_only else {}),
    }
    seal_id = fingerprint(identity)
    parent = root / "sealed"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / seal_id
    with (parent / f"{seal_id}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not destination.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".pending-seal-", dir=parent))
            try:
                _materialize(
                    source_feeds,
                    experiment,
                    config.horizons,
                    temporary,
                    seal_id,
                    version["source_sha256"],
                )
                temporary.rename(destination)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
    seal = verify_seal(destination)
    return {
        "sealed_dir": str(destination.resolve()),
        "seal_id": seal_id,
        "seal_sha256": hashlib.sha256((destination / "seal.json").read_bytes()).hexdigest(),
        "source_sha256": version["source_sha256"],
        "git_commit": version["git_commit"],
        "hypothesis": config.hypothesis,
        "universe": list(experiment.universe),
        "sectors": experiment.sectors,
        "holdout_start": str(cutoff),
        "feature_config": asdict(experiment.features),
        "training_sessions": experiment.training_sessions,
        "validation_sessions": experiment.validation_sessions,
        "test_sessions": experiment.test_sessions,
        "expanding": experiment.expanding,
        "embargo_sessions": experiment.embargo_sessions,
        "initial_cash": experiment.initial_cash,
        "execution": experiment.execution,
        "strategy": {
            **asdict(experiment.ranking),
            "minimum_prediction": None,
            "volatility_adjusted": False,
            "position_sizing": "equal",
        },
        "eligibility": asdict(config.eligibility),
        "score": asdict(config.score),
        "cost_multipliers": list(config.cost_multipliers),
        "synthetic": seal["synthetic"],
    }


def _materialize(original, experiment, horizons, temporary, seal_id, source_sha):
    (temporary / "actions").mkdir()
    (temporary / "datasets").mkdir()
    store = SnapshotStore(temporary)
    feeds, identifiers = {}, {}
    for symbol, data in original.items():
        frame = pl.DataFrame(
            [
                {
                    "session_date": b.session_date,
                    "timestamp": b.close_time,
                    "available_at": b.available_at,
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": int(b.volume),
                    "symbol": symbol,
                    "exchange_timezone": "America/New_York",
                }
                for b in data.bars
                if b.session_date < experiment.holdout_start
            ]
        )
        start, end = frame["session_date"].min(), frame["session_date"].max()
        raw = (
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
        identifier = store.write(
            "discovery-development",
            DataRequest(symbol, start, end),
            Download(
                raw,
                f"development prefix of {data.snapshot_id}",
                data.manifest["price_basis"],
                data.manifest["synthetic"],
            ),
            frame,
        )
        actions = replace(
            data.actions,
            coverage_start=start,
            coverage_end=end,
            source=f"development prefix: {data.actions.source}",
            splits=tuple(a for a in data.actions.splits if start <= a.date <= end),
            dividends=tuple(a for a in data.actions.dividends if start <= a.ex_date <= end),
        )
        (temporary / "actions" / f"{symbol}.json").write_text(dumps(asdict(actions)))
        feeds[symbol] = DailyData.from_snapshot(store, identifier, actions)
        identifiers[symbol] = identifier
    cache = {}
    selected_horizons = sorted(set((1, *horizons)))
    dataset_metadata = {}
    for horizon in selected_horizons:
        dataset = build_dataset(
            feeds,
            experiment.universe,
            experiment.benchmark,
            experiment.holdout_start,
            horizon,
            experiment.features,
            experiment.sectors,
            development_only=True,
            feature_cache=cache,
        )
        frame = dataset.frame.with_columns(pl.col("target").alias("excess_return"))
        # RMS future open-to-open log total returns, including split/dividend entitlement.
        volatility = []
        for row in frame.iter_rows(named=True):
            bars = feeds[row["symbol"]].bars
            lookup = {bar.open_time: i for i, bar in enumerate(bars)}
            entry, end = lookup[row["execution_at"]], lookup[row["label_end_at"]]
            returns = [
                math.log1p(forward_return(feeds[row["symbol"]], i, i + 1))
                for i in range(entry, end)
            ]
            volatility.append(math.sqrt(sum(r * r for r in returns) / len(returns) * 252))
        frame = frame.with_columns(pl.Series("future_volatility", volatility))
        frame.write_parquet(temporary / "datasets" / f"horizon-{horizon}.parquet")
        dataset_metadata[str(horizon)] = dataset.metadata
    feature_rows = [
        {"symbol": s, "session_date": d, "prediction_at": t, **values}
        for (s, d, t), values in cache.items()
    ]
    pl.DataFrame(feature_rows).write_parquet(temporary / "features.parquet")
    hashes = {
        str(p.relative_to(temporary)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(temporary.rglob("*"))
        if p.is_file()
    }
    write_json(
        temporary / "seal.json",
        {
            "seal_id": seal_id,
            "source_sha256": source_sha,
            "holdout_start": experiment.holdout_start,
            "holdout_status": "not_accessible_to_trials",
            "holdout_sessions_excluded": sum(
                b.session_date >= experiment.holdout_start
                for b in next(iter(original.values())).bars
            ),
            "synthetic": next(iter(original.values())).manifest["synthetic"],
            "snapshots": identifiers,
            "action_coverage": {
                s: {
                    "complete": d.actions.complete,
                    "method": d.actions.coverage_method,
                    "limitations": d.actions.limitations,
                }
                for s, d in feeds.items()
            },
            "files_sha256": hashes,
            "datasets": dataset_metadata,
        },
    )


def verify_seal(directory: Path, expected_sha: str | None = None):
    if (
        expected_sha
        and hashlib.sha256((directory / "seal.json").read_bytes()).hexdigest() != expected_sha
    ):
        raise ValueError("Development seal changed")
    seal = read_json(directory / "seal.json")
    if seal.get("holdout_status") != "not_accessible_to_trials":
        raise ValueError("Not a development-only seal")
    for relative, checksum in seal["files_sha256"].items():
        path = (directory / relative).resolve()
        if (
            not path.is_relative_to(directory.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
        ):
            raise ValueError(f"Sealed data checksum mismatch: {relative}")
    return seal


def worker_data(definition):
    directory = Path(definition["sealed_dir"])
    seal = verify_seal(directory, definition["seal_sha256"])
    if (
        seal["source_sha256"] != definition["source_sha256"]
        or str(seal["holdout_start"]) != definition["holdout_start"]
    ):
        raise ValueError("Discovery source/holdout policy mismatch")
    store = SnapshotStore(directory)
    feeds = {
        s: DailyData.from_snapshot(
            store, identifier, CorporateActions.load(directory / "actions" / f"{s}.json")
        )
        for s, identifier in seal["snapshots"].items()
    }
    if any(
        str(b.session_date) >= definition["holdout_start"] for d in feeds.values() for b in d.bars
    ):
        raise ValueError("Holdout rows reached a trial")
    frame = pl.read_parquet(directory / "datasets" / f"horizon-{definition['horizon']}.parquet")
    # Compare horizons on a common calendar, not their different forecast tails.
    longest = max(int(h) for h in seal["datasets"])
    calendar = pl.read_parquet(directory / "datasets" / f"horizon-{longest}.parquet").select(
        "symbol", "session_date", pl.col("label_known_at").alias("boundary_known_at")
    )
    frame = frame.join(calendar, on=["symbol", "session_date"], how="inner").sort(
        "prediction_at", "symbol"
    )
    universe = definition["universe"]
    if set(universe) - set(feeds) or "SPY" in universe or not universe:
        raise ValueError("Invalid trial universe")
    frame = frame.filter(pl.col("symbol").is_in(universe))
    target = definition["target"]
    if target == "stock_return":
        frame = frame.with_columns(pl.col("forward_return").alias("target"))
    elif target == "volatility":
        frame = frame.with_columns(pl.col("future_volatility").alias("target"))
    elif target not in ("excess_return", "direction"):
        raise ValueError("Unknown trial target")
    names = tuple(seal["datasets"][str(definition["horizon"])]["feature_definitions"])
    selected = select_features(names, definition["groups"])
    if not selected:
        raise ValueError("Selected feature groups are empty")
    return feeds, frame, selected, seal


def select_features(names, groups):
    def group(name):
        memberships = set()
        if name.startswith(("return_", "log_return")) or name == "momentum":
            memberships.add("momentum")
        if name.startswith(("ma_distance", "distance_", "rolling_", "bollinger")):
            memberships.add("mean_reversion")
        if "volatility" in name or name.startswith("realized_vol") or name == "atr":
            memberships.add("volatility")
        if "volume" in name:
            memberships.add("volume")
        if name.startswith("spy_") or name == "market_trend":
            memberships.add("market_regime")
        if name.startswith(("rsi", "macd", "bollinger", "ma_crossover")):
            memberships.add("technical")
        if "relative_strength" in name:
            memberships.add("relative_strength")
        return memberships

    return tuple(name for name in names if group(name) & set(groups))
