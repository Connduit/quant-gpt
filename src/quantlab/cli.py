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
    download.add_argument("--provider", choices=["stooq", "fixture"])
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
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    configure_logging("INFO")
    try:
        settings = load_settings(args.config)
        configure_logging(settings.log_level)
        store = SnapshotStore(args.data_dir or settings.data_dir)
        if args.command in ("download", "import-csv"):
            if args.command == "import-csv":
                from quantlab.data.providers.csv import CsvProvider

                provider = CsvProvider(args.csv, args.source, args.price_basis)
                refresh, extend = True, None
            else:
                provider_name = args.provider or settings.provider
                provider = (
                    FixtureProvider()
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
