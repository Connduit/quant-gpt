"""Atomic report exports; include input provenance, assumptions and benchmark results."""

import csv
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

from quantlab.backtesting.engine import BacktestResult


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def dumps(value) -> str:
    return json.dumps(value, default=json_default, sort_keys=True, indent=2, allow_nan=False)


def export_report(
    result: BacktestResult,
    benchmark: BacktestResult,
    output: Path,
    benchmark_policy: str | None = None,
) -> dict:
    if output.exists():
        raise ValueError(f"Report output already exists: {output}; choose a new directory")
    if result.metadata["snapshot_id"] != benchmark.metadata["snapshot_id"]:
        raise ValueError("Benchmark must use the same snapshot and simulation period")
    if (
        result.metadata["configuration"] != benchmark.metadata["configuration"]
        or result.metadata["corporate_actions"] != benchmark.metadata["corporate_actions"]
    ):
        raise ValueError("Benchmark must use identical accounting, costs and action inputs")
    if benchmark_policy is None and benchmark.metadata["strategy"] != "BuyAndHold":
        raise ValueError("Benchmark must be the buy-and-hold baseline")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".pending-report-", dir=output.parent))
    try:
        for name, rows, empty_fields in (
            (
                "trades.csv",
                result.trades,
                [
                    "order_id",
                    "symbol",
                    "side",
                    "quantity",
                    "timestamp",
                    "price",
                    "commission",
                    "realized_pnl",
                ],
            ),
            ("equity.csv", result.equity, []),
            ("orders.csv", result.orders, ["order_id", "symbol", "status", "reason"]),
            ("signals.csv", result.signals, ["timestamp", "symbol", "target_quantity"]),
            ("corporate_actions.csv", result.actions, ["timestamp", "kind"]),
            ("benchmark_equity.csv", benchmark.equity, []),
            ("benchmark_trades.csv", benchmark.trades, ["order_id", "symbol", "side"]),
            ("positions.csv", result.positions, ["session_date", "symbol", "quantity"]),
        ):
            fields = list(dict.fromkeys(key for row in rows for key in row)) or empty_fields
            with (temporary / name).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        package = Path(__file__).resolve().parents[1]
        sources = {
            str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.rglob("*.py"))
        }
        (temporary / "benchmark_orders.json").write_text(dumps(benchmark.orders) + "\n")
        artifacts = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(temporary.iterdir())
        }
        metadata = {
            **result.metadata,
            "software_version": version("quant-research-lab"),
            "benchmark": benchmark.metadata,
            "benchmark_policy": benchmark_policy
            or "same_symbol_and_costs_fixed_shares_cash_remainder",
            "python_version": sys.version.split()[0],
            "dependency_versions": {
                name: version(name)
                for name in ("duckdb", "exchange-calendars", "polars", "pyarrow", "pandas", "numpy")
            },
            "package_source_sha256": hashlib.sha256(dumps(sources).encode()).hexdigest(),
        }
        fingerprint = hashlib.sha256(
            dumps({"metadata": metadata, "artifacts": artifacts}).encode()
        ).hexdigest()
        report = {
            "run_id": fingerprint,
            "metadata": metadata,
            "artifacts_sha256": artifacts,
            "performance": result.metrics,
            "benchmark_performance": benchmark.metrics,
            "excess_total_return": result.metrics["total_return"]
            - benchmark.metrics["total_return"],
            "order_status_counts": {
                status: sum(order["status"] == status for order in result.orders)
                for status in ("filled", "rejected", "cancelled", "expired")
            },
            "warnings": [
                "Hypothetical simulation, not live performance or evidence of profitability.",
                "Synthetic test data."
                if result.metadata["synthetic"]
                else (
                    "Caller-declared raw prices and complete actions; not independently verified."
                ),
                "Full market fills at next eligible open; no volume/queue/latency model.",
                "Fractional shares allowed; no taxes, interest, FX, borrow or cash-in-lieu.",
                "Data is not certified point-in-time or survivorship-free.",
            ],
        }
        if not result.trades:
            report["warnings"].append(
                "Strategy produced no fills; inspect signals and order statuses."
            )
        if not benchmark.trades:
            report["warnings"].append("Benchmark produced no fills and remained in cash.")
        if not result.metadata["strategy_parameters_complete"]:
            report["warnings"].append(
                "Custom strategy state is not captured; use a configured dataclass."
            )
        (temporary / "report.json").write_text(dumps(report) + "\n")
        temporary.rename(output)
        return report
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
