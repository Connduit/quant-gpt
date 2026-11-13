"""Verify saved prediction evidence and raw execution inputs before simulation."""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import polars as pl

from quantlab.backtesting.actions import CorporateActions
from quantlab.backtesting.data import DailyData, MarketData
from quantlab.data.storage import SnapshotStore
from quantlab.profitability.strategy import verify_prediction_rows
from quantlab.web.workflows import research_blockers, safe_manifest

PROTECTED_START, PROTECTED_END = date(2019, 1, 2), date(2019, 12, 31)


def permitted_dates(start, end):
    if start <= PROTECTED_END and end >= PROTECTED_START:
        raise ValueError("Phase 12C cannot read or evaluate the protected 2019 equity holdout")
    if start > end:
        raise ValueError("Invalid evaluation dates")


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes its saved job")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_saved_predictions(source: Path, request):
    source = source.resolve()
    result = json.loads(checked_path(source, "result.json").read_text())
    if result.get("status") != "COMPLETED" or result.get("workflow") != "training":
        raise ValueError("Choose a completed saved ML training job")
    original = result["request"]
    # Bounds are inspected BEFORE opening predictions, dataset or any price payload.
    if not original.get("start") or not original.get("end"):
        raise ValueError("Re-run training with explicit dates before strategy evaluation")
    start, end = date.fromisoformat(original["start"]), date.fromisoformat(original["end"])
    permitted_dates(start, end)
    permitted_dates(request.start, request.end)
    if request.start < start or request.end > end:
        raise ValueError("Evaluation range must be inside the saved training run's range")
    report = result["report"]
    input_ids = result.get("input_snapshot_ids")
    if not isinstance(input_ids, list) or not 2 <= len(input_ids) <= 12:
        raise ValueError("Saved execution input identities are missing")
    input_library = checked_path(source, "inputs")
    for sid in input_ids:
        metadata = safe_manifest(input_library, sid, allow_holdout=True)
        bounds = metadata["request"]
        permitted_dates(date.fromisoformat(bounds["start"]), date.fromisoformat(bounds["end"]))
        if metadata.get("parent_snapshot") not in result.get("snapshot_ids", []):
            raise ValueError("Execution input lineage differs from the training run")
    directory = checked_path(source, "research")
    for file, key in (
        ("out_of_sample_predictions.parquet", "predictions_sha256"),
        ("dataset.parquet", "dataset_sha256"),
    ):
        if sha(checked_path(directory, file)) != report[key]:
            raise ValueError(f"Saved {file} checksum mismatch")
    frame = pl.read_parquet(directory / "out_of_sample_predictions.parquet")
    frame = frame.filter(
        (pl.col("model") == request.model)
        & pl.col("session_date").is_between(request.start, request.end)
    )
    if frame.is_empty():
        raise ValueError("No saved out-of-sample predictions for this model and date range")
    if frame.height > 36000:
        raise ValueError("Prediction row budget exceeded")
    rows = frame.to_dicts()
    verify_prediction_rows(rows)
    manifests = {}
    for fold in frame["fold"].unique().to_list():
        name = f"models/fold-{int(fold)}/{request.model}"
        manifest = json.loads(checked_path(directory, f"{name}/manifest.json").read_text())
        if (
            manifest["spec"]["type"] != request.model
            or sha(checked_path(directory, f"{name}/model.joblib")) != manifest["sha256"]
        ):
            raise ValueError("Saved model identity or checksum mismatch")
        manifests[str(fold)] = manifest
    fold_evidence = {fold["fold"]: fold for fold in report.get("folds", [])}
    for row in rows:
        evidence = fold_evidence.get(row["fold"])
        if (
            not evidence
            or row["model_available_at"] != datetime.fromisoformat(evidence["fitted_at"])
            or row["train_label_max"] != datetime.fromisoformat(evidence["train_label_max"])
        ):
            raise ValueError("Prediction clocks disagree with the saved fold evidence")
        manifest = manifests[str(row["fold"])]
        if not set(manifest["features"]).issubset(frame.columns):
            raise ValueError("Prediction feature schema differs from the saved model")
        row["model_version"] = manifest["sha256"]
    return result, rows, manifests


def load_execution_feeds(source, result, request):
    library = checked_path(source, "inputs")
    store = SnapshotStore(library)
    feeds, blockers = {}, []
    ids = result["input_snapshot_ids"]
    if not 2 <= len(ids) <= 12:
        raise ValueError("Saved execution input count is outside the budget")
    # Inspect every manifest before opening ANY price payload.
    metadata = {}
    for sid in ids:
        m = safe_manifest(library, sid, allow_holdout=True)
        bounds = m["request"]
        permitted_dates(date.fromisoformat(bounds["start"]), date.fromisoformat(bounds["end"]))
        if m["price_basis"] != "unadjusted" or m["synthetic"]:
            raise ValueError(
                "Profitability evaluation requires real, raw unadjusted execution prices"
            )
        if m.get("symbol_changes") or m.get("delisted") or m.get("lifecycle_events"):
            raise ValueError(
                "Symbol changes/delistings require a validated lifecycle execution adapter"
            )
        reasons = research_blockers(library, sid, m, start=request.start, end=request.end)
        if reasons and request.research_mode != "exploratory":
            raise ValueError("Strict profitability evidence missing: " + "; ".join(reasons))
        blockers.extend(f"{bounds['symbol']}: {r}" for r in reasons)
        metadata[sid] = m
    for sid, m in metadata.items():
        bounds = m["request"]
        ledger = checked_path(library, f"actions/{sid}.json")
        if ledger.is_file():
            actions = CorporateActions.load(ledger)
        else:
            actions = CorporateActions(
                bounds["symbol"],
                date.fromisoformat(bounds["start"]),
                date.fromisoformat(bounds["end"]),
                "No corporate-event evidence supplied; event coverage UNKNOWN, not asserted empty",
                complete=False,
                coverage_method="unverified_events",
                limitations=(
                    "Missing splits and dividends can invalidate simulated wealth and returns.",
                ),
            )
        feed = DailyData.from_snapshot(
            store, sid, actions, allow_unverified_actions=request.research_mode == "exploratory"
        )
        if feed.instrument.symbol in feeds:
            raise ValueError("Duplicate execution instrument")
        feeds[feed.instrument.symbol] = feed
    if "SPY" not in feeds:
        raise ValueError("Execution inputs require SPY")
    MarketData(tuple(feeds.values()))
    return feeds, blockers
