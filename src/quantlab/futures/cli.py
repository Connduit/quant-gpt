"""Explicit futures data/research operations; no live order command."""

from dataclasses import asdict
from datetime import datetime

import polars as pl
import yaml

from quantlab.backtesting.report import dumps
from quantlab.data.providers.base import Download
from quantlab.discovery.common import read_json, write_json
from quantlab.futures.calendar import calendar_from_dict
from quantlab.futures.continuous import continuous_series
from quantlab.futures.contracts import PRODUCTS, contract_from_dict
from quantlab.futures.engine import run_futures_backtest
from quantlab.futures.features import intraday_features
from quantlab.futures.providers import DatabentoProvider, FuturesRequest, LeanFuturesProvider
from quantlab.futures.research import run_futures_research
from quantlab.futures.storage import FuturesStore, normalize
from quantlab.futures.strategies import FuturesStrategy


def execute(args):
    name = args.futures_command
    if name == "specifications":
        result = {s: {**asdict(p), "tick_value": p.tick_value} for s, p in PRODUCTS.items()}
    elif name == "import":
        document = yaml.safe_load(args.contracts.read_text())
        contract = contract_from_dict(document["contracts"][args.contract])
        calendar = calendar_from_dict(document.get("calendar", {}))
        request = FuturesRequest(
            contract, datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
        )
        if args.provider == "csv":
            if args.csv is None or not args.source:
                raise ValueError("CSV import requires --csv and --source provenance")
            if not args.raw_contract_prices:
                raise ValueError(
                    "Explicit --raw-contract-prices declaration "
                    "required; continuous inputs are forbidden"
                )
            download = Download(
                args.csv.read_bytes(), args.source, "actual_contract_unadjusted", args.synthetic
            )
            provider = None
        else:
            if args.synthetic:
                raise ValueError("Network providers never silently become synthetic")
            provider = (
                LeanFuturesProvider(calendar=calendar, include_auxiliary=args.include_auxiliary)
                if args.provider == "lean"
                else DatabentoProvider(maximum_download_cost=args.maximum_download_cost)
            )
            download = provider.fetch(request)
        frame, quality = normalize(
            download.raw,
            contract,
            calendar=calendar,
            allow_sparse=args.allow_sparse,
            request=request,
        )
        if frame["timestamp"].min() < request.start or frame["timestamp"].max() >= request.end:
            raise ValueError("Downloaded bars outside requested interval")
        if provider is not None:
            quality["source_hashes"] = getattr(provider, "source_hashes", {})
        identifier = FuturesStore(args.store).write(
            frame,
            download.raw,
            contract,
            provider=provider.name if provider else "declared-csv",
            source=download.source,
            synthetic=download.synthetic,
            quality=quality,
        )
        result = {
            "snapshot_id": identifier,
            "rows": frame.height,
            "quality": quality,
            "synthetic": download.synthetic,
        }
    elif name in ("inspect", "query", "validate-history"):
        store = FuturesStore(args.store)
        if name == "query":
            result = store.query(args.snapshot, args.sql).to_dicts()
        elif name == "inspect":
            result = store.manifest(args.snapshot)
        else:
            metadata = store.manifest(args.snapshot)
            frame = store.read(args.snapshot)
            contract = contract_from_dict(metadata["contract"])
            calendar = calendar_from_dict(
                metadata["quality"].get(
                    "calendar_definition", {"mode": metadata["quality"]["session_mode"]}
                )
            )
            q = metadata["quality"]
            declared_request = (
                FuturesRequest(
                    contract,
                    datetime.fromisoformat(q["requested_start"]),
                    datetime.fromisoformat(q["requested_end"]),
                )
                if q.get("requested_start")
                else None
            )
            normalized, quality = normalize(
                (args.store / args.snapshot / "source.csv").read_bytes(),
                contract,
                calendar=calendar,
                allow_sparse=bool(metadata["quality"]["missing_minutes"]),
                request=declared_request,
            )
            if not frame.equals(normalized):
                raise ValueError("Normalized history differs from source")
            result = {
                "snapshot_id": args.snapshot,
                "valid": True,
                "rows": frame.height,
                "quality": quality,
            }
    elif name in ("research", "train", "discover", "resume"):
        report = run_futures_research(args.research_config, args.output, resume=name == "resume")
        result = {
            "output": str(args.output),
            "counts": report["counts"],
            "synthetic": report["synthetic"],
            "results": [
                {k: r[k] for k in ("experiment_id", "role", "status", "summary")}
                for r in report["results"]
            ],
            "failed": report["failed"],
            "final_holdout": report["final_holdout"],
            "paper_trading_shortlist": report["paper_trading_shortlist"],
        }
    elif name in ("report", "validation-report"):
        report = read_json(args.root / "research.json")
        result = (
            report
            if name == "report"
            else {
                "counts": report["counts"],
                "final_holdout": report["final_holdout"],
                "results": [
                    {k: r[k] for k in ("experiment_id", "status", "statistics")}
                    for r in report["results"]
                ],
            }
        )
    else:
        store = FuturesStore(args.store)
        metadata = [store.manifest(s) for s in args.snapshots]
        if len({m["synthetic"] for m in metadata}) != 1:
            raise ValueError("Do not mix invented and real data")
        frame = pl.concat([store.read(s) for s in args.snapshots], how="diagonal_relaxed")
        if frame.select(pl.struct("contract", "timestamp").is_duplicated().any()).item():
            raise ValueError("Duplicate contract revisions cannot be combined")
        contracts = {
            m["contract"]["identifier"]: contract_from_dict(m["contract"]) for m in metadata
        }
        if args.output.exists():
            raise ValueError("Output exists")
        args.output.mkdir(parents=True)
        if name == "continuous":
            series, result = continuous_series(
                frame,
                contracts,
                method=args.roll_method,
                roll_days=args.roll_days,
                back_adjust=args.back_adjust,
            )
            series.write_parquet(args.output / "research-series.parquet")
            write_json(args.output / "series.json", result)
        else:
            cutoff = datetime.fromisoformat(args.holdout_start)
            if frame["available_at"].max() >= cutoff:
                raise ValueError("Backtest input includes protected data")
            features = intraday_features(frame)
            strategy = FuturesStrategy(features, contracts, family=args.family)
            result = run_futures_backtest(
                frame,
                contracts,
                strategy,
                metadata={
                    "tradable": True,
                    "price_basis": "actual_contract_unadjusted",
                    "synthetic": metadata[0]["synthetic"],
                    "calendar": metadata[0]["quality"].get(
                        "calendar_definition", {"mode": metadata[0]["quality"]["session_mode"]}
                    ),
                },
            )
            result["evaluation_role"] = "full_permitted_research_range_not_an_independent_OOS_claim"
            write_json(args.output / "backtest.json", result)
            result = {
                "output": str(args.output),
                "performance": result["performance"],
                "evaluation_role": result["evaluation_role"],
            }
    print(dumps(result))
    return 0
