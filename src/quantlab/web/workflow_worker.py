"""Isolated dashboard worker: validated requests only, no shell or trading authority."""

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantlab.web.workflows import (
    HOLDOUT_START,
    DownloadRequest,
    ResearchRequest,
    safe_manifest,
    selected_snapshots,
)


def acquire(payload, library, output):
    import csv
    from datetime import date
    from io import StringIO

    from quantlab.data.ingestion import ingest
    from quantlab.data.providers.base import DataRequest, ProviderError
    from quantlab.data.providers.factory import create_provider
    from quantlab.data.storage import SnapshotStore
    from quantlab.data.validation import ValidationError

    request = DownloadRequest.model_validate(payload)
    store = SnapshotStore(library)

    provider = create_provider(
        request.provider,
        alpaca_feed=request.alpaca_feed,
        databento_dataset=request.databento_dataset,
        maximum_download_cost=request.maximum_download_cost,
    )

    class BoundedProvider:
        name = provider.name

        def fetch(self, data_request):
            download = provider.fetch(data_request)
            # Never retain an archive that silently includes dates outside the request.
            try:
                dates = [
                    date.fromisoformat(row["Date"])
                    for row in csv.DictReader(StringIO(download.raw.decode("utf-8")))
                ]
            except (ValueError, KeyError, UnicodeError) as exc:
                raise ProviderError("Provider returned invalid source dates") from exc
            if any(day < data_request.start or day > data_request.end for day in dates):
                raise ProviderError("Provider returned dates outside the bounded request")
            return download

    results = []
    for symbol in request.symbols:
        try:
            sid, cached = ingest(
                BoundedProvider(),
                DataRequest(symbol, request.start, request.end),
                store,
                refresh=request.refresh,
            )
            metadata = safe_manifest(library, sid, allow_holdout=True)
            frame = store.read(sid)
            if frame.height != metadata["row_count"]:
                raise ValueError("Snapshot count mismatch")
            if store.query(sid, "SELECT count(*) AS n FROM bars")["n"][0] != frame.height:
                raise ValueError("DuckDB snapshot count mismatch")
            results.append(
                {
                    "symbol": symbol,
                    "status": "CACHED" if cached else "CREATED",
                    "snapshot_id": sid,
                    "rows": frame.height,
                    "price_basis": metadata["price_basis"],
                }
            )
        except (ProviderError, ValidationError) as exc:
            results.append({"symbol": symbol, "status": "FAILED", "reason": str(exc)})
    failures = sum(r["status"] == "FAILED" for r in results)
    report = {
        "status": "FAILED" if failures == len(results) else "PARTIAL" if failures else "COMPLETED",
        "snapshots": results,
        "provider": request.provider,
        "estimated_cost_reserved_usd": getattr(provider, "quoted_cost", 0),
        "note": "Raw OHLCV does not certify corporate actions or point-in-time membership.",
    }
    if failures:
        report["reason"] = "; ".join(
            f"{row['symbol']}: {row['reason']}" for row in results if row["status"] == "FAILED"
        )
    return report


def experiment_document(request, library, snapshots):
    return {
        "experiment": {"name": request.name, "primary_model": request.models[0]},
        "data": {
            "data_dir": str(library),
            "snapshots": snapshots,
            "benchmark": "SPY",
            "universe": [s for s in snapshots if s != "SPY"],
            "prediction_horizon": request.horizon,
            "holdout_start": str(request.end + timedelta(days=1) if request.end else HOLDOUT_START),
        },
        "models": [
            {
                "type": m,
                "seed": request.seed,
                "objective": "classification" if m == "logistic" else "regression",
                "parameters": {"n_estimators": 50, "max_depth": 4}
                if m in ("random_forest", "lightgbm", "xgboost")
                else {},
            }
            for m in request.models
        ],
        "validation": {
            "training_sessions": request.training_sessions,
            "validation_sessions": request.validation_sessions,
            "test_sessions": request.test_sessions,
            "expanding": False,
            "embargo_sessions": request.horizon,
        },
        "strategy": {
            "top_n": request.top_n,
            "rebalance_sessions": 5,
            "maximum_position_weight": min(0.4, 0.8 / request.top_n),
            "cash_allocation": 0.2,
            "minimum_dollar_volume": 10000000,
        },
        "execution": {
            "initial_cash": "100000",
            "commission_per_share": "0.005",
            "slippage_bps": 5,
            "spread_bps": 2,
        },
    }


