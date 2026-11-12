"""Reproducible multi-strategy research using saved OOS prediction books."""

import copy
import hashlib
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import polars as pl
import yaml

from quantlab.backtesting.actions import CorporateActions
from quantlab.backtesting.data import DailyData, MarketData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs, decimal
from quantlab.backtesting.report import export_report
from quantlab.data.storage import SnapshotStore
from quantlab.discovery.common import code_version, read_json, write_json
from quantlab.portfolio.allocation import diversification
from quantlab.portfolio.book import MultiStrategyBook, Registration
from quantlab.portfolio.risk import RiskLimits
from quantlab.research.config import RankingConfig, strict
from quantlab.strategies.ranking import RankingStrategy


def load_portfolio(path):
    path = Path(path).resolve()
    doc = yaml.safe_load(path.read_text())
    strict(
        doc,
        (
            "name",
            "mode",
            "validation_report",
            "verified_inputs",
            "strategies",
            "start",
            "end",
            "holdout_start",
            "allocation_methods",
            "allocation",
            "risk",
            "rebalance",
            "execution",
            "sectors",
        ),
        "portfolio",
    )
    if doc.get("mode", "research") not in ("research", "paper"):
        raise ValueError("Live mode unavailable")
    for key in ("start", "end", "holdout_start"):
        doc[key] = date.fromisoformat(str(doc[key]))
    if not doc["start"] <= doc["end"] < doc["holdout_start"]:
        raise ValueError("Portfolio must end before final holdout")
    for key in ("validation_report", "verified_inputs"):
        doc[key] = (path.parent / doc[key]).resolve()
    if not doc["strategies"] or len(doc["strategies"]) > 20:
        raise ValueError("Specify 1–20 evaluated strategies")
    if any(
        m not in ("equal", "fixed", "inverse_volatility", "risk_parity", "volatility_target")
        for m in doc["allocation_methods"]
    ):
        raise ValueError("Unknown allocation method")
    RiskLimits(**doc.get("risk", {}))
    return doc


