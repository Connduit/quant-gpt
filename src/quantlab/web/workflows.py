"""Typed dashboard workflows. Paths, models, budgets and holdout bounds are server-owned."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantlab.data.providers.base import DataRequest
from quantlab.data.storage import digest

HOLDOUT_START = date(2019, 1, 2)
SAFE_END = date(2018, 12, 31)
MODEL_TYPES = Literal["ridge", "logistic", "random_forest", "lightgbm", "xgboost"]


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["alpaca", "databento"] = "alpaca"
    alpaca_feed: Literal["sip", "iex"] = "sip"
    databento_dataset: Literal["XNAS.ITCH", "DBEQ.BASIC"] = "XNAS.ITCH"
    maximum_download_cost: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    symbols: list[str] = Field(min_length=1, max_length=12)
    start: date
    end: date
    refresh: bool = False
    confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_request(self):
        if self.start < date(1990, 1, 1):
            raise ValueError("Downloads must start on or after 1990-01-01")
        if (self.end - self.start).days > 3653:
            raise ValueError("Download at most ten years per snapshot")
        if self.provider == "databento" and (self.end - self.start).days > 30:
            raise ValueError("Databento equity downloads are limited to 31 calendar days per job")
        self.symbols = list(dict.fromkeys(s.upper().strip() for s in self.symbols))
        for symbol in self.symbols:
            DataRequest(symbol, self.start, self.end)
        return self


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: Literal["training", "discovery"]
    research_mode: Literal["strict", "exploratory"] = "strict"
    name: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9 _-]+$")
    snapshot_ids: list[str] = Field(min_length=2, max_length=12)
    models: list[MODEL_TYPES] = Field(min_length=1, max_length=5)
    start: date | None = None
    end: date | None = None
    horizon: Literal[1, 5, 10] = 5
    training_sessions: int = Field(default=504, ge=60, le=1500)
    validation_sessions: int = Field(default=126, ge=20, le=252)
    test_sessions: int = Field(default=126, ge=20, le=252)
    top_n: int = Field(default=3, ge=1, le=10)
    max_trials: int = Field(default=4, ge=1, le=8)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_request(self):
        if self.research_mode == "exploratory" and (
            self.workflow != "training" or self.start is None or self.end is None
        ):
            raise ValueError("Exploratory ML requires training workflow and an explicit date range")
        if (self.start is None) != (self.end is None):
            raise ValueError("Supply both research start and end dates")
        if self.start is not None:
            DataRequest("SPY", self.start, self.end)
        if len(set(self.snapshot_ids)) != len(self.snapshot_ids):
            raise ValueError("Select each snapshot once")
        if any(not re.fullmatch(r"[a-f0-9]{64}", sid) for sid in self.snapshot_ids):
            raise ValueError("Invalid snapshot ID")
        if len(set(self.models)) != len(self.models):
            raise ValueError("Select each model once")
        return self


def safe_manifest(library: Path, sid: str, *, allow_holdout: bool = False) -> dict:
    """Inspect bounds and identity BEFORE the storage reader opens price payloads."""
    if not re.fullmatch(r"[a-f0-9]{64}", sid):
        raise ValueError("Invalid snapshot ID")
    path = library / "snapshots" / sid / "manifest.json"
    if not path.resolve().is_relative_to(library.resolve()):
        raise ValueError("Snapshot escapes the dashboard library")
    metadata = json.loads(path.read_text())
    if digest(json.dumps(metadata, sort_keys=True).encode()) != sid:
        raise ValueError("Snapshot manifest checksum mismatch")
    request = metadata["request"]
    if not allow_holdout and date.fromisoformat(request["end"]) > SAFE_END:
        raise ValueError("Snapshot overlaps or follows the reserved holdout; payload not opened")
    DataRequest(
        request["symbol"], date.fromisoformat(request["start"]), date.fromisoformat(request["end"])
    )
    for filename in ("source.csv", "bars.parquet"):
        if not (path.parent / filename).resolve().is_relative_to(library.resolve()):
            raise ValueError("Snapshot payload escapes the dashboard library")
    return metadata


def research_blockers(
    library: Path, sid: str, metadata: dict, *, start: date | None = None, end: date | None = None
) -> list[str]:
    start_bound = str(start) if start else metadata["request"]["start"]
    end_bound = str(end) if end else metadata["request"]["end"]
    if metadata["synthetic"]:
        return ["Synthetic inputs are engineering fixtures, not eligible real research data"]
    reasons = []
    if metadata["price_basis"] != "unadjusted":
        reasons.append("Trading simulations require verified unadjusted execution prices")
    if not metadata.get("point_in_time") or not metadata.get("universe_membership_included"):
        reasons.append("Certified point-in-time universe membership is missing")
    ledger = library / "actions" / f"{sid}.json"
    if not ledger.is_file():
        reasons.append("Complete corporate-action ledger is missing")
    elif not ledger.resolve().is_relative_to(library.resolve()):
        reasons.append("Action ledger escapes the dashboard library")
    else:
        from quantlab.backtesting.actions import CorporateActions

        try:
            actions = CorporateActions.load(ledger)
            if not actions.complete:
                reasons.append("Corporate-action ledger is incomplete")
            if (
                actions.symbol != metadata["request"]["symbol"]
                or str(actions.coverage_start) > start_bound
                or str(actions.coverage_end) < end_bound
            ):
                reasons.append("Action coverage must include the selected research date range")
        except (ValueError, KeyError, TypeError):
            reasons.append("Corporate-action ledger failed validation")
    return reasons


def exploratory_blockers(metadata: dict) -> list[str]:
    reasons = []
    if metadata["synthetic"]:
        reasons.append("Synthetic inputs are engineering fixtures, not eligible real research data")
    if metadata["price_basis"] not in ("unadjusted", "adjusted"):
        reasons.append("Exploratory ML requires a declared adjusted or unadjusted price basis")
    return reasons


def snapshot_inventory(
    library: Path,
    *,
    start: date | None = None,
    end: date | None = None,
    research_mode: Literal["strict", "exploratory"] = "strict",
) -> dict:
    if (start is None) != (end is None):
        raise ValueError("Supply both research start and end dates")
    if start is not None:
        DataRequest("SPY", start, end)
    items, errors = [], []
    for path in sorted((library / "snapshots").glob("*/manifest.json")):
        sid = path.parent.name
        try:
            metadata = safe_manifest(library, sid, allow_holdout=True)
            strict_reasons = research_blockers(library, sid, metadata, start=start, end=end)
            reasons = (
                exploratory_blockers(metadata) if research_mode == "exploratory" else strict_reasons
            )
            if start is not None and (
                str(start) < metadata["request"]["start"] or str(end) > metadata["request"]["end"]
            ):
                reasons.append("Snapshot does not cover the selected research date range")
            items.append(
                {
                    "id": sid,
                    "symbol": metadata["request"]["symbol"],
                    "start": metadata["request"]["start"],
                    "end": metadata["request"]["end"],
                    "rows": metadata["row_count"],
                    "provider": metadata["provider"],
                    "price_basis": metadata["price_basis"],
                    "retrieved_at": metadata["retrieved_at"],
                    "eligible": not reasons,
                    "blockers": reasons,
                    "strict_blockers": strict_reasons,
                    "research_mode": research_mode,
                }
            )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({"id": sid, "error": str(exc)})
    return {"items": items, "errors": errors, "safe_end": str(SAFE_END)}


def selected_snapshots(library: Path, request: ResearchRequest) -> dict:
    snapshots = {}
    price_bases = set()
    for sid in request.snapshot_ids:
        metadata = safe_manifest(library, sid, allow_holdout=request.start is not None)
        if request.start is not None and (
            str(request.start) < metadata["request"]["start"]
            or str(request.end) > metadata["request"]["end"]
        ):
            raise ValueError("Research dates must be within every selected snapshot")
        reasons = (
            exploratory_blockers(metadata)
            if request.research_mode == "exploratory"
            else (research_blockers(library, sid, metadata, start=request.start, end=request.end))
        )
        if reasons:
            raise ValueError(f"{metadata['request']['symbol']}: " + "; ".join(reasons))
        price_bases.add(metadata["price_basis"])
        symbol = metadata["request"]["symbol"]
        if symbol in snapshots:
            raise ValueError("Choose one snapshot per symbol")
        snapshots[symbol] = {
            "snapshot_id": sid,
            "actions": str(library / "actions" / f"{sid}.json"),
        }
    if request.research_mode == "exploratory" and len(price_bases) != 1:
        raise ValueError("Exploratory inputs must use the same declared price basis")
    if "SPY" not in snapshots:
        raise ValueError("Select a SPY benchmark snapshot plus at least one equity")
    if request.research_mode == "strict" and request.top_n > len(snapshots) - 1:
        raise ValueError("Top holdings cannot exceed the selected equity count")
    return snapshots
