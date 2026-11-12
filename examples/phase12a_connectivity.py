"""Bounded Stooq acquisition check; no model, holdout, or execution imports.

Run from the repository root with .venv/bin/python examples/phase12a_connectivity.py.
Exit 2 means research remains data-gated, even if diagnostic snapshots succeed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from quantlab.data.providers.base import DataRequest, ProviderError
from quantlab.data.providers.stooq import StooqProvider
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily

ROOT = Path(__file__).resolve().parents[1]
SAFE_END = date(2018, 12, 31)


def require_safe(request: DataRequest) -> None:
    if request.end > SAFE_END:
        raise ValueError("Phase 12A acquisition must end before the reserved equity holdout")


def main() -> int:
    evidence = ROOT / "data/phase12a/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    probe = DataRequest("AAPL", date(2018, 1, 2), date(2018, 1, 10))
    require_safe(probe)
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "probe_request": probe.as_dict(),
        "tls_verification": True,
        "proxy": "inherited environment; no bypass",
        "snapshots": [],
        "status": "BLOCKED_DATA",
        "new_model_fits": 0,
        "new_strategy_trials": 0,
        "holdout_payloads_read": False,
        "live_trading_enabled": False,
        "historical_artifacts_present": {
            relative: (ROOT / relative).exists()
            for relative in (
                "data/network-verification/real-inputs/data_quality.json",
                "data/network-verification/holdout-vault.sqlite",
                "data/futures/holdout-vault.sqlite",
            )
        },
    }
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                "https://stooq.com/q/d/l/",
                params={"s": "aapl.us", "d1": "20180102", "d2": "20180110", "i": "d"},
            )
        raw = response.content
        (evidence / "direct-response.bin").write_bytes(raw)
        report["direct"] = {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "csv_header": raw.lstrip().startswith(b"Date,Open,High,Low,Close,Volume"),
            "javascript_verification": b"verify your browser" in raw,
            "url": str(response.url),
        }
    except httpx.RequestError as exc:
        report["direct"] = {"error_type": type(exc).__name__}

    provider = StooqProvider()
    try:
        download = provider.fetch(probe)
    except ProviderError as exc:
        report["application_provider"] = {
            "status": "FAILED",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    else:
        frame = normalize_daily(download.raw, probe)
        report["application_provider"] = {"status": "VALIDATED", "rows": frame.height}
        store = SnapshotStore(ROOT / "data/phase12a")
        # Diagnostic coverage only. These three names cannot satisfy the campaign universe gate.
        for symbol in ("AAPL", "IBM", "SPY"):
            request = DataRequest(symbol, date(2008, 1, 2), SAFE_END)
            require_safe(request)
            try:
                payload = provider.fetch(request)
                bars = normalize_daily(payload.raw, request)
            except ProviderError as exc:
                report["snapshots"].append({"symbol": symbol, "error": str(exc)})
                continue
            sid = store.write(provider.name, request, payload, bars)
            metadata = store.manifest(sid)
            if not store.read(sid).equals(bars):
                raise ValueError("Snapshot read-back mismatch")
            if store.query(sid, "SELECT count(*) AS n FROM bars")["n"][0] != bars.height:
                raise ValueError("DuckDB read-back mismatch")
            report["snapshots"].append(
                {
                    "symbol": symbol,
                    "snapshot_id": sid,
                    "rows": bars.height,
                    "request": request.as_dict(),
                    "price_basis": metadata["price_basis"],
                    "research_eligible": False,
                }
            )
    report["blockers"] = [
        "No certified full corporate-action, delisting-return, identifier and PIT universe bundle.",
        "Restore historical ignored data and canonical ledgers if absent; do not recreate them.",
        "Independent confirmation plan and prefix-only research adapter remain prerequisites.",
    ]
    destination = ROOT / "docs/phase12/phase12a-connectivity.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
