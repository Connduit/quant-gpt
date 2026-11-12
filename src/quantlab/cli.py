import argparse
import json
import logging
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

from quantlab.config import load_settings
from quantlab.data.ingestion import ingest
from quantlab.data.providers.base import DataRequest
from quantlab.data.providers.fixture import FixtureProvider
from quantlab.data.providers.stooq import StooqProvider
from quantlab.data.storage import SnapshotStore
from quantlab.logging import configure_logging


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Quant Research Lab: daily equities data")
    result.add_argument("--config", type=Path, help="TOML configuration file")
    result.add_argument("--data-dir", type=Path, help="Override snapshot storage location")
    commands = result.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Download and validate inclusive daily dates")
    download.add_argument("symbol")
    download.add_argument("--start", type=date.fromisoformat, required=True)
    download.add_argument("--end", type=date.fromisoformat, required=True)
    download.add_argument("--provider", choices=["stooq", "fixture", "lean"])
    download.add_argument("--refresh", action="store_true", help="Fetch a new vendor revision")
    download.add_argument("--extend", help="Append new sessions to this parent snapshot")
    imported = commands.add_parser(
        "import-csv", help="Import daily OHLCV with declared price basis"
    )
    imported.add_argument("symbol")
    imported.add_argument("--csv", type=Path, required=True)
    imported.add_argument("--source", required=True, help="Dataset provenance label")
    imported.add_argument("--price-basis", choices=["unadjusted", "adjusted"], required=True)
    imported.add_argument("--start", type=date.fromisoformat, required=True)
    imported.add_argument("--end", type=date.fromisoformat, required=True)
    inspect = commands.add_parser("inspect", help="Verify and describe a snapshot")
    inspect.add_argument("snapshot_id")
    query = commands.add_parser("query", help="Run one SELECT against the bars relation")
    query.add_argument("snapshot_id")
    query.add_argument("--sql", default="SELECT * FROM bars ORDER BY session_date")
    backtest = commands.add_parser("backtest", help="Replay a verified daily-equity snapshot")
    backtest.add_argument("snapshot_id")
    backtest.add_argument(
        "--strategy", choices=["momentum", "mean-reversion", "buy-hold"], default="momentum"
    )
    backtest.add_argument("--lookback", type=int, default=20)
    backtest.add_argument("--threshold", help="Fraction, e.g. 0.02 (not a percentage)")
    backtest.add_argument("--shares", default="10", help="Fixed entry and benchmark share quantity")
    backtest.add_argument("--initial-cash", default="100000")
    backtest.add_argument("--commission-per-share", default="0.005")
    backtest.add_argument("--commission-fixed", default="0")
    backtest.add_argument("--minimum-commission", default="0")
    backtest.add_argument("--slippage-bps", default="1")
    backtest.add_argument("--spread-bps", default="0", help="Full bid/ask spread in basis points")
    backtest.add_argument("--actions", type=Path, help="Complete split/dividend JSON ledger")
    backtest.add_argument("--output", type=Path, required=True, help="New report directory")
    research = commands.add_parser(
        "research", help="Run a configured CPU walk-forward ML experiment"
    )
    research.add_argument(
        "--experiment", type=Path, required=True, help="YAML experiment definition"
    )
    research.add_argument(
        "--output", type=Path, required=True, help="New research report directory"
    )
    discovery = commands.add_parser("discovery", help="Bounded strategy discovery")
    sub = discovery.add_subparsers(dest="discovery_command", required=True)
    for name in (
        "run",
        "batch",
        "study",
        "resume",
        "list",
        "compare",
        "reproduce",
        "report",
        "rejected",
    ):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        if name in ("run", "batch", "study", "resume", "reproduce"):
            command.add_argument("--study", type=Path, required=True)
        if name == "run":
            command.add_argument("--parameters", type=Path)
        if name == "batch":
            command.add_argument("--parameters", type=Path, nargs="+", required=True)
        if name == "reproduce":
            command.add_argument("attempt_id")
    validate = commands.add_parser("validate", help="Statistical research validation")
    validation_sub = validate.add_subparsers(dest="validation_command", required=True)
    for name in (
        "run",
        "walk-forward",
        "robustness",
        "confidence-intervals",
        "multiple-testing",
        "report",
        "compare",
        "list",
        "rejected",
        "eligible",
    ):
        command = validation_sub.add_parser(name)
        if name in ("run", "walk-forward", "robustness"):
            command.add_argument("--validation-config", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--reports", type=Path, nargs="+", required=True)
    portfolio = commands.add_parser("portfolio", help="Multi-strategy research portfolios")
    portfolio_sub = portfolio.add_subparsers(dest="portfolio_command", required=True)
    for name in ("backtest", "stress", "report", "risk", "strategies"):
        command = portfolio_sub.add_parser(name)
        if name in ("backtest", "stress"):
            command.add_argument("--portfolio-config", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--report", type=Path, required=True)
    create = portfolio_sub.add_parser("create")
    create.add_argument("--output-config", type=Path, required=True)
    create.add_argument("--source-validation", type=Path, required=True)
    create.add_argument("--verified-inputs", type=Path, required=True)
    create.add_argument("--start", required=True)
    create.add_argument("--end", required=True)
    register = portfolio_sub.add_parser("register")
    register.add_argument("--portfolio-config", type=Path, required=True)
    register.add_argument("--name", required=True)
    register.add_argument("--strategy-id", required=True)
    allocation = portfolio_sub.add_parser("allocate")
    allocation.add_argument("--portfolio-config", type=Path, required=True)
    allocation.add_argument(
        "--method",
        choices=("equal", "fixed", "inverse_volatility", "risk_parity", "volatility_target"),
        required=True,
    )
    dashboard = commands.add_parser("dashboard", help="Authenticated curated research dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8000)
    paper = commands.add_parser("paper", help="Simulated execution and experimental replay")
    paper_sub = paper.add_subparsers(dest="paper_command", required=True)
    for name in (
        "positions",
        "orders",
        "fills",
        "equity",
        "strategies",
        "logs",
        "report",
        "pause",
        "resume",
        "stop",
        "kill",
        "reset-kill",
        "connect",
        "disconnect",
    ):
        command = paper_sub.add_parser(name)
        command.add_argument("--database", type=Path, required=True)
        if name in ("pause", "resume", "stop", "kill", "reset-kill", "connect", "disconnect"):
            command.add_argument("--strategy")
            command.add_argument("--reason", required=True)
    command = paper_sub.add_parser("start")
    command.add_argument("--paper-config", type=Path, required=True)
    command = paper_sub.add_parser("replay")
    command.add_argument("--output", type=Path, required=True)
    futures = commands.add_parser("futures", help="Contract-aware futures research only")
    future_sub = futures.add_subparsers(dest="futures_command", required=True)
    future_sub.add_parser("specifications")
    command = future_sub.add_parser("import")
    command.add_argument("--store", type=Path, required=True)
    command.add_argument("--contracts", type=Path, required=True)
    command.add_argument("--contract", required=True)
    command.add_argument("--start", required=True)
    command.add_argument("--end", required=True)
    command.add_argument("--provider", choices=("lean", "databento", "csv"), required=True)
    command.add_argument("--csv", type=Path)
    command.add_argument("--source")
    command.add_argument("--synthetic", action="store_true")
    command.add_argument("--raw-contract-prices", action="store_true")
    command.add_argument("--include-auxiliary", action="store_true")
    command.add_argument("--allow-sparse", action="store_true")
    command.add_argument("--maximum-download-cost", type=float, default=0)
    for name in ("inspect", "query", "validate-history"):
        command = future_sub.add_parser(name)
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("snapshot")
        if name == "query":
            command.add_argument("--sql", required=True)
    for name in ("research", "train", "discover", "resume"):
        command = future_sub.add_parser(name)
        command.add_argument("--research-config", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    for name in ("report", "validation-report"):
        command = future_sub.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
    for name in ("continuous", "backtest"):
        command = future_sub.add_parser(name)
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("--snapshots", nargs="+", required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "continuous":
            command.add_argument(
                "--roll-method", choices=("calendar", "volume"), default="calendar"
            )
            command.add_argument("--roll-days", type=int, default=5)
            command.add_argument("--back-adjust", action="store_true")
        else:
            command.add_argument(
                "--family",
                choices=("momentum", "vwap", "opening_range", "regime", "buy_hold"),
                default="momentum",
            )
            command.add_argument("--holdout-start", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    configure_logging("INFO")
    try:
        settings = load_settings(args.config)
        configure_logging(settings.log_level)
        store = SnapshotStore(args.data_dir or settings.data_dir)
        if args.command == "dashboard":
            import os

            import uvicorn

            from quantlab.web.app import from_environment

            os.environ["QUANTLAB_BIND_HOST"] = args.host
            app = from_environment()
            uvicorn.run(app, host=args.host, port=args.port)
            return 0
        if args.command == "paper":
            from quantlab.paper.cli import execute

            return execute(args)
        if args.command == "futures":
            from quantlab.futures.cli import execute

            return execute(args)
        if args.command == "portfolio":
            from quantlab.portfolio.cli import execute

            return execute(args)
        if args.command == "validate":
            from quantlab.statistical.cli import execute

            return execute(args)
        if args.command == "discovery":
            try:
                from quantlab.discovery.cli import execute
            except ImportError as exc:
                raise ValueError("Install discovery dependencies: uv sync --all-extras") from exc
            return execute(args)
        elif args.command in ("download", "import-csv"):
            if args.command == "import-csv":
                from quantlab.data.providers.csv import CsvProvider

                provider = CsvProvider(args.csv, args.source, args.price_basis)
                refresh, extend = True, None
            else:
                provider_name = args.provider or settings.provider
                from quantlab.data.providers.lean import LeanProvider

                provider = (
                    LeanProvider(timeout=settings.timeout_seconds)
                    if provider_name == "lean"
                    else FixtureProvider()
                    if provider_name == "fixture"
                    else StooqProvider(settings.timeout_seconds)
                )
                refresh, extend = args.refresh, args.extend
            request = DataRequest(args.symbol, args.start, args.end)
            snapshot_id, cached = ingest(provider, request, store, refresh, extend)
            print(
                json.dumps(
                    {
                        "snapshot_id": snapshot_id,
                        "cached": cached,
                        "manifest": store.manifest(snapshot_id),
                    }
                )
            )
        elif args.command == "inspect":
            metadata = store.manifest(args.snapshot_id)
            summary = store.query(
                args.snapshot_id,
                """
                SELECT count(*) AS rows, min(session_date) AS first_session,
                       max(session_date) AS last_session, sum(volume) AS total_volume
                FROM bars
            """,
            )
            print(json.dumps({"manifest": metadata, "summary": summary.to_dicts()}, default=str))
        elif args.command == "query":
            print(store.query(args.snapshot_id, args.sql).write_json())
        elif args.command == "research":
            try:
                from quantlab.research.runner import run_experiment
            except ImportError as exc:
                raise ValueError(
                    "Install research dependencies: uv sync --extra ml --extra dev"
                ) from exc
            report = run_experiment(args.experiment, args.output)
            print(
                json.dumps(
                    {
                        "output": str(args.output),
                        "synthetic": report["synthetic"],
                        "conclusion": report["conclusion"],
                        "folds": len(report["folds"]),
                    }
                )
            )
        elif args.command == "backtest":
            from quantlab.backtesting.actions import CorporateActions
            from quantlab.backtesting.data import DailyData
            from quantlab.backtesting.engine import BacktestConfig, run_backtest
            from quantlab.backtesting.models import Costs, decimal
            from quantlab.backtesting.report import dumps, export_report
            from quantlab.strategies.baselines import BuyAndHold, MeanReversion, Momentum

            actions = CorporateActions.load(args.actions) if args.actions else None
            data = DailyData.from_snapshot(store, args.snapshot_id, actions)
            shares = decimal(args.shares)
            costs = Costs(
                args.commission_per_share,
                args.commission_fixed,
                args.minimum_commission,
                args.slippage_bps,
                args.spread_bps,
            )
            config = BacktestConfig(decimal(args.initial_cash), costs)
            if args.strategy == "buy-hold":
                strategy = BuyAndHold(shares)
            else:
                cls = Momentum if args.strategy == "momentum" else MeanReversion
                threshold = (
                    args.threshold
                    if args.threshold is not None
                    else ("0" if args.strategy == "momentum" else "0.02")
                )
                strategy = cls(args.lookback, shares, decimal(threshold))
            result = run_backtest(data, strategy, config)
            benchmark = run_backtest(data, BuyAndHold(shares), config)
            report = export_report(result, benchmark, args.output)
            logging.getLogger("quantlab").info(
                "Exported hypothetical backtest", extra={"event": "backtest_exported"}
            )
            print(
                dumps(
                    {
                        "output": str(args.output),
                        "run_id": report["run_id"],
                        "performance": report["performance"],
                        "benchmark_performance": report["benchmark_performance"],
                        "synthetic": data.manifest["synthetic"],
                    }
                )
            )
    except (ValueError, TypeError, OSError, duckdb.Error, pl.exceptions.PolarsError) as exc:
        logging.getLogger("quantlab").error(str(exc), extra={"event": "command_failed"})
        return 1
    return 0
