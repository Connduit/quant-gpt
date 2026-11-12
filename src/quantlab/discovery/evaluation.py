"""Transparent, heuristic ranking over search-validation windows, never final tests."""

import math
import statistics
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import polars as pl

from quantlab.backtesting.data import MarketData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, decimal
from quantlab.backtesting.report import export_report
from quantlab.discovery.common import code_version, write_json
from quantlab.discovery.config import Eligibility, ScoreWeights
from quantlab.discovery.data import worker_data
from quantlab.ml.evaluation import evaluate
from quantlab.ml.models import ModelSpec, ResearchModel
from quantlab.ml.validation import walk_forward
from quantlab.research.config import RankingConfig
from quantlab.strategies.ranking import RankingStrategy


def summarize(windows: list[dict], eligibility: Eligibility, weights: ScoreWeights):
    returns = [w["performance"]["total_return"] for w in windows]
    excess = [w["performance"]["total_return"] - w["benchmark"]["total_return"] for w in windows]
    deviation = statistics.pstdev(excess) if len(excess) > 1 else 0
    mean_excess = statistics.mean(excess)
    baseline_excess = statistics.mean(
        w["performance"]["total_return"]
        - max(
            [
                w["benchmark"]["total_return"],
                *(b["total_return"] for b in w.get("baselines", {}).values()),
            ]
        )
        for w in windows
    )
    mean_turnover = statistics.mean(w["performance"]["gross_turnover"] for w in windows)
    max_drawdown = max(abs(w["performance"]["maximum_drawdown"]) for w in windows)
    cost_rate = statistics.mean(w["cost_rate"] for w in windows)
    stress_degradation = max(
        (
            w["performance"]["total_return"] - s["total_return"]
            for w in windows
            for s in w["cost_stress"].values()
        ),
        default=0,
    )
    gains = [p for w in windows for p in w["exit_profits"] if p > 0]
    concentration = max(gains) / sum(gains) if gains else None
    positive_fraction = sum(r > 0 for r in excess) / len(excess)
    fills = sum(w["performance"]["fill_count"] for w in windows)
    exits = sum(w["performance"]["exit_fill_count"] for w in windows)
    reasons = []
    for condition, text in (
        (len(windows) < eligibility.minimum_windows, "too_few_validation_windows"),
        (fills < eligibility.minimum_fills, "too_few_fills"),
        (exits < eligibility.minimum_exit_fills, "too_few_exit_fills"),
        (max_drawdown > eligibility.maximum_drawdown, "excessive_drawdown"),
        (mean_turnover > eligibility.maximum_turnover, "excessive_turnover"),
        (deviation > eligibility.maximum_window_excess_std, "unstable_window_returns"),
        (
            positive_fraction < eligibility.minimum_positive_window_fraction,
            "too_few_positive_excess_windows",
        ),
        (mean_excess < eligibility.minimum_mean_excess, "insufficient_excess_return"),
        (
            baseline_excess < eligibility.minimum_mean_baseline_excess,
            "weaker_than_simple_baselines",
        ),
        (stress_degradation > eligibility.maximum_cost_degradation, "cost_sensitive"),
        (
            concentration is not None
            and concentration > eligibility.maximum_top_trade_profit_share,
            "profit_concentrated",
        ),
    ):
        if condition:
            reasons.append(text)
    skill = statistics.mean(w["predictive_skill"] for w in windows)
    bounded_sharpe = statistics.mean(
        math.tanh((w["performance"]["sharpe_ratio"] or 0) / 3) for w in windows
    )
    terms = {
        "excess_return": weights.excess_return * mean_excess,
        "predictive_skill": weights.predictive_skill * skill,
        "sharpe": weights.sharpe * bounded_sharpe,
        "drawdown": -weights.drawdown * max_drawdown,
        "turnover": -weights.turnover * mean_turnover,
        "costs": -weights.costs * cost_rate,
        "instability": -weights.instability * deviation,
    }
    raw = sum(terms.values())
    metrics = {}
    for name in ("annualized_return", "sharpe_ratio", "sortino_ratio", "profit_factor", "win_rate"):
        values = [
            w["performance"].get(name) for w in windows if w["performance"].get(name) is not None
        ]
        metrics[f"mean_{name}"] = statistics.mean(values) if values else None
    return {
        **metrics,
        "eligible": not reasons,
        "rejection_reasons": reasons,
        "score": raw,
        "objective": raw - (weights.rejection_penalty if reasons else 0),
        "score_terms": terms,
        "mean_validation_return": statistics.mean(returns),
        "mean_excess_return": mean_excess,
        "mean_baseline_excess": baseline_excess,
        "window_excess_std": deviation,
        "positive_window_fraction": positive_fraction,
        "worst_drawdown": max_drawdown,
        "mean_turnover": mean_turnover,
        "cost_rate": cost_rate,
        "cost_degradation": stress_degradation,
        "top_trade_profit_share": concentration,
        "fills": fills,
        "exit_fills": exits,
        "validation_windows": len(windows),
        "thresholds_are_heuristics": True,
    }


