"""Curated artifact IDs; no recursive data browsing or caller-supplied paths."""

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantlab.backtesting.report import dumps
from quantlab.discovery.common import fingerprint
from quantlab.futures.contracts import contract_from_dict
from quantlab.paper.account import Account

KINDS = {
    "datasets",
    "research",
    "models",
    "discovery",
    "validation",
    "backtests",
    "portfolios",
    "paper",
    "agent",
    "live",
}


class Catalog:
    def __init__(self, configuration, workspace):
        self.workspace = Path(workspace).resolve()
        self.records = {}
        self.errors = []
        configuration = Path(configuration)
        doc = yaml.safe_load(configuration.read_text()) or {}
        if set(doc) - {"artifacts"}:
            raise ValueError("Unknown catalog configuration field")
        for entry in doc.get("artifacts", []):
            if set(entry) - {
                "id",
                "kind",
                "label",
                "path",
                "mode",
                "status",
                "database",
                "series_path",
                "benchmark_series_path",
            }:
                raise ValueError("Unknown catalog entry field")
            if (
                not re.fullmatch("[a-z0-9][a-z0-9_-]{0,63}", entry["id"])
                or entry["id"] in self.records
            ):
                raise ValueError("Invalid or duplicate catalog ID")
            if entry["kind"] not in KINDS:
                raise ValueError("Unsupported catalog kind")
            entry = entry.copy()
            for field in ("path", "database", "series_path", "benchmark_series_path"):
                if field in entry:
                    path = (self.workspace / entry[field]).resolve()
                    if not path.is_relative_to(self.workspace):
                        raise ValueError("Catalog artifact escapes workspace")
                    if field == "path" and path.suffix != ".json":
                        raise ValueError("Only reviewed JSON reports can be exposed")
                    entry[field] = path
            self.records[entry["id"]] = entry

    def entry(self, identity):
        if identity not in self.records:
            raise KeyError(identity)
        return self.records[identity]

    def document(self, identity):
        entry = self.entry(identity)
        path = entry["path"]
        if not path.is_file():
            raise FileNotFoundError("Cataloged artifact is not available")
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Report exceeds dashboard size budget")
        doc = json.loads(path.read_text())
        if entry["kind"] == "paper" and entry.get("database"):
            # Read a consistent SQLite snapshot without taking over the account writer.
            with sqlite3.connect(entry["database"].as_uri() + "?mode=ro", uri=True) as db:
                db.execute("BEGIN")
                state = json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])
                checksum = db.execute(
                    "SELECT state_checksum FROM journal ORDER BY number DESC LIMIT 1"
                ).fetchone()
            if checksum is None or fingerprint(state) != checksum[0]:
                raise ValueError("Paper state does not reconcile to its last journal commit")
            config = state["configuration"]
            contracts = {
                key: contract_from_dict(value) for key, value in config["contracts"].items()
            }
            account = Account(config["capital"], contracts)
            for fill in state["fills"]:
                account.fill(
                    fill["instrument"],
                    fill["quantity"],
                    fill["price"],
                    fill["fee"],
                    fill["at"],
                    fill["client_id"],
                    fill["strategy"],
                )
            from quantlab.backtesting.models import decimal

            account.prices = {key: decimal(value) for key, value in state["prices"].items()}
            doc.update(
                {
                    "account": json.loads(dumps(account.view())),
                    "orders": list(state["orders"].values()),
                    "fills": state["fills"],
                    "strategies": state["strategies"],
                    "equity_history": state["equity_history"],
                    "predictions": state["predictions"],
                    "alerts": state["alerts"],
                    "connected": state["connected"],
                    "killed": state["killed"],
                    "latest_processed_clock": state["clock"],
                    "data_mode": config["mode"],
                }
            )
        return self.redact(doc if isinstance(doc, dict) else {"items": doc})

    def redact(self, value):
        if isinstance(value, dict):
            return {
                k: self.redact(v)
                for k, v in value.items()
                if not re.search(
                    r"(^|_)(password|secret|api_key|access_token|authorization|credentials)($|_)",
                    k,
                    re.I,
                )
            }
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, str):
            return value.replace(str(self.workspace), "${WORKSPACE}")
        return value

    def record(self, identity):
        e = self.entry(identity)
        d = self.document(identity)
        status = e.get("status", "RESEARCH")
        if d.get("killed"):
            status = "HALTED"
        if d.get("status"):
            status = str(d["status"])
        summary = {}
        for key in (
            "counts",
            "recorded_history",
            "performance",
            "account",
            "benchmark",
            "paper_eligible",
            "paper_trading_shortlist",
            "final_holdout",
            "drawdown",
            "daily_observations",
            "model_accuracy",
            "row_count",
            "start",
            "end",
            "provider",
            "synthetic",
            "spec",
            "features",
            "versions",
        ):
            if key in d:
                summary[key] = d[key]
        if "results" in d:
            summary["result_count"] = len(d["results"])
        if "runs" in d:
            summary["portfolio_runs"] = {k: v.get("performance") for k, v in d["runs"].items()}
        if not summary:
            summary = {"available_fields": list(d)}
        return {
            "id": identity,
            "kind": e["kind"],
            "label": e["label"],
            "mode": e.get("mode", "RESEARCH"),
            "status": status,
            "summary": summary,
            "updated_at": datetime.fromtimestamp(e["path"].stat().st_mtime, UTC).isoformat(),
        }

    def index(self, *, kind=None, search="", sort="updated_at"):
        result = []
        self.errors = []
        for identity in self.records:
            if kind and self.records[identity]["kind"] != kind:
                continue
            try:
                row = self.record(identity)
            except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
                self.errors.append(identity + ": " + type(exc).__name__)
                continue
            if search.lower() not in (row["label"] + " " + row["status"]).lower():
                continue
            result.append(row)
        return sorted(result, key=lambda r: r[sort], reverse=sort == "updated_at")

    def series(self, identity):
        doc = self.document(identity)
        rows = doc.get("equity_history", [])
        entry = self.entry(identity)
        if entry.get("series_path"):
            # Only an administrator-curated CSV, never caller-supplied SQL or filenames.
            import csv

            with entry["series_path"].open() as f:
                rows = list(csv.DictReader(f))
        benchmarks = {}
        if entry.get("benchmark_series_path"):
            import csv

            with entry["benchmark_series_path"].open() as f:
                for row in csv.DictReader(f):
                    benchmarks[row.get("timestamp", row.get("session_date"))] = float(row["equity"])
        result = []
        peak = None
        for row in rows:
            at = row.get("at", row.get("timestamp", row.get("session_date")))
            equity = row.get("equity")
            if at is None or equity is None:
                continue
            equity = float(equity)
            peak = max(peak or equity, equity)
            point = {
                "at": str(at),
                "equity": equity,
                "drawdown": equity / peak - 1 if peak > 0 else None,
            }
            for k in ("gross", "margin", "benchmark"):
                if row.get(k) is not None:
                    point[k] = float(row[k])
            if str(at) in benchmarks:
                point["benchmark"] = benchmarks[str(at)]
            if row.get("gross_exposure") is not None:
                point["gross"] = float(row["gross_exposure"]) * equity
            result.append(point)
        # Bound response size while preserving final measurement.
        if len(result) > 5000:
            step = (len(result) + 4998) // 4999
            result = result[::step] + [result[-1]]
        return result
