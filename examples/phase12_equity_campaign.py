"""Read-only Phase 12 data preflight. Never fits models or reads holdout payloads.

Run from the repository root. Exit 2 means insufficient research data; exit 1
means an integrity/software failure. A successful preflight would still require
review and a separately implemented execution adapter; this is not a scheduler.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import date
from pathlib import Path

import yaml

from quantlab.data.providers.base import DataRequest
from quantlab.data.storage import SnapshotStore, digest
from quantlab.data.validation import normalize_daily

ROOT = Path(__file__).resolve().parents[1]


def ledger_states():
    result = {}
    for relative in (
        "data/network-verification/holdout-vault.sqlite",
        "data/futures/holdout-vault.sqlite",
    ):
        path = ROOT / relative
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            result[relative] = connection.execute(
                "SELECT id,state FROM holdouts ORDER BY id"
            ).fetchall()
    return result


def main():
    plan_path = ROOT / "configs/phase12/equity-ml-campaign.yaml"
    plan = yaml.safe_load(plan_path.read_text())
    if not __debug__:
        raise RuntimeError("Run this audit without Python optimization; assertions are required")
    before = ledger_states()
    assert all(state == "SEALED" for rows in before.values() for _, state in rows)
    if not all(before.values()):
        raise ValueError("Canonical holdout ledgers must contain records")
    root = ROOT / "data/network-verification/real-inputs"
    quality = json.loads((root / "data_quality.json").read_text())
    store = SnapshotStore(root)
    audits = []
    for symbol, entry in sorted(quality["snapshots"].items()):
        sid = entry["snapshot_id"]
        directory = root / "snapshots" / sid
        metadata = json.loads((directory / "manifest.json").read_text())
        # Check request bounds and content identity BEFORE reading any payload.
        assert digest(json.dumps(metadata, sort_keys=True).encode()) == sid
        assert metadata["request"]["end"] < "2019-01-02"
        assert metadata["request"]["symbol"] == symbol
        assert metadata["price_basis"] == "unadjusted" and not metadata["synthetic"]
        metadata = store.manifest(sid)
        request = DataRequest(
            symbol,
            date.fromisoformat(metadata["request"]["start"]),
            date.fromisoformat(metadata["request"]["end"]),
        )
        normalized = normalize_daily((directory / "source.csv").read_bytes(), request)
        frame = store.read(sid)
        assert normalized.equals(frame)
        assert str(frame["session_date"].max()) < "2019-01-02"
        assert store.query(sid, "SELECT count(*) AS n FROM bars")["n"][0] == frame.height
        actions = json.loads((root / "actions" / f"{symbol}.json").read_text())
        audits.append(
            dict(
                symbol=symbol,
                snapshot_id=sid,
                provider=metadata["provider"],
                start=str(frame["session_date"].min()),
                end=str(frame["session_date"].max()),
                rows=frame.height,
                integrity="PASS",
                price_basis=metadata["price_basis"],
                sector=quality["quality"][symbol]["sectors"],
                point_in_time=metadata["point_in_time"],
                corporate_actions_complete=actions["complete"],
                action_method=actions["coverage_method"],
                dividends=len(actions["dividends"]),
                splits=len(actions["splits"]),
                unknown_payment_dates=sum(
                    x.get("pay_date") is None for x in actions["dividends"]
                ),
            )
        )
    history = []
    for category in ("discovery", "statistical", "futures", "agent"):
        for path in sorted((ROOT / "data" / category).rglob("registry.sqlite")):
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                history.append(
                    dict(
                        path=str(path.relative_to(ROOT)),
                        experiments=connection.execute(
                            "SELECT count(*) FROM experiments"
                        ).fetchone()[0],
                        attempts=connection.execute("SELECT count(*) FROM attempts").fetchone()[0],
                        statuses=connection.execute(
                            "SELECT status,count(*) FROM attempts GROUP BY status"
                        ).fetchall(),
                    )
                )
    after = ledger_states()
    assert before == after
    reasons = []
    stocks = [a for a in audits if a["symbol"] != "SPY"]
    if len(stocks) < plan["data_requirements"]["minimum_stocks"]:
        reasons.append(
            "Only seven stocks; protocol requires at least 100 point-in-time "
            "constituents including delisted securities."
        )
    if len({a["sector"] for a in stocks}) < plan["data_requirements"]["minimum_sectors"]:
        reasons.append("Only four stock sectors; protocol requires eight.")
    if min(a["rows"] for a in audits) < plan["data_requirements"]["minimum_sessions"]:
        reasons.append(
            "Only 1,195 sessions; protocol requires 2,000 and independent confirmation "
            "outside previously reused validation."
        )
    if not all(a["corporate_actions_complete"] for a in audits):
        reasons.append(
            "Factor-file proxies do not certify complete corporate actions, "
            "known payment dates or delisting payouts."
        )
    if not all(a["point_in_time"] for a in audits):
        reasons.append(
            "No certified point-in-time membership, historical symbol mapping, "
            "or historical publication timestamps."
        )
    reasons.append(
        "Independent confirmation dates, dated cost/capacity calibration and a "
        "prefix-only equity execution adapter remain unapproved/unimplemented."
    )
    report = dict(
        campaign="P12-EQ-001",
        status="BLOCKED_DATA",
        script_role="preflight_only",
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        plan_id=plan["campaign_id"],
        snapshots=audits,
        blockers=reasons,
        history=history,
        holdout_states=after,
        holdout_states_unchanged=True,
        new_model_fits=0,
        new_strategy_trials=0,
        new_candidates=[],
        promotions=[],
        statistics=dict(
            p_values=None,
            confidence_intervals=None,
            deflated_sharpe=None,
            reason="No eligible data or new research trials; unavailable is not a zero estimate.",
        ),
    )
    destination = ROOT / "docs/phase12/preflight.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"BLOCKED_DATA: audited {len(audits)} pre-holdout snapshots; "
        f"zero fits/trials. {destination}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
