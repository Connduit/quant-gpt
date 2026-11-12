"""A fixed candidate-model evaluation, not automated hypothesis or strategy discovery."""

import hashlib
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import polars as pl
import yaml

from quantlab.backtesting.actions import CorporateActions
from quantlab.backtesting.data import DailyData, MarketData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, decimal
from quantlab.backtesting.report import dumps, export_report
from quantlab.data.storage import SnapshotStore
from quantlab.ml.datasets import build_dataset
from quantlab.ml.evaluation import evaluate
from quantlab.ml.models import ResearchModel
from quantlab.ml.validation import walk_forward
from quantlab.research.config import Experiment, load_experiment
from quantlab.strategies.ranking import RankingStrategy


def run_experiment(config_path: Path, output: Path, *, prefix_only=False) -> dict:
    config = load_experiment(config_path)
    if output.exists():
        raise ValueError("Research output exists; use a new directory")
    store = SnapshotStore(config.data_dir)
    if prefix_only:
        for entry in config.snapshots.values():
            sid = entry["snapshot_id"] if isinstance(entry, dict) else entry
            store.prefix_manifest(sid, config.holdout_start)
    feeds = {}
    for symbol, entry in config.snapshots.items():
        actions = None
        if isinstance(entry, dict):
            if set(entry) != {"snapshot_id", "actions"}:
                raise ValueError("Snapshot mappings require snapshot_id and actions")
            ledger = Path(entry["actions"])
            if not ledger.is_absolute():
                ledger = config_path.resolve().parent / ledger
            actions = CorporateActions.load(ledger)
            snapshot = entry["snapshot_id"]
        else:
            snapshot = entry
        feeds[symbol] = DailyData.from_snapshot(store, snapshot, actions)
        if feeds[symbol].instrument.symbol != symbol:
            raise ValueError("Snapshot instrument does not match configured ticker")
    dataset = build_dataset(
        feeds,
        config.universe,
        config.benchmark,
        config.holdout_start,
        config.horizon,
        config.features,
        config.sectors,
        prefix_only=prefix_only,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".pending-research-", dir=output.parent))
    try:
        return _execute(config, config_path, feeds, dataset, temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _execute(config: Experiment, config_path, feeds, dataset, temporary, output):
    predictions = []
    fold_reports = []
    for fold in walk_forward(
        dataset.frame,
        config.training_sessions,
        config.validation_sessions,
        config.test_sessions,
        config.expanding,
        config.embargo_sessions,
    ):
        report = {
            "fold": fold.number,
            "fitted_at": fold.fitted_at,
            "train_label_max": fold.train["label_known_at"].max(),
            "train_rows": fold.train.height,
            "validation_rows": fold.validation.height,
            "test_rows": fold.test.height,
            "purged_train": fold.purged_train,
            "purged_validation": fold.purged_validation,
            "train_prediction_start": fold.train["prediction_at"].min(),
            "train_prediction_end": fold.train["prediction_at"].max(),
            "validation_start": fold.validation["prediction_at"].min(),
            "validation_end": fold.validation["prediction_at"].max(),
            "test_start": fold.test["prediction_at"].min(),
            "test_end": fold.test["prediction_at"].max(),
            "models": {},
        }
        for spec in config.models:
            model = ResearchModel(spec).fit(fold.train, dataset.feature_names)
            val_predictions = model.predict(fold.validation)
            scores = model.predict(fold.test)
            model.save(temporary / "models" / f"fold-{fold.number}" / spec.type)
            report["models"][spec.type] = {
                "objective": spec.objective,
                "validation": evaluate(fold.validation, val_predictions, spec.objective),
                "out_of_sample": evaluate(fold.test, scores, spec.objective),
                "feature_importance": model.importance(),
            }
            predicted = fold.test.with_columns(
                pl.Series("prediction", scores, dtype=pl.Float64),
                pl.lit(spec.type).alias("model"),
                pl.lit(fold.number).alias("fold"),
                pl.lit(fold.fitted_at).alias("model_available_at"),
                pl.lit(report["train_label_max"]).alias("train_label_max"),
            )
            predictions.append(predicted)
        fold_reports.append(report)
    all_predictions = pl.concat(predictions).sort("model", "prediction_at", "symbol")
    primary = all_predictions.filter(pl.col("model") == config.primary_model)
    start_day = primary["session_date"].min()
    # Include the last signal's eligible open, never any holdout prices.
    end_day = primary["execution_at"].max().date()
    market = MarketData(
        tuple(
            replace(
                d,
                bars=tuple(
                    b
                    for b in d.bars
                    if start_day <= b.session_date <= end_day
                    and b.session_date < config.holdout_start
                ),
            )
            for d in feeds.values()
        )
    )
    execution = BacktestConfig(decimal(config.initial_cash), Costs(**config.execution))
    rows = primary.to_dicts()
    benchmark = run_backtest(
        market,
        RankingStrategy(rows, config.universe, config.benchmark, config.ranking, "spy_buy_hold"),
        execution,
    )
    trading = {}
    for mode in ("ml", "random", "momentum", "mean_reversion", "equal_weight"):
        result = run_backtest(
            market,
            RankingStrategy(rows, config.universe, config.benchmark, config.ranking, mode),
            execution,
        )
        exported = export_report(
            result,
            benchmark,
            temporary / "backtests" / mode,
            benchmark_policy="SPY_buy_hold_with_configured_cash_reserve",
        )
        trading[mode] = {
            "performance": result.metrics,
            "order_status_counts": exported["order_status_counts"],
        }
    trading["spy_buy_hold"] = {"performance": benchmark.metrics}
    primary_return = trading["ml"]["performance"]["total_return"]
    simpler = {k: v["performance"]["total_return"] for k, v in trading.items() if k != "ml"}
    best_baseline = max(simpler, key=simpler.get)
    conclusion = (
        "ML did not outperform the strongest simpler baseline after costs."
        if primary_return <= simpler[best_baseline]
        else (
            "ML exceeded the simpler baselines in this simulation; "
            "this does not establish statistical significance or a trading edge."
        )
    )
    original = config_path.read_text()
    resolved = yaml.safe_load(original)
    resolved["data"]["data_dir"] = str(config.data_dir.resolve())
    for entry in resolved["data"]["snapshots"].values():
        if isinstance(entry, dict):
            ledger = Path(entry["actions"])
            entry["actions"] = str((config_path.resolve().parent / ledger).resolve())
    (temporary / "original_configuration.yaml").write_text(original)
    (temporary / "configuration.yaml").write_text(yaml.safe_dump(resolved, sort_keys=False))
    dataset.frame.write_parquet(temporary / "dataset.parquet")
    all_predictions.write_parquet(temporary / "out_of_sample_predictions.parquet")
    report = {
        "name": config.name,
        "primary_model": config.primary_model,
        "synthetic": market.manifest["synthetic"],
        "performance_kind": "hypothetical_research",
        "dataset": dataset.metadata,
        "features": asdict(config.features),
        "folds": fold_reports,
        "predictive_performance": {
            spec.type: evaluate(
                all_predictions.filter(pl.col("model") == spec.type),
                all_predictions.filter(pl.col("model") == spec.type)["prediction"].to_numpy(),
                spec.objective,
            )
            for spec in config.models
        },
        "trading": trading,
        "best_baseline": best_baseline,
        "ml_outperformed_spy": primary_return > simpler["spy_buy_hold"],
        "ml_outperformed_all_baselines": primary_return > simpler[best_baseline],
        "conclusion": conclusion,
        "holdout": {"start": config.holdout_start, "status": "not_evaluated"},
        "limitations": [
            "Fixed supplied universe: survivorship bias possible.",
            "No independently verified point-in-time source certification.",
            "Overlapping OOS labels are not independent statistical evidence.",
            "No hypothesis search, significance test or multiple-testing correction.",
            "Position weights are rebalance targets; gaps/drift can change realized weights.",
            "All demonstrations on synthetic inputs are software checks, not trading evidence.",
        ],
        "configuration_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256((temporary / "dataset.parquet").read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256(
            (temporary / "out_of_sample_predictions.parquet").read_bytes()
        ).hexdigest(),
    }
    (temporary / "research_report.json").write_text(dumps(report) + "\n")
    temporary.rename(output)
    return report
