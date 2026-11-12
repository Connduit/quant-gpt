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
    inspect = commands.add_parser("inspect", help="Verify and describe a snapshot")
    inspect.add_argument("snapshot_id")
    query = commands.add_parser("query", help="Run one SELECT against the bars relation")
    query.add_argument("snapshot_id")
    query.add_argument("--sql", default="SELECT * FROM bars ORDER BY session_date")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    configure_logging("INFO")
    try:
        settings = load_settings(args.config)
        configure_logging(settings.log_level)
        store = SnapshotStore(args.data_dir or settings.data_dir)
        if args.command == "download":
            provider_name = args.provider or settings.provider
            provider = (
                FixtureProvider()
                if provider_name == "fixture"
                else StooqProvider(settings.timeout_seconds)
            )
            request = DataRequest(args.symbol, args.start, args.end)
            snapshot_id, cached = ingest(provider, request, store, args.refresh, args.extend)
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
        else:
            print(store.query(args.snapshot_id, args.sql).write_json())
    except (ValueError, TypeError, OSError, duckdb.Error, pl.exceptions.PolarsError) as exc:
        logging.getLogger("quantlab").error(str(exc), extra={"event": "command_failed"})
        return 1
    return 0
