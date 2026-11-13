"""Price-only predictive experiments, deliberately independent of trading adapters."""

import hashlib
import math
import shutil
import tempfile
from bisect import bisect_right
from datetime import date, timedelta
from pathlib import Path

import exchange_calendars as xcals
import polars as pl

from quantlab.backtesting.models import Bar, decimal
from quantlab.backtesting.report import dumps
from quantlab.data.providers.base import DataRequest
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily
from quantlab.features import FeatureConfig, calculate, definitions
from quantlab.ml.evaluation import evaluate
from quantlab.ml.models import ModelSpec, ResearchModel
from quantlab.ml.validation import walk_forward


def price_histories(library, snapshots):
    store = SnapshotStore(library)
    histories, provenance, jumps = {}, {}, {}
    for symbol, sid in snapshots.items():
        metadata = store.manifest(sid)
        if metadata["synthetic"] or metadata["price_basis"] not in ("unadjusted", "adjusted"):
            raise ValueError("Exploratory ML requires real data with a declared price basis")
        if metadata["calendar"] != "XNYS" or metadata["interval"] != "1d":
            raise ValueError("Exploratory ML supports XNYS daily-equity snapshots only")
        frame = store.read(sid)
        bounds = metadata["request"]
        request = DataRequest(
            symbol, date.fromisoformat(bounds["start"]), date.fromisoformat(bounds["end"])
        )
        raw = (store.root / sid / "source.csv").read_bytes()
        normalized = normalize_daily(raw, request)
        columns = ["session_date", "open", "high", "low", "close", "volume", "timestamp"]
        if (
            frame.height != metadata["row_count"]
            or bounds["symbol"] != symbol
            or frame["symbol"].unique().to_list() != [symbol]
            or not frame.select(columns).equals(normalized.select(columns))
        ):
            raise ValueError("Exploratory input does not match its validated source")
        availability = frame["available_at"]
        if (
            not isinstance(availability.dtype, pl.Datetime)
            or availability.dtype.time_zone != "UTC"
            or availability.null_count()
            or not availability.is_sorted()
            or (availability < frame["timestamp"]).any()
        ):
            raise ValueError("Exploratory inputs require chronological UTC availability timestamps")
        calendar = xcals.get_calendar(
            "XNYS", start=request.start - timedelta(days=7), end=request.end + timedelta(days=7)
        )
        bars = tuple(
            Bar(
                symbol,
                row["session_date"],
                calendar.session_open(str(row["session_date"])).to_pydatetime(),
                row["timestamp"],
                row["available_at"],
                *[decimal(row[name]) for name in ("open", "high", "low", "close")],
                row["volume"],
            )
            for row in frame.iter_rows(named=True)
        )
        histories[symbol] = bars
        provenance[symbol] = {
            "snapshot_id": sid,
            "parent_snapshot": metadata["parent_snapshot"],
            "price_basis": metadata["price_basis"],
        }
        jumps[symbol] = sum(
            abs(float(b.close / a.close - 1)) >= 0.4 for a, b in zip(bars, bars[1:], strict=False)
        )
    if len({entry["price_basis"] for entry in provenance.values()}) != 1:
        raise ValueError("Exploratory inputs must use the same declared price basis")
    dates = [[b.session_date for b in bars] for bars in histories.values()]
    if any(days != dates[0] for days in dates):
        raise ValueError("Exploratory inputs must have identical trading sessions")
    return histories, provenance, jumps


def price_dataset(histories, horizon):
    features = FeatureConfig()
    names = tuple(definitions(features))
    reference = histories["SPY"]
    opens = [b.open_time for b in reference]
    rows = []
    for i in range(features.warmup - 1, len(reference)):
        prediction_at = max(bars[i].available_at for bars in histories.values())
        entry = bisect_right(opens, prediction_at)
        exit_index = entry + horizon
        if exit_index >= len(reference):
            continue
        benchmark_change = float(reference[exit_index].open / reference[entry].open - 1)
        for symbol, bars in histories.items():
            if symbol == "SPY":
                continue
            values = calculate(bars[: i + 1], reference[: i + 1], features)
            if any(value is None or not math.isfinite(float(value)) for value in values.values()):
                continue
            change = float(bars[exit_index].open / bars[entry].open - 1)
            target = change - benchmark_change
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": reference[i].session_date,
                    "prediction_at": prediction_at,
                    "execution_at": reference[entry].open_time,
                    "label_end_at": reference[exit_index].open_time,
                    "label_known_at": max(
                        bars[exit_index].available_at, reference[exit_index].available_at
                    ),
                    "forward_return": change,
                    "benchmark_forward_return": benchmark_change,
                    "target": target,
                    "target_class": int(target > 0),
                    **values,
                }
            )
    if not rows:
        raise ValueError("Not enough history for exploratory features and targets")
    return pl.DataFrame(rows).sort("prediction_at", "symbol"), names


