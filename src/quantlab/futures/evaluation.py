"""Resource-worker futures evaluation on immutable pre-holdout minute prefixes."""

import hashlib
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import polars as pl

from quantlab.discovery.common import code_version, read_json, write_json
from quantlab.futures.contracts import contract_from_dict
from quantlab.futures.engine import FuturesBacktestConfig, FuturesCosts, run_futures_backtest
from quantlab.futures.features import build_futures_dataset, futures_folds
from quantlab.futures.risk import FuturesRisk
from quantlab.futures.strategies import FuturesStrategy
from quantlab.ml.evaluation import evaluate
from quantlab.ml.models import ModelSpec, ResearchModel
from quantlab.statistical.statistics import uncertainty


def sealed_data(definition):
    from datetime import datetime

    root = Path(definition["sealed_dir"])
    seal = read_json(root / "seal.json")
    if hashlib.sha256((root / "seal.json").read_bytes()).hexdigest() != definition["seal_sha256"]:
        raise ValueError("Futures seal changed")
    if (
        code_version()["source_sha256"] != definition["source_sha256"]
        or seal["source_sha256"] != definition["source_sha256"]
    ):
        raise ValueError("Futures code changed since preparation")
    for name, digest in seal["files_sha256"].items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Futures data checksum mismatch")
    frame = pl.read_parquet(root / "bars.parquet")
    features = pl.read_parquet(root / "features.parquet")
    cutoff = datetime.fromisoformat(definition["holdout_start"])
    if max(frame["available_at"].max(), features["available_at"].max()) >= cutoff:
        raise ValueError("Protected futures data reached worker")
    return (
        frame,
        features,
        seal,
        {k: contract_from_dict(v) for k, v in seal["contracts"].items()},
        cutoff,
    )