def research(payload, library, output):
    import yaml

    request = ResearchRequest.model_validate(payload)
    snapshots = selected_snapshots(library, request)  # Bounds first; no source payload reads.
    input_library = library
    if request.start is not None:
        from quantlab.web.research_inputs import prepare_research_inputs

        input_library = output / "inputs"
        snapshots = prepare_research_inputs(request, library, input_library)
    manifests = [
        safe_manifest(
            input_library,
            entry["snapshot_id"] if isinstance(entry, dict) else entry,
            allow_holdout=request.start is not None,
        )
        for entry in snapshots.values()
    ]
    if len({(m["request"]["start"], m["request"]["end"]) for m in manifests}) != 1:
        raise ValueError("Select snapshots with identical date coverage")
    rows = max(m["row_count"] for m in manifests)
    if (
        rows > 3000
        or math.ceil(
            (rows - request.training_sessions - request.validation_sessions) / request.test_sessions
        )
        > 8
    ):
        raise ValueError("Budget allows at most 3,000 sessions and eight folds; adjust windows")
    if rows < request.training_sessions + request.validation_sessions + 80:
        raise ValueError("Insufficient sessions for feature warmup, purge and evaluation windows")
    if request.research_mode == "exploratory":
        from quantlab.web.exploratory import run_exploratory_ml

        report = run_exploratory_ml(request, input_library, snapshots, output / "research")
        return {
            "status": "COMPLETED",
            "workflow": request.workflow,
            "research_status": "EXPLORATORY_ML",
            "report": report,
            "snapshot_ids": request.snapshot_ids,
            "research_range": {"start": str(request.start), "end": str(request.end)},
            "input_snapshot_ids": list(snapshots.values()),
            "note": "Prediction metrics only; no trading simulation, qualification or promotion.",
        }
    experiment = output / "experiment.yaml"
    experiment.write_text(yaml.safe_dump(experiment_document(request, input_library, snapshots)))
    if request.workflow == "training":
        from quantlab.research.runner import run_experiment

        report = run_experiment(experiment, output / "research", prefix_only=True)
    else:
        from quantlab.discovery.study import run_study

        study = {
            "study": {
                "name": request.name,
                "hypothesis": "Bounded feature/model search versus simpler baselines after costs.",
                "experiment": str(experiment),
                "seed": request.seed,
                "max_trials": request.max_trials,
                "max_wall_seconds": 900,
            },
            "resources": {
                "workers": 1,
                "cpu_threads": 1,
                "memory_mb": 4096,
                "trial_wall_seconds": 180,
                "trial_cpu_seconds": 120,
                "max_attempts": 1,
            },
            "search": {
                "feature_sets": {
                    "momentum": ["momentum", "relative_strength", "volume"],
                    "reversion": ["mean_reversion", "volatility"],
                },
                "targets": ["direction" if request.models == ["logistic"] else "excess_return"],
                "horizons": [request.horizon],
                "models": {
                    m: {
                        "C" if m == "logistic" else "alpha": {
                            "type": "categorical",
                            "choices": [0.1, 1, 10],
                        }
                    }
                    if m in ("ridge", "logistic")
                    else {
                        "n_estimators": {"type": "categorical", "choices": [25, 50]},
                        "max_depth": {"type": "categorical", "choices": [3, 4]},
                    }
                    for m in request.models
                },
                "strategy": {
                    "top_n": {"type": "categorical", "choices": [request.top_n]},
                    "rebalance_sessions": {"type": "categorical", "choices": [5, 10]},
                },
            },
            "cost_multipliers": [2],
            "robustness": {"top_k": 0},
        }
        if "logistic" in request.models and len(request.models) > 1:
            study["search"]["targets"].append("direction")
        configuration = output / "study.yaml"
        configuration.write_text(yaml.safe_dump(study))
        report = run_study(configuration, output / "discovery", prefix_only=True)
    return {
        "status": "COMPLETED",
        "research_status": "DEVELOPMENT_ONLY",
        "report": report,
        "snapshot_ids": request.snapshot_ids,
        "research_range": {"start": str(request.start), "end": str(request.end)}
        if request.start is not None
        else None,
        "input_snapshot_ids": [
            e["snapshot_id"] if isinstance(e, dict) else e for e in snapshots.values()
        ],
        "note": "Development research; no Phase 12 qualification or deployment approval.",
    }


def execute(specification, output):
    library = Path(specification["library"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    payload = specification["payload"]
    try:
        if specification["workflow"] == "download":
            result = acquire(payload, library, output)
        elif specification["workflow"] == "profitability":
            import zipfile

            from quantlab.profitability.runner import run_profitability
            from quantlab.web.workflows import ProfitabilityRequest

            checked = ProfitabilityRequest.model_validate(payload)
            report = run_profitability(
                Path(specification["source_artifacts"]),
                checked,
                output / "profitability",
                Path(specification["registry_root"]),
            )
            with zipfile.ZipFile(
                output / "profitability.zip", "w", zipfile.ZIP_DEFLATED
            ) as archive:
                for path in sorted((output / "profitability").rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(output / "profitability"))
            result = {
                "status": "COMPLETED",
                "workflow": "profitability",
                "report": report,
                "note": "Net simulated performance; NOT independently validated or approved.",
            }
        else:
            result = research(payload, library, output)
    except (ValueError, FileNotFoundError) as exc:
        result = {"status": "BLOCKED_DATA", "reason": str(exc)}
    except ImportError:
        result = {"status": "FAILED", "reason": "Research dependencies are missing on the server"}
    result.update(
        {
            "workflow": specification["workflow"],
            "request": payload,
            "completed_at": datetime.now(UTC).isoformat(),
            "specification_sha256": hashlib.sha256(
                json.dumps(specification, sort_keys=True).encode()
            ).hexdigest(),
            "holdout_accessed": False,
            "source_archive_read_for_slicing": payload.get("start") is not None
            and specification["workflow"] in ("training", "discovery"),
            "live_enabled": False,
        }
    )
    (output / "result.json").write_text(json.dumps(result, default=str, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (900, 900))
    resource.setrlimit(resource.RLIMIT_AS, (4096 * 1024**2, 4096 * 1024**2))
    result = execute(json.loads(args.spec.read_text()), args.output)
    print(result.get("reason", result.get("note", result["status"])))
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
