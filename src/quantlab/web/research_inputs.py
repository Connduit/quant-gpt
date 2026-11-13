"""Build job-local date-bounded inputs; fitting engines never open the full archive."""

import csv
import json
from io import StringIO
from pathlib import Path

import polars as pl

from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore
from quantlab.data.validation import normalize_daily
from quantlab.web.workflows import ResearchRequest, safe_manifest


def prepare_research_inputs(request: ResearchRequest, library: Path, destination: Path) -> dict:
    if request.start is None or request.end is None:
        raise ValueError("Automatic slicing requires research start and end dates")
    source_store = SnapshotStore(library)
    target_store = SnapshotStore(destination)
    snapshots = {}
    for sid in request.snapshot_ids:
        metadata = safe_manifest(library, sid, allow_holdout=True)
        bounds = DataRequest(metadata["request"]["symbol"], request.start, request.end)
        frame = source_store.read(sid)  # Verify both original checksums before slicing.
        if frame.height != metadata["row_count"]:
            raise ValueError("Snapshot count mismatch")
        child = frame.filter(pl.col("session_date").is_between(bounds.start, bounds.end))
        if child.height > 3000:
            raise ValueError("Budget allows at most 3,000 sessions; narrow the research date range")
        # Copy only in-range original rows, preserving vendor values and extra columns.
        source = library / "snapshots" / sid / "source.csv"
        reader = csv.DictReader(StringIO(source.read_text()))
        raw = StringIO()
        writer = csv.DictWriter(raw, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if str(bounds.start) <= row["Date"] <= str(bounds.end):
                writer.writerow(row)
        raw_bytes = raw.getvalue().encode()
        normalized = normalize_daily(raw_bytes, bounds)
        columns = ["session_date", "open", "high", "low", "close", "volume"]
        if not child.select(columns).equals(normalized.select(columns)):
            raise ValueError("Original source and normalized snapshot disagree")
        child_id = target_store.write(
            metadata["provider"],
            bounds,
            Download(raw_bytes, metadata["source"], metadata["price_basis"], metadata["synthetic"]),
            child,
            parent=sid,
            point_in_time=metadata.get("point_in_time", False),
            universe_membership_included=metadata.get("universe_membership_included", False),
        )
        # Eligibility was checked before any source payload was opened. Copy only
        # events effective within the requested range; keep delayed dividend pay dates.
        source_ledger = library / "actions" / f"{sid}.json"
        if request.research_mode != "exploratory" and source_ledger.exists():
            if not source_ledger.resolve().is_relative_to(library.resolve()):
                raise ValueError("Action ledger escapes the dashboard library")
            ledger = json.loads(source_ledger.read_text())
            ledger.update(
                coverage_start=str(bounds.start),
                coverage_end=str(bounds.end),
                splits=[
                    a for a in ledger["splits"] if str(bounds.start) <= a["date"] <= str(bounds.end)
                ],
                dividends=[
                    a
                    for a in ledger["dividends"]
                    if str(bounds.start) <= a["ex_date"] <= str(bounds.end)
                ],
            )
            actions = destination / "actions" / f"{child_id}.json"
            actions.parent.mkdir(exist_ok=True)
            actions.write_text(json.dumps(ledger, indent=2) + "\n")
            snapshots[bounds.symbol] = {"snapshot_id": child_id, "actions": str(actions)}
        else:
            snapshots[bounds.symbol] = (
                child_id  # Price-only exploration or synthetic engine fixtures.
            )
    return snapshots