def evaluate_futures_candidate(definition, output, *, progress_handshake=False):
    frame, features, seal, contracts, cutoff = sealed_data(definition)
    instrument = definition.get("instrument") or next(iter(contracts.values())).product
    contracts = {k: c for k, c in contracts.items() if c.product == instrument}
    frame = frame.filter(pl.col("symbol") == instrument)
    features = features.filter(pl.col("symbol") == instrument)
    if frame.is_empty():
        raise ValueError("Requested futures instrument missing from sealed data")
    dataset, names, _ = build_futures_dataset(
        frame,
        holdout_start=cutoff,
        horizon=definition["horizon"],
        groups=definition["groups"],
        target=definition["target"],
        precomputed_features=features,
    )
    common = pl.read_parquet(Path(definition["sealed_dir"]) / "common-keys.parquet")
    dataset = dataset.join(common, on=["contract", "prediction_at"], how="inner")
    decision = definition.get("decision_minutes", 1)
    if decision not in (1, 5, 15):
        raise ValueError("Bound decision cadence to 1/5/15 minutes")
    dataset = dataset.filter(pl.col("prediction_at").dt.minute() % decision == 0)
    folds = list(
        futures_folds(
            dataset,
            training_sessions=definition["training_sessions"],
            validation_sessions=definition["validation_sessions"],
            test_sessions=definition["test_sessions"],
            expanding=definition.get("expanding", True),
            embargo_minutes=definition.get("embargo_minutes", 5),
            gap_minutes=definition.get("gap_minutes", 1),
            minute_grid=features["available_at"].unique().to_list(),
        )
    )
    if not folds:
        raise ValueError("No purged chronological futures folds")
    config = FuturesBacktestConfig(
        definition["initial_cash"],
        FuturesCosts(**definition["execution"]),
        FuturesRisk(**definition["risk"]),
        overnight=definition.get("overnight", "flat_rth"),
    )
    family = definition.get("strategy_family", "ml")
    windows = []
    predictions = []
    returns = []
    for number, fold in enumerate(folds):
        directory = output / f"window-{number}"
        directory.mkdir()
        test = fold["test"]
        days = test["session_date"].unique().to_list()
        market = frame.filter(pl.col("session_date").is_in(days))
        score_book = {}
        predictive = None
        if family == "ml":
            spec = ModelSpec(**definition["model"])
            required = (
                "classification"
                if definition["target"] in ("direction", "breakout_continuation")
                else "regression"
            )
            if spec.objective != required:
                raise ValueError("Target/model objective mismatch")
            model = ResearchModel(spec).fit(fold["train"], names)
            model.save(directory / "model")
            values = model.predict(test)
            predicted = test.with_columns(
                pl.Series("prediction", values),
                pl.lit(fold["fitted_at"]).alias("model_available_at"),
                pl.lit(fold["train"]["label_known_at"].max()).alias("train_label_max"),
                pl.lit(number).alias("window"),
            )
            if not (predicted["train_label_max"] < predicted["model_available_at"]).all():
                raise ValueError("Futures label leakage")
            predictions.append(predicted)
            score_book = {
                (r["prediction_at"], r["contract"]): {
                    k: r[k] for k in ("prediction", "model_available_at", "train_label_max")
                }
                for r in predicted.to_dicts()
            }
            predictive = {
                "in_sample": evaluate(fold["train"], model.predict(fold["train"]), spec.objective),
                "inner_validation": evaluate(
                    fold["validation"], model.predict(fold["validation"]), spec.objective
                ),
                "search_validation": evaluate(test, values, spec.objective),
            }
            for metrics in predictive.values():
                metrics["error_target"] = definition["target"]
                metrics["within_session_temporal_rank_correlation"] = metrics[
                    "rank_information_coefficient"
                ]
                metrics["rank_information_coefficient"] = None
                metrics["rank_ic_sessions"] = 0
            if definition["target"] == "breakout_continuation":
                predictive["search_validation"]["directional_accuracy"] = None
                predictive["search_validation"]["continuation_accuracy"] = float(
                    np.mean((values >= 0.5) == test["target_class"].to_numpy())
                )
        kwargs = definition["strategy"].copy()
        strategy = FuturesStrategy(
            features,
            contracts,
            family=family,
            scores=score_book,
            classification=definition["target"] in ("direction", "breakout_continuation"),
            prediction_target=definition["target"],
            allowed_times=test["prediction_at"].to_list(),
            **kwargs,
        )
        metadata = {
            "tradable": True,
            "price_basis": "actual_contract_unadjusted",
            "snapshots": seal["snapshots"],
            "synthetic": seal["synthetic"],
            "calendar": seal.get("calendar", {"mode": "rth"}),
            "holdout_start": definition["holdout_start"],
        }
        result = run_futures_backtest(market, contracts, strategy, config=config, metadata=metadata)
        benchmark = run_futures_backtest(
            market,
            contracts,
            FuturesStrategy(
                features,
                contracts,
                family="buy_hold",
                threshold=0,
                maximum_holding_minutes=1440,
                stop_loss=0.99,
                take_profit=0.99,
                allowed_times=test["prediction_at"].to_list(),
            ),
            config=config,
            metadata=metadata,
        )
        write_json(directory / "backtest.json", result)
        write_json(directory / "benchmark.json", benchmark)
        stresses = {}
        if family == "ml":
            stressed = replace(
                config, costs=FuturesCosts(**{k: v * 2 for k, v in asdict(config.costs).items()})
            )
            stressed_strategy = FuturesStrategy(
                features,
                contracts,
                family=family,
                scores=score_book,
                classification=definition["target"] in ("direction", "breakout_continuation"),
                prediction_target=definition["target"],
                allowed_times=test["prediction_at"].to_list(),
                **kwargs,
            )
            stress = run_futures_backtest(
                market, contracts, stressed_strategy, config=stressed, metadata=metadata
            )
            write_json(directory / "double-costs.json", stress)
            stresses["double_costs"] = stress["performance"]
        values = [r["bar_return"] for r in result["equity"]]
        returns.append(values)
        window = {
            "number": number,
            "performance": result["performance"],
            "benchmark": benchmark["performance"],
            "predictive": predictive,
            "training_start": fold["train"]["prediction_at"].min(),
            "training_end": fold["train"]["prediction_at"].max(),
            "train_label_max": fold["train"]["label_known_at"].max(),
            "fitted_at": fold["fitted_at"],
            "inner_validation_start": fold["validation"]["prediction_at"].min(),
            "prediction_start": test["prediction_at"].min(),
            "prediction_end": test["prediction_at"].max(),
            "label_known_max": test["label_known_at"].max(),
            "purged_train": fold["purged_train"],
            "purged_validation": fold["purged_validation"],
            "cost_stress": stresses,
            "margin_halts": len(result["halts"]),
            "final_positions": result["final_positions"],
            "evaluation_role": "search_validation",
        }
        windows.append(window)
        write_json(
            output / "progress.json",
            {
                "completed_windows": len(windows),
                "total_windows": len(folds),
                "intermediate_score": float(
                    np.mean([w["performance"]["total_return"] for w in windows])
                ),
            },
        )
        if progress_handshake and len(windows) < len(folds):
            until = time.monotonic() + 15
            while not (output / f"ack-{len(windows)}").exists():
                if (output / "cancel").exists():
                    raise InterruptedError("Futures pruning requested")
                if time.monotonic() >= until:
                    raise TimeoutError("Futures controller stopped acknowledging folds")
                time.sleep(0.02)
    if predictions:
        pl.concat(predictions).write_parquet(output / "predictions.parquet")
    average = float(np.mean([w["performance"]["total_return"] for w in windows]))
    excess = float(
        np.mean(
            [w["performance"]["total_return"] - w["benchmark"]["total_return"] for w in windows]
        )
    )
    independent_days = sum(w["performance"]["sessions"] for w in windows)
    reasons = []
    if average <= 0:
        reasons.append("nonpositive_net_return")
    if excess <= 0:
        reasons.append("underperformed_contract_benchmark")
    if independent_days < 252:
        reasons.append("insufficient_independent_sessions")
    reasons.append("uncertified_historical_margin_and_data_scope")
    summary = {
        "score": average - 0.5 * max(abs(w["performance"]["maximum_drawdown"]) for w in windows),
        "objective": average - 1,
        "eligible": False,
        "rejection_reasons": reasons,
        "mean_validation_return": average,
        "mean_benchmark_excess": excess,
        "validation_windows": len(windows),
        "independent_sessions": independent_days,
        "fills": sum(w["performance"]["fill_count"] for w in windows),
    }
    result = {
        "definition": definition,
        "selected_features": names,
        "windows": windows,
        "summary": summary,
        "research_status": "REJECTED" if average <= 0 or excess <= 0 else "INSUFFICIENT_EVIDENCE",
        "conditional_minute_uncertainty": uncertainty(
            returns,
            replications=100,
            block_length=min(15, min(map(len, returns))),
            seed=definition["model"]["seed"],
        )
        if min(map(len, returns)) >= 15
        and all(v is not None and v > -1 for f in returns for v in f)
        else None,
        "final_holdout": "not_read_or_evaluated",
        "synthetic": seal["synthetic"],
        "warnings": [
            (
                "Two/few daily observations do not justify "
                "independent significance or paper promotion."
            ),
            (
                "Minute bootstrap is conditional within "
                "observed sessions, not independent-session evidence."
            ),
            "Margins/costs and session settlement proxies are declared assumptions.",
        ],
    }
    write_json(output / "result.json", result)
    return result
