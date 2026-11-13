"""Cost-sensitive, reproducible simulation of saved out-of-sample predictions."""

import csv
import statistics
import time
from bisect import bisect_right
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from quantlab.backtesting.data import MarketData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, decimal
from quantlab.backtesting.report import dumps, export_report
from quantlab.discovery.registry import Registry
from quantlab.profitability.inputs import load_execution_feeds, load_saved_predictions, sha
from quantlab.profitability.strategy import PredictionStrategy, StrategyPolicy
from quantlab.statistical.statistics import deflated_sharpe, uncertainty

COST_SCENARIO_MULTIPLIERS = {"low": 0.5, "baseline": 1, "high": 2}


def grouped_returns(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(str(row["session_date"])[:key], []).append(float(row["daily_return"]))
    return [
        {
            "period": name,
            "net_return": float(np.prod(1 + np.array(values)) - 1),
            "sessions": len(values),
        }
        for name, values in sorted(groups.items())
    ]


def summary(result, benchmark, gross):
    costs = {
        name: float(result.metrics[name])
        for name in ("commissions", "spread_cost", "slippage_cost", "market_impact_cost")
    }
    rows = result.equity
    regimes = {"SPY_up": [], "SPY_down": [], "SPY_flat": []}
    for row, reference in zip(rows, benchmark.equity, strict=True):
        state = (
            "SPY_up"
            if reference["daily_return"] > 0
            else "SPY_down"
            if reference["daily_return"] < 0
            else "SPY_flat"
        )
        regimes[state].append(row["daily_return"])
    return {
        "net": result.metrics,
        "gross_zero_cost_rerun": gross.metrics,
        "gross_definition": "Independent zero-cost rerun; fills may differ. Not net plus costs.",
        "costs": {**costs, "total": sum(costs.values())},
        "excess_total_return_vs_spy": result.metrics["total_return"]
        - benchmark.metrics["total_return"],
        "monthly_returns": grouped_returns(rows, 7),
        "yearly_returns": grouped_returns(rows, 4),
        "regimes": [
            {
                "regime": name,
                "sessions": len(values),
                "conditional_mean_daily_return": statistics.mean(values) if values else None,
            }
            for name, values in regimes.items()
        ],
        "regime_definition": "Ex-post daily SPY path sign; descriptive, never a signal.",
        "order_status_counts": {
            status: sum(o["status"] == status for o in result.orders)
            for status in ("filled", "rejected", "cancelled", "expired")
        },
        "risk_reduced_orders": sum(
            o.get("reason") == "portfolio_risk_reduced" for o in result.orders
        ),
    }


def prepare_market(feeds, rows, request, *, warnings=None):
    reference = feeds["SPY"].bars
    opens = [b.open_time for b in reference]
    by_day = {b.session_date: i for i, b in enumerate(reference)}
    if set(r["symbol"] for r in rows) != set(feeds) - {"SPY"}:
        raise ValueError("Prediction and execution universes differ")
    for row in rows:
        if row["session_date"] not in by_day:
            raise ValueError("Prediction date is absent from execution data")
        index = by_day[row["session_date"]]
        if any(feed.bars[index].available_at > row["prediction_at"] for feed in feeds.values()):
            raise ValueError("Prediction predates its feature-bar availability")
        entry = bisect_right(opens, row["prediction_at"])
        if entry >= len(opens) or opens[entry] != row["execution_at"]:
            raise ValueError(
                "Prediction execution must be the first eligible opening after its signal"
            )
    # Complete cross sections are required: partial signals cannot borrow later data.
    universe = set(feeds) - {"SPY"}
    for day in {r["session_date"] for r in rows}:
        if {r["symbol"] for r in rows if r["session_date"] == day} != universe:
            raise ValueError("Incomplete prediction cross section")
    first = min(r["session_date"] for r in rows)
    last = max(b.session_date for b in reference if b.session_date <= request.end)
    trimmed = tuple(
        replace(feed, bars=tuple(b for b in feed.bars if first <= b.session_date <= last))
        for feed in feeds.values()
    )
    if not 3 <= len(trimmed[0].bars) <= 3000:
        raise ValueError("Evaluation requires 3–3,000 trading sessions")
    # Exploratory replay may continue, but unknown events make profit figures unreliable.
    for feed in trimmed:
        splits = {s.date for s in feed.actions.splits}
        for previous, current in zip(feed.bars, feed.bars[1:], strict=False):
            if (
                not feed.actions.complete
                and current.session_date not in splits
                and abs(float(current.open / previous.close - 1)) >= 0.4
            ):
                if request.research_mode != "exploratory":
                    raise ValueError(
                        "Unexplained raw-price discontinuity; supply corporate-action evidence"
                    )
                if warnings is not None:
                    warnings.append(
                        f"{feed.instrument.symbol} {current.session_date}: unexplained raw-price "
                        f"gap of {float(current.open / previous.close - 1):.1%}. "
                        "Possible missing corporate action; no split or dividend was inferred. "
                        "Simulated profit/loss is unreliable until event evidence is supplied."
                    )
    return MarketData(trimmed)


def run_profitability(source: Path, request, output: Path, registry_root: Path):
    registry = Registry(registry_root)
    registry.recover()
    definition = {
        "hypothesis": "Saved OOS signals yield positive net risk-constrained performance",
        "source_job_id": request.source_job_id,
        "request": request.model_dump(mode="json"),
        "source_result_sha256": sha(source / "result.json")
        if (source / "result.json").is_file()
        else None,
    }
    _, attempt, created = registry.claim(definition, role="profitability", reproduce=True)
    if not created:
        raise ValueError("Unable to register profitability attempt")
    try:
        baseline_costs = Costs(
            commission_per_share=request.commission_per_share,
            spread_bps=request.spread_bps,
            slippage_bps=request.slippage_bps,
            market_impact_bps=request.market_impact_bps,
        )
        cost_scenarios = {
            name: Costs(
                **{
                    key: value * decimal(multiplier)
                    for key, value in asdict(baseline_costs).items()
                }
            )
            for name, multiplier in COST_SCENARIO_MULTIPLIERS.items()
        }
        source_result, rows, versions = load_saved_predictions(source, request)
        feeds, blockers = load_execution_feeds(source, source_result, request)
        discontinuities = []
        market = prepare_market(feeds, rows, request, warnings=discontinuities)
        blockers.extend(discontinuities)
        universe = tuple(sorted(set(feeds) - {"SPY"}))
        if request.top_n > len(universe):
            raise ValueError("Top holdings cannot exceed the execution stock count")
        policy = StrategyPolicy(
            **{key: getattr(request, key) for key in StrategyPolicy.__dataclass_fields__}
        )
        probability = next(iter(versions.values()))["spec"]["objective"] == "classification"
        if any(
            (v["spec"]["objective"] == "classification") != probability for v in versions.values()
        ):
            raise ValueError("Model objectives differ across saved folds")
        output.mkdir(parents=True, exist_ok=False)
        zero = Costs(0, 0, 0, 0, 0, 0)
        modes = ("ml", "spy_buy_hold", "equal_weight", "momentum", "mean_reversion", "cash")

        def replay(mode, costs, variant=policy):
            # SPY is an 80%-invested buy/hold reference, not an artificially 40%-capped stock.
            if mode in ("spy_buy_hold", "equal_weight"):
                variant = replace(
                    variant, maximum_position_weight=1, maximum_drawdown=1, maximum_daily_loss=1
                )
            return run_backtest(
                market,
                PredictionStrategy(rows, universe, variant, mode, probability=probability),
                BacktestConfig(
                    decimal(request.initial_cash),
                    costs,
                    liquidate_at_end=True,
                    whole_shares=policy.whole_shares,
                ),
            )

        gross = {mode: replay(mode, zero) for mode in modes}
        scenarios, baseline_results = {}, None
        curves_by_scenario = {}
        for name, costs in cost_scenarios.items():
            results = {mode: replay(mode, costs) for mode in modes}
            if name == "baseline":
                baseline_results = results
            summaries = {}
            for mode, result in results.items():
                path = output / name / mode
                exported = export_report(
                    result,
                    results["spy_buy_hold"],
                    path,
                    benchmark_policy="same_period_cash_reserve_SPY_buy_hold_with_terminal_costs",
                )
                summaries[mode] = {
                    **summary(result, results["spy_buy_hold"], gross[mode]),
                    "artifact_directory": f"{name}/{mode}",
                    "run_id": exported["run_id"],
                }
            scenarios[name] = {"assumptions": asdict(costs), "strategies": summaries}
            curves_by_scenario[name] = [
                {
                    "date": str(row["session_date"]),
                    "net_equity": float(row["equity"]),
                    "gross_equity": float(gross["ml"].equity[i]["equity"]),
                    "spy_equity": float(results["spy_buy_hold"].equity[i]["equity"]),
                    "equal_weight_equity": float(results["equal_weight"].equity[i]["equity"]),
                    "drawdown": row["drawdown"],
                }
                for i, row in enumerate(results["ml"].equity)
            ]
        primary = baseline_results["ml"]
        benchmark = baseline_results["spy_buy_hold"]
        daily = [r["daily_return"] for r in primary.equity]
        active = [
            r["daily_return"] - b["daily_return"]
            for r, b in zip(primary.equity, benchmark.equity, strict=True)
        ]
        observations = []
        for fold in sorted({r["fold"] for r in rows}):
            dates = {r["session_date"] for r in rows if r["fold"] == fold}
            selected = [r for r in primary.equity if r["session_date"] in dates]
            if selected:
                observations.append(
                    {
                        "fold": fold,
                        "start": min(dates),
                        "end": max(dates),
                        "sessions": len(selected),
                        "net_return": float(np.prod([1 + r["daily_return"] for r in selected]) - 1),
                    }
                )
        history_count = len(registry.rows()) * (len(modes) * (len(cost_scenarios) + 1) + 4)
        diagnostics = {
            "status": "NOT_VALIDATED",
            "qualified": False,
            "recorded_variants_lower_bound": history_count,
            "history_scope": "Includes retained repeats/failures; external hypotheses unknown",
            "multiple_testing": "External search family unknown; no FDR qualification claimed",
            "final_holdout": "NOT_READ_OR_EVALUATED",
            "independent_confirmation": "NOT_PERFORMED",
        }
        if len(daily) >= 20 and all(r > -1 for r in active):
            diagnostics["active_return_uncertainty"] = uncertainty(
                [active], replications=200, block_length=10, seed=42
            )
            diagnostics["deflated_sharpe_diagnostic"] = deflated_sharpe(daily, history_count)
        variants = {}
        for label, variant in (
            (
                "rebalance_shorter",
                replace(policy, rebalance_sessions=max(1, policy.rebalance_sessions - 1)),
            ),
            (
                "rebalance_longer",
                replace(policy, rebalance_sessions=min(126, policy.rebalance_sessions + 1)),
            ),
            (
                "holding_shorter",
                replace(policy, holding_sessions=max(1, policy.holding_sessions - 1)),
            ),
            (
                "holding_longer",
                replace(policy, holding_sessions=min(252, policy.holding_sessions + 1)),
            ),
        ):
            value = replay("ml", cost_scenarios["baseline"], variant)
            variants[label] = {"policy": asdict(variant), "net": value.metrics}
            (output / f"sensitivity-{label}.json").write_text(
                dumps(
                    {"equity": value.equity, "trades": value.trades, "performance": value.metrics}
                )
            )
        curves = [
            {
                "date": str(row["session_date"]),
                "net_equity": float(row["equity"]),
                "gross_equity": float(gross["ml"].equity[i]["equity"]),
                "spy_equity": float(benchmark.equity[i]["equity"]),
                "equal_weight_equity": float(baseline_results["equal_weight"].equity[i]["equity"]),
                "drawdown": row["drawdown"],
            }
            for i, row in enumerate(primary.equity)
        ]
        with (output / "verified_predictions.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        strongest = max(
            (mode for mode in baseline_results if mode != "ml"),
            key=lambda mode: baseline_results[mode].metrics["total_return"],
        )
        net_return = primary.metrics["total_return"]
        screening = {
            "net_positive_at_baseline_costs": net_return > 0,
            "positive_at_high_costs": scenarios["high"]["strategies"]["ml"]["net"]["total_return"]
            > 0,
            "strongest_simple_baseline": strongest,
            "excess_total_return_vs_strongest": net_return
            - baseline_results[strongest].metrics["total_return"],
            "conclusion": "Net simulated loss at baseline costs."
            if net_return <= 0
            else (
                "Positive simulated net return, but below the strongest simple baseline."
                if net_return <= baseline_results[strongest].metrics["total_return"]
                else "Positive simulated net return above these baselines; still not validated."
            ),
            "exposure_caveat": "Total returns have differing realized risk/exposure.",
        }
        report = {
            "name": "Saved ML strategy profitability evaluation",
            "screening_summary": screening,
            "profitability_warning": (
                "Unreliable profit/loss: unexplained raw-price jumps may be missing corporate "
                "actions. This exploratory replay leaves prices and share counts unchanged; "
                "do not treat its returns or baseline comparisons as evidence of profitability."
                if discontinuities
                else None
            ),
            "unexplained_discontinuities": discontinuities,
            "performance_kind": "exploratory_backtest"
            if blockers or request.research_mode == "exploratory"
            else "development_backtest",
            "qualified": False,
            "promotion_allowed": False,
            "live_enabled": False,
            "source_job_id": request.source_job_id,
            "model": request.model,
            "prediction_integrity": {
                "predictions_sha256": source_result["report"]["predictions_sha256"],
                "model_versions": versions,
                "verified_rows": len(rows),
            },
            "policy": asdict(policy),
            "scenarios": scenarios,
            "equity_curve": curves,
            "equity_curves": curves_by_scenario,
            "prediction_diagnostics": source_result["report"].get("predictive_performance", {}),
            "evaluation_start": str(market.feeds[0].bars[0].session_date),
            "evaluation_end": str(market.feeds[0].bars[-1].session_date),
            "performance_by_fold": observations,
            "parameter_sensitivity": variants,
            "statistical_validation": diagnostics,
            "data_limitations": blockers,
            "trade_preview": primary.trades[:100],
            "trade_count": len(primary.trades),
            "exposure_comparison": {
                mode: value.metrics["average_gross_exposure"]
                for mode, value in baseline_results.items()
            },
            "limitations": [
                "Hypothetical executable cash simulation, not live profit or future profitability.",
                "Fixed-bps impact is an assumption, not calibrated capacity.",
                "Full next-open fills; no book/queue, tax, financing, interest or cash-in-lieu.",
                "Missing events are UNKNOWN and can invalidate exploratory results.",
                "SPY/equal-weight: same cash; no stock cap/drawdown stop. Compare exposure.",
                "Regimes/bootstrap are descriptive diagnostics, not independent confirmation.",
                "Final positions liquidated at the last scheduled open, with transaction costs.",
            ],
        }
        (output / "profitability_report.json").write_text(dumps(report) + "\n")
        registry.update(
            attempt["id"],
            status="COMPLETE",
            ended=time.time(),
            result={
                "qualified": False,
                "net_return": primary.metrics["total_return"],
                "report": str(output / "profitability_report.json"),
            },
        )
        return report
    except BaseException as exc:
        registry.update(attempt["id"], status="FAILED", reason=str(exc), ended=time.time())
        raise