def evaluate_candidate(definition: dict, output: Path, *, progress_handshake=False):
    if code_version()["source_sha256"] != definition["source_sha256"]:
        raise ValueError("Code changed since study preparation; trial cancelled")
    feeds, frame, features, seal = worker_data(definition)
    model_spec = ModelSpec(**definition["model"])
    required = "classification" if definition["target"] == "direction" else "regression"
    if model_spec.objective != required or (
        model_spec.type == "logistic" and required != "classification"
    ):
        raise ValueError("Incompatible model and prediction target")
    ranking = RankingConfig(
        **{**definition["strategy"], "lower_is_better": definition["target"] == "volatility"}
    )
    eligibility, weights = (
        Eligibility(**definition["eligibility"]),
        ScoreWeights(**definition["score"]),
    )
    folds = list(
        walk_forward(
            frame,
            definition["training_sessions"],
            definition["validation_sessions"],
            definition["test_sessions"],
            definition["expanding"],
            definition["embargo_sessions"],
        )
    )
    if len(folds) < eligibility.minimum_windows:
        raise ValueError("Multiple independent chronological validation windows are required")
    windows = []
    prediction_frames = []
    for index, fold in enumerate(folds):
        original_rows = fold.test.height
        if index + 1 < len(folds):
            cutoff = folds[index + 1].test["prediction_at"].min()
            fold = replace(fold, test=fold.test.filter(pl.col("boundary_known_at") < cutoff))
        if fold.test.is_empty():
            raise ValueError("Validation window is too short after boundary label purging")
        if (output / "cancel").exists():
            raise InterruptedError("Pruning requested at validation boundary")
        directory = output / f"window-{fold.number}"
        directory.mkdir()
        model = ResearchModel(model_spec).fit(fold.train, features)
        model.save(directory / "model")
        scores = model.predict(fold.test)
        predicted = fold.test.with_columns(
            pl.Series("prediction", scores, dtype=pl.Float64),
            pl.lit(fold.number).alias("window"),
            pl.lit(fold.fitted_at).alias("model_available_at"),
            pl.lit(fold.train["label_known_at"].max()).alias("train_label_max"),
        )
        if not (predicted["train_label_max"] < predicted["model_available_at"]).all():
            raise ValueError("Suspected training-label leakage")
        prediction_frames.append(predicted)
        first, last = predicted["session_date"].min(), predicted["execution_at"].max().date()
        market = MarketData(
            tuple(
                replace(d, bars=tuple(b for b in d.bars if first <= b.session_date <= last))
                for d in feeds.values()
            )
        )
        execution = BacktestConfig(
            decimal(definition["initial_cash"]), Costs(**definition["execution"])
        )
        rows = predicted.to_dicts()

        def replay(mode, costs=execution.costs, market=market, rows=rows, execution=execution):
            return run_backtest(
                market,
                RankingStrategy(
                    rows, tuple(definition["universe"]), "SPY", ranking, mode, model_spec.seed
                ),
                replace(execution, costs=costs),
            )

        primary, benchmark = replay("ml"), replay("spy_buy_hold")
        export_report(
            primary,
            benchmark,
            directory / "backtest",
            benchmark_policy="SPY_search_validation_with_cash_reserve",
        )
        baselines = {
            mode: replay(mode).metrics
            for mode in ("random", "momentum", "mean_reversion", "equal_weight")
        }
        cost_stress = {}
        for multiplier in definition["cost_multipliers"]:
            stressed = Costs(
                **{
                    name: value * decimal(multiplier)
                    for name, value in asdict(execution.costs).items()
                }
            )
            stressed_result = replay("ml", stressed)
            cost_stress[str(multiplier)] = stressed_result.metrics
            # Preserve the stressed path independently of the base report.
            write_json(
                directory / f"cost-stress-{multiplier}.json",
                {
                    "performance": stressed_result.metrics,
                    "orders": stressed_result.orders,
                    "equity": stressed_result.equity,
                    "trades": stressed_result.trades,
                },
            )
        predictive = evaluate(fold.test, scores, model_spec.objective)
        train = evaluate(fold.train, model.predict(fold.train), model_spec.objective)
        inner = evaluate(fold.validation, model.predict(fold.validation), model_spec.objective)
        if definition["target"] == "volatility":
            for metrics in (predictive, train, inner):
                metrics["directional_accuracy"] = None
        target = "target_class" if required == "classification" else "target"
        y = fold.test[target].to_numpy()
        baseline_error = float(np.mean((y - (0.5 if required == "classification" else 0)) ** 2))
        skill = (
            float(np.clip(1 - predictive["mean_squared_error"] / baseline_error, -1, 1))
            if baseline_error
            else 0
        )
        total_cost = sum(
            float(primary.metrics[k]) for k in ("commissions", "spread_cost", "slippage_cost")
        )
        window = {
            "number": fold.number,
            "evaluation_role": "search_validation",
            "performance": primary.metrics,
            "benchmark": benchmark.metrics,
            "baselines": baselines,
            "in_sample": train,
            "inner_validation": inner,
            "search_validation": predictive,
            "feature_importance": model.importance(),
            "predictive_skill": skill,
            "cost_stress": cost_stress,
            "cost_rate": total_cost / float(execution.initial_cash),
            "exit_profits": [
                float(t["realized_pnl"]) for t in primary.trades if t["side"] == "sell"
            ],
            "market_environment": "SPY_up"
            if benchmark.metrics["total_return"] >= 0
            else "SPY_down",
            "fitted_at": fold.fitted_at,
            "train_label_max": fold.train["label_known_at"].max(),
            "validation_label_max": fold.validation["label_known_at"].max(),
            "prediction_start": fold.test["prediction_at"].min(),
            "prediction_end": fold.test["prediction_at"].max(),
            "purged_train": fold.purged_train,
            "purged_inner_validation": fold.purged_validation,
            "purged_window_boundary": original_rows - fold.test.height,
            "label_known_max": fold.test["label_known_at"].max(),
            "boundary_known_max": fold.test["boundary_known_at"].max(),
            "fill_count": len(primary.trades),
        }
        windows.append(window)
        partial = summarize(windows, eligibility, weights)
        write_json(
            output / "progress.json",
            {
                "completed_windows": len(windows),
                "total_windows": len(folds),
                "intermediate_score": partial["score"],
            },
        )
        if progress_handshake and len(windows) < len(folds):
            deadline = time.monotonic() + 15
            while not (output / f"ack-{len(windows)}").exists():
                if (output / "cancel").exists():
                    raise InterruptedError("Pruning requested at validation boundary")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Controller stopped acknowledging validation boundaries")
                time.sleep(0.02)
    pl.concat(prediction_frames).write_parquet(output / "predictions.parquet")
    summary = summarize(windows, eligibility, weights)
    report = {
        "definition": definition,
        "selected_features": features,
        "windows": windows,
        "summary": summary,
        "holdout": {
            "status": "not_accessible_to_trials",
            "start": seal["holdout_start"],
            "excluded_sessions": seal["holdout_sessions_excluded"],
        },
        "synthetic": seal["synthetic"],
        "action_coverage": seal.get("action_coverage", {}),
        "evaluation_role": "search_validation",
        "warnings": [
            "Search-validation results are not independent final tests.",
            "Multiple testing and selection bias remain; eligibility thresholds are heuristics.",
            "Static supplied universes may be survivor-biased; no verified trading edge.",
            "Daily cash-equity model; data/execution limitations from Milestones 1-3 apply.",
        ],
    }
    write_json(output / "result.json", report)
    return report