def run_portfolio(config_path, output, *, stress=False):
    config = load_portfolio(config_path)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Portfolio output exists; choose a new directory")
    output.mkdir(parents=True)
    source = read_json(config["validation_report"])
    if source["final_holdout"] != "not_read_or_evaluated" or source["holdout"]["state"] != "SEALED":
        raise ValueError("Validation did not preserve an untouched holdout")
    from quantlab.statistical.holdout import HoldoutVault

    vault = HoldoutVault(config["verified_inputs"].parent / "holdout-vault.sqlite")
    if vault.status(source["holdout"]["id"])["state"] != "SEALED":
        raise ValueError("Current holdout ledger is no longer sealed")
    candidates = {c["strategy_id"]: c for c in source["candidates"]}
    quality = read_json(config["verified_inputs"] / "data_quality.json")
    from quantlab.data.providers.lean import verify_existing_import

    first = next(iter(quality["quality"].values()))
    verify_existing_import(
        config["verified_inputs"],
        date.fromisoformat(first["start"]),
        date.fromisoformat(first["end"]),
        tuple(quality["snapshots"]),
    )
    if date.fromisoformat(first["end"]) >= config["holdout_start"]:
        raise ValueError("Physical data prefix includes holdout")
    store = SnapshotStore(config["verified_inputs"])
    feeds = {
        s: DailyData.from_snapshot(
            store, v["snapshot_id"], CorporateActions.load(Path(v["actions"]))
        )
        for s, v in quality["snapshots"].items()
    }
    feeds = {
        s: replace(
            f, bars=tuple(b for b in f.bars if config["start"] <= b.session_date <= config["end"])
        )
        for s, f in feeds.items()
    }
    market = MarketData(tuple(feeds.values()))
    specs = []
    provenance = []
    for entry in config["strategies"]:
        strict(entry, ("name", "strategy_id", "paper_approved"), "registered strategy")
        c = candidates[entry["strategy_id"]]
        if str(config["holdout_start"]) != c["configuration"]["holdout_start"]:
            raise ValueError("Holdout cutoff mismatch")
        artifact = Path(c["artifact_path"])
        path = artifact / "predictions.parquet"
        result = read_json(artifact / "result.json")
        if result["summary"] != c["result"]["summary"]:
            raise ValueError("Validation artifact no longer matches report")
        frame = pl.read_parquet(path).filter(
            (pl.col("session_date") >= config["start"]) & (pl.col("session_date") <= config["end"])
        )
        if frame.is_empty():
            raise ValueError("No OOS predictions in portfolio period")
        definition = c["configuration"]
        specs.append(
            {
                "name": entry["name"],
                "status": c["status"],
                "approved": entry.get("paper_approved", False),
                "rows": frame.to_dicts(),
                "universe": tuple(definition["universe"]),
                "ranking": RankingConfig(
                    **{
                        **definition["strategy"],
                        "lower_is_better": definition["target"] == "volatility",
                    }
                ),
                "seed": definition["model"]["seed"],
            }
        )
        provenance.append(
            {
                "name": entry["name"],
                "strategy_id": entry["strategy_id"],
                "research_status": c["status"],
                "predictions_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "parent_attempt": c["attempt_id"],
            }
        )
    if len({s["name"] for s in specs}) != len(specs):
        raise ValueError("Duplicate strategy name")
    execution = config.get("execution", {}).copy()
    cash = decimal(execution.pop("initial_cash", "100000"))
    costs = Costs(**execution)
    backtest_config = BacktestConfig(cash, costs)

    def strategy(spec):
        return RankingStrategy(
            copy.deepcopy(spec["rows"]),
            spec["universe"],
            "SPY",
            spec["ranking"],
            "ml",
            spec["seed"],
        )

    standalone = {}
    for spec in specs:
        standalone[spec["name"]] = run_backtest(market, strategy(spec), backtest_config)
    reference = []
    reference_feed = next(iter(feeds.values()))
    for i, bar in enumerate(reference_feed.bars):
        reference.append(
            {
                "available_at": bar.available_at,
                "returns": [float(standalone[s["name"]].equity[i]["daily_return"]) for s in specs],
            }
        )

    def benchmark():
        spec = specs[0]
        return run_backtest(
            market,
            RankingStrategy(
                copy.deepcopy(spec["rows"]),
                spec["universe"],
                "SPY",
                spec["ranking"],
                "spy_buy_hold",
                spec["seed"],
            ),
            backtest_config,
        )

    baseline = benchmark()
    runs = {}
    books = {}
    methods = config["allocation_methods"]
    scenarios = [(m, 1) for m in methods]
    if stress:
        scenarios += [
            ("equal", 2),
            ("inverse_volatility", 2),
            ("equal_liquidity", 1),
            ("equal_rejected_order", 1),
            ("equal_disconnected", 1),
        ]
    for method, cost_multiplier in scenarios:
        key = method if cost_multiplier == 1 else f"{method}_double_costs"
        stress_options = {}
        if method == "equal_liquidity":
            stress_options = {"maximum_participation": 0.00001}
        elif method == "equal_rejected_order":
            stress_options = {"reject_order_ids": (1,)}
        elif method == "equal_disconnected":
            stress_options = {"execution_available": False}
        method = "equal" if method.startswith("equal_") else method
        book = MultiStrategyBook(
            [Registration(s["name"], strategy(s), s["status"], s["approved"]) for s in specs],
            method=method,
            mode=config.get("mode", "research"),
            limits=RiskLimits(**config.get("risk", {})),
            sectors=config.get("sectors", {}),
            reference_history=reference,
            **stress_options,
            **config.get("allocation", {}),
            **config.get("rebalance", {}),
        )
        run_config = replace(
            backtest_config,
            costs=Costs(**{k: v * cost_multiplier for k, v in asdict(costs).items()}),
        )
        result = run_backtest(market, book, run_config)
        # Compare costs consistently inside each artifact package.
        spec = specs[0]
        bench = run_backtest(
            market,
            RankingStrategy(
                copy.deepcopy(spec["rows"]),
                spec["universe"],
                "SPY",
                spec["ranking"],
                "spy_buy_hold",
                spec["seed"],
            ),
            run_config,
        )
        export_report(result, bench, output / key, benchmark_policy="SPY_shared_period_same_costs")
        write_json(output / key / "attribution.json", book.attribution)
        write_json(output / key / "risk-decisions.json", book.risk_decisions)
        write_json(output / key / "allocations.json", book.allocations)
        write_json(output / key / "events.json", book.logs)
        write_json(output / key / "internal-transfers.json", book.internal_transfers)
        books[key] = book
        weights = [book.weights[s["name"]] for s in specs]
        runs[key] = {
            "performance": result.metrics,
            "benchmark": bench.metrics,
            "diversification": diversification(book.history, weights),
            "strategy_pnl": {
                name: float(
                    p.view({s: f.bars[-1].close for s, f in feeds.items()}).equity - p.initial_cash
                )
                for name, p in book.ledgers.items()
            },
            "suspended": [n for n, r in book.registrations.items() if r.suspended],
            "internal_transfer_count": len(book.internal_transfers),
            "risk_decision_counts": {
                d: sum(r["decision"] == d for r in book.risk_decisions)
                for d in ("APPROVED", "REDUCED", "REJECTED")
            },
        }
        total = sum(runs[key]["strategy_pnl"].values())
        if abs(total - float(result.metrics["final_equity"]) + float(cash)) > 1e-7:
            raise ArithmeticError("Final P&L attribution mismatch")
    overlap = {}
    for key, book in books.items():
        shared = {
            s: sum(
                p.positions.get(s, None) is not None and p.positions[s].quantity > 0
                for p in book.ledgers.values()
            )
            for s in feeds
        }
        overlap[key] = {
            "shared_positions": {s: n for s, n in shared.items() if n > 1},
            "warning": "shared names and crisis correlations may defeat diversification",
        }
    report = {
        "configuration": {k: str(v) if isinstance(v, Path) else v for k, v in config.items()},
        "code": code_version(),
        "strategies": provenance,
        "runs": runs,
        "individuals": {n: r.metrics for n, r in standalone.items()},
        "benchmark": baseline.metrics,
        "exposure_overlap": overlap,
        "final_holdout": "not_accessed",
        "mode": config.get("mode", "research"),
        "paper_eligible": [
            p["name"] for p in provenance if p["research_status"] == "VALIDATED_FOR_PAPER_TRADING"
        ],
        "data_sources": quality,
        "stress_scenarios": scenario_analysis(books.get("equal", next(iter(books.values())))),
        "limitations": [
            "Research-only rejected candidates demonstrate mechanics, not a validated portfolio.",
            "Static survivor universe and incomplete corporate-action factor proxies.",
            "Virtual cash claims may borrow internally; only aggregate cash is spendable.",
            "No shorting, leverage, live orders or futures execution in the equity adapter.",
            "Historical correlations and portfolio optimization are not forecasts.",
        ],
    }
    write_json(output / "portfolio.json", report)
    return report


def scenario_analysis(book):
    import numpy as np

    x = np.asarray(book.history, dtype=float)
    if len(x) < 3:
        return {"status": "insufficient_history"}
    weights = np.array(list(book.weights.values()))
    base = x @ weights
    return {
        "kind": "explicitly_hypothetical_diagnostics_not_forecasts",
        "double_volatility": {"worst_daily_return": float(np.min(base * 2))},
        "perfect_loss_correlation": {
            "worst_daily_return": float(np.min(np.min(x, axis=1) * weights.sum()))
        },
        "overnight_gap_minus_10_percent": {
            "equity_loss_fraction_at_max_gross": -0.1 * book.limits.maximum_gross
        },
        "strategy_underperformance": {
            n: float(np.mean(base - x[:, i] * weights[i] - 0.001 * weights[i]))
            for i, n in enumerate(book.registrations)
        },
        "liquidity_or_missing_data": {
            "policy": "reject unavailable/stale instrument data; never forward-fill tradable bars"
        },
        "failed_order": {"policy": "no virtual fill attribution until authoritative fill succeeds"},
        "broker_disconnection": {"status": "not_applicable_offline_research; no broker connector"},
    }
