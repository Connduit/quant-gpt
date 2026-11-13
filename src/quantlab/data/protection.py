"""Metadata-only training/test plans shared by dashboard data and research gates."""

import fcntl
import json
from pathlib import Path

from quantlab.data.storage import digest


def plans(library: Path) -> list[dict]:
    path = library / "dataset-plans.json"
    if not path.exists():
        return []
    if not path.resolve().is_relative_to(library.resolve()):
        raise ValueError("Dataset plan escapes its trusted library")
    return json.loads(path.read_text())


def protection_reasons(library: Path, metadata: dict) -> list[str]:
    if metadata.get("dataset_role") == "protected_test":
        return ["Protected test snapshot: sealed; unavailable for routine training or evaluation"]
    bounds = metadata["request"]
    for plan in plans(library):
        if (
            bounds["symbol"] in plan["symbols"]
            and bounds["start"] <= plan["end"]
            and bounds["end"] >= plan["split_date"]
        ):
            return ["Archive includes reserved test dates; use the separate training snapshot"]
    return []


def reserve_plan(library: Path, request) -> dict:
    library.mkdir(parents=True, exist_ok=True)
    value = {
        "provider": request.provider,
        "alpaca_feed": request.alpaca_feed,
        "symbols": sorted(request.symbols),
        "start": str(request.start),
        "split_date": str(request.split_date),
        "end": str(request.end),
    }
    identifier = digest(json.dumps(value, sort_keys=True).encode())
    value.update(
        id=identifier, state="SEALED", protection="protected test; no fitting/evaluation authorized"
    )
    with (library / ".dataset-plans.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = plans(library)
        for prior in existing:
            if set(prior["symbols"]) & set(value["symbols"]):
                if value["start"] <= prior["end"] and value["split_date"] > prior["split_date"]:
                    raise ValueError(
                        "Training range overlaps reserved test dates; keep the original split"
                    )
        old = next((p for p in existing if p["id"] == identifier), None)
        if old:
            return old
        # Reservation precedes downloads so partial failures do not unseal successful test data.
        temporary = library / ".dataset-plans.pending"
        temporary.write_text(json.dumps(existing + [value], indent=2) + "\n")
        temporary.replace(library / "dataset-plans.json")
    return value


def check_saved_job(source: Path, library: Path):
    """Apply new reservations to older saved jobs before reading prediction or price bytes."""
    if not plans(library):
        return
    from quantlab.data.storage import SnapshotStore

    result = json.loads((source / "result.json").read_text())
    store = SnapshotStore(source / "inputs")
    for sid in result.get("input_snapshot_ids", []):
        reasons = protection_reasons(library, store.inspect(sid))
        if reasons:
            raise ValueError(
                "Saved run overlaps a protected test reservation. " + "; ".join(reasons)
            )