def predictive_metrics(frame, predictions, objective):
    metrics = evaluate(frame, predictions, objective)
    metrics["error_target"] = (
        "positive_excess_price_change_probability"
        if objective == "classification"
        else "excess_price_change"
    )
    return metrics


def run_exploratory_ml(request, library: Path, snapshots: dict, output: Path) -> dict:
    if output.exists():
        raise ValueError("Exploratory output exists; use a new directory")
    histories, provenance, jumps = price_histories(library, snapshots)
    frame, names = price_dataset(histories, request.horizon)
    folds = list(
        walk_forward(
            frame,
            request.training_sessions,
            request.validation_sessions,
            request.test_sessions,
            expanding=False,
            embargo_sessions=request.horizon,
        )
    )
    if len(folds) > 8:
        raise ValueError("Budget allows at most eight folds; adjust windows")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".pending-exploratory-", dir=output.parent))
    try:
        predictions, fold_reports = [], []
        for fold in folds:
            report = {
                "fold": fold.number,
                "fitted_at": fold.fitted_at,
                "train_label_max": fold.train["label_known_at"].max(),
                "train_rows": fold.train.height,
                "validation_rows": fold.validation.height,
                "test_rows": fold.test.height,
                "purged_train": fold.purged_train,
                "purged_validation": fold.purged_validation,
                "test_start": fold.test["session_date"].min(),
                "test_end": fold.test["session_date"].max(),
                "models": {},
            }
            for name in request.models:
                spec = ModelSpec(
                    name,
                    "classification" if name == "logistic" else "regression",
                    request.seed,
                    {"n_estimators": 50, "max_depth": 4}
                    if name in ("random_forest", "lightgbm", "xgboost")
                    else {},
                )
                model = ResearchModel(spec).fit(fold.train, names)
                scores = model.predict(fold.test)
                model.save(temporary / "models" / f"fold-{fold.number}" / name)
                report["models"][name] = {
                    "validation": predictive_metrics(
                        fold.validation, model.predict(fold.validation), spec.objective
                    ),
                    "out_of_sample": predictive_metrics(fold.test, scores, spec.objective),
                    "feature_importance": model.importance(),
                }
                predictions.append(
                    fold.test.with_columns(
                        pl.Series("prediction", scores, dtype=pl.Float64),
                        pl.lit(name).alias("model"),
                        pl.lit(fold.number).alias("fold"),
                        pl.lit(fold.fitted_at).alias("model_available_at"),
                        pl.lit(report["train_label_max"]).alias("train_label_max"),
                    )
                )
            fold_reports.append(report)
        combined = pl.concat(predictions).sort("model", "prediction_at", "symbol")
        frame.write_parquet(temporary / "dataset.parquet")
        combined.write_parquet(temporary / "out_of_sample_predictions.parquet")
        (temporary / "configuration.json").write_text(request.model_dump_json(indent=2) + "\n")
        report = {
            "name": request.name,
            "research_mode": "exploratory",
            "performance_kind": "exploratory_predictive_only",
            "synthetic": False,
            "qualified": False,
            "promotion_allowed": False,
            "trading_simulated": False,
            "dataset": {
                "target": "next_eligible_open_to_horizon_open_excess_price_change",
                "total_return": False,
                "point_in_time_certified": False,
                "start": str(request.start),
                "end": str(request.end),
                "samples": frame.height,
                "horizon": request.horizon,
                "feature_definitions": definitions(FeatureConfig()),
                "snapshots": provenance,
                "large_close_price_changes": jumps,
            },
            "folds": fold_reports,
            "predictive_performance": {
                name: predictive_metrics(
                    combined.filter(pl.col("model") == name),
                    combined.filter(pl.col("model") == name)["prediction"].to_numpy(),
                    "classification" if name == "logistic" else "regression",
                )
                for name in request.models
            },
            "limitations": [
                "Price-only experiment without required action or historical-membership evidence.",
                "No action corrections are inferred. Raw splits and dividends "
                "can distort features and labels; declared adjusted prices use the vendor's basis.",
                "Targets are quoted price changes, not verified total returns.",
                "Fixed supplied stocks may introduce survivorship and selection bias.",
                "Chronological validation does not certify an untouched holdout or trading edge.",
                "No portfolio simulation, after-cost metrics, qualification or deployment.",
                "Large close-price changes (absolute change >=40%) are diagnostic counts, not "
                "verified corporate actions or corrected data.",
            ],
            "configuration_sha256": hashlib.sha256(
                (temporary / "configuration.json").read_bytes()
            ).hexdigest(),
            "dataset_sha256": hashlib.sha256(
                (temporary / "dataset.parquet").read_bytes()
            ).hexdigest(),
            "predictions_sha256": hashlib.sha256(
                (temporary / "out_of_sample_predictions.parquet").read_bytes()
            ).hexdigest(),
        }
        (temporary / "research_report.json").write_text(dumps(report) + "\n")
        temporary.rename(output)
        return report
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
