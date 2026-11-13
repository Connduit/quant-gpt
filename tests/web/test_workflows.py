"""Dashboard actions exercise real storage/workers; market and fitting fixtures are synthetic."""

import json
import time
from datetime import date
from pathlib import Path

import exchange_calendars as xcals
import httpx
import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore, digest
from quantlab.data.validation import normalize_daily
from quantlab.web.app import create_app
from quantlab.web.catalog import Catalog
from quantlab.web.jobs import JobManager
from quantlab.web.workflow_worker import acquire, research
from quantlab.web.workflows import (
    DownloadRequest,
    ResearchRequest,
    safe_manifest,
    snapshot_inventory,
)

TOKEN = "test-researcher-00000000000000000000"


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    days = xcals.get_calendar("XNYS", start="2014-01-01", end="2015-12-31").sessions[:230]
    ids = {}
    for index, symbol in enumerate(("AAA", "SPY")):
        rng = np.random.default_rng(index + 42)
        prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
        raw = (
            "Date,Open,High,Low,Close,Volume\n"
            + "\n".join(
                f"{day.date()},{p},{p * 1.01},{p * 0.99},{p},1000000"
                for day, p in zip(days, prices, strict=True)
            )
        ).encode()
        request = DataRequest(symbol, days[0].date(), days[-1].date())
        ids[symbol] = SnapshotStore(root).write(
            "explicit-synthetic-test",
            request,
            Download(raw, "invented test prices", "synthetic", True),
            normalize_daily(raw, request),
        )
    return root, ids


def payload(ids=None, workflow="training"):
    return {
        "workflow": workflow,
        "name": "Synthetic integration check",
        "snapshot_ids": list((ids or {"AAA": "a" * 64, "SPY": "b" * 64}).values()),
        "models": ["ridge"],
        "horizon": 5,
        "training_sessions": 60,
        "validation_sessions": 20,
        "test_sessions": 60,
        "top_n": 1,
        "max_trials": 1,
        "seed": 42,
        "confirmed": True,
    }


def test_api_roles_request_bounds_and_no_shell(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text("artifacts: []\n")
    app = create_app(
        Catalog(path, tmp_path), state_root=tmp_path / "state", tokens={TOKEN: "researcher"}
    )
    headers = {"Authorization": "Bearer " + TOKEN}
    download = {"symbols": ["AAPL"], "start": "2018-01-02", "end": "2018-01-10", "confirmed": True}
    with TestClient(app) as client:
        assert client.post("/api/v1/workflows/download", json=download).status_code == 403
        for change in (
            {"end": "2017-12-31"},
            {"symbols": ["AAPL;touch /tmp/pwn"]},
            {"confirmed": False},
            {"command": "evil"},
            {"start": "1980-01-01"},
        ):
            assert (
                client.post(
                    "/api/v1/workflows/download", json={**download, **change}, headers=headers
                ).status_code
                == 422
            )
        assert client.get("/api/v1/workflows/snapshots").json()["items"] == []
        assert (
            client.post("/api/v1/workflows/research", json=payload(), headers=headers).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/workflows/research",
                json={**payload(), "snapshot_ids": ["../secret", "b" * 64]},
                headers=headers,
            ).status_code
            == 422
        )
        assert client.get("/api/v1/workflows/jobs/unknown").status_code == 404
        assert app.state.jobs.rows() == []


def test_download_html_rejection_then_snapshot_cache(library, tmp_path, monkeypatch):
    import csv
    import io

    monkeypatch.setenv("APCA_API_KEY_ID", "test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    root, ids = library
    raw = (root / "snapshots" / ids["AAA"] / "source.csv").read_bytes()
    m = safe_manifest(root, ids["AAA"])
    document = {
        "symbols": ["AAA"],
        "start": m["request"]["start"],
        "end": m["request"]["end"],
        "confirmed": True,
    }
    original = httpx.Client
    body = [b"<html>verify your browser</html>"]
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=body[0]))
        ),
    )
    destination = tmp_path / "downloads"
    assert acquire(document, destination, tmp_path)["status"] == "FAILED"
    assert not (destination / "snapshots").exists()
    calendar = xcals.get_calendar("XNYS", start=document["start"], end=document["end"])
    body[0] = json.dumps(
        {
            "symbol": "AAA",
            "bars": [
                {
                    "t": calendar.session_open(row["Date"]).isoformat(),
                    **{
                        key: float(row[column])
                        for key, column in zip(
                            ("o", "h", "l", "c", "v"),
                            ("Open", "High", "Low", "Close", "Volume"),
                            strict=True,
                        )
                    },
                }
                for row in csv.DictReader(io.StringIO(raw.decode()))
            ],
        }
    ).encode()
    report = acquire(document, destination, tmp_path)
    assert report["status"] == "COMPLETED"
    sid = report["snapshots"][0]["snapshot_id"]
    assert SnapshotStore(destination).read(sid).height == 230
    assert acquire(document, destination, tmp_path)["snapshots"][0]["status"] == "CACHED"
    inventory = snapshot_inventory(destination)["items"]
    assert not inventory[0]["eligible"]
    assert inventory[0]["price_basis"] == "unadjusted"
    assert "corporate-action" in " ".join(inventory[0]["blockers"])


def test_protected_manifest_rejected_before_payload_open(tmp_path):
    metadata = {
        "request": {"symbol": "AAPL", "start": "2018-01-01", "end": "2019-01-02"},
        "row_count": 250,
        "synthetic": False,
        "provider": "alpaca",
        "price_basis": "unadjusted",
        "retrieved_at": "2025-01-01T00:00:00Z",
    }
    sid = digest(json.dumps(metadata, sort_keys=True).encode())
    directory = tmp_path / "snapshots" / sid
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps(metadata))
    # No source payload exists: a reader trying to open one would fail differently.
    with pytest.raises(ValueError, match="payload not opened"):
        safe_manifest(tmp_path, sid)
    inventory = snapshot_inventory(tmp_path)
    assert not inventory["errors"]
    assert not inventory["items"][0]["eligible"]
    assert "corporate-action" in " ".join(inventory["items"][0]["blockers"])
    assert "reserved holdout" not in " ".join(inventory["items"][0]["blockers"])


def test_real_subprocess_worker_retains_blocker_and_request(tmp_path):
    manager = JobManager(tmp_path / "jobs")
    try:
        identity = manager.submit_workflow("training", payload(), tmp_path / "library", tmp_path)
        deadline = time.monotonic() + 30
        while manager.rows()[0]["status"] in ("QUEUED", "RUNNING"):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert manager.rows()[0]["status"] == "BLOCKED_DATA"
        report = manager.result(identity)
        assert report["request"] == ResearchRequest.model_validate(payload()).model_dump(
            mode="json"
        )
        assert not report["live_enabled"]
        assert list((tmp_path / "jobs/requests").glob("*.json"))
    finally:
        manager.close()


@pytest.mark.parametrize("workflow", ["training", "discovery"])
def test_generated_configuration_reaches_existing_engines(library, tmp_path, monkeypatch, workflow):
    root, ids = library
    # Allow fixtures only in this engine integration test; the public gate rejects them.
    assert all(not item["eligible"] for item in snapshot_inventory(root)["items"])
    monkeypatch.setattr("quantlab.web.workflow_worker.selected_snapshots", lambda *args: ids)
    output = tmp_path / "run"
    output.mkdir()
    result = research(payload(ids, workflow), root, output)
    assert result["status"] == "COMPLETED"
    document = yaml.safe_load((output / "experiment.yaml").read_text())
    assert document["data"]["holdout_start"] == "2019-01-02"
    if workflow == "training":
        assert result["report"]["synthetic"]
        assert result["report"]["folds"]
        assert (output / "research/models/fold-0/ridge/model.joblib").exists()
    else:
        assert result["report"]["study"]["trials"] == 1
        assert (output / "discovery/registry.sqlite").exists()


def test_download_bounds_and_distinct_snapshots():
    with pytest.raises(ValueError, match="ten years"):
        DownloadRequest(
            symbols=["AAPL"], start=date(1990, 1, 1), end=date(2018, 12, 31), confirmed=True
        )
    with pytest.raises(ValueError, match="once"):
        ResearchRequest.model_validate({**payload(), "snapshot_ids": ["a" * 64] * 2})


def test_training_prefix_rejects_archive_before_reading_payload(library, tmp_path, monkeypatch):
    from quantlab.research.runner import run_experiment
    from quantlab.web.workflow_worker import experiment_document

    root, ids = library
    document = experiment_document(ResearchRequest.model_validate(payload(ids)), root, ids)
    document["data"]["holdout_start"] = "2014-01-03"
    configuration = tmp_path / "unsafe.yaml"
    configuration.write_text(yaml.safe_dump(document))

    def forbidden(*args, **kwargs):
        pytest.fail("Price payload was opened before prefix bounds were checked")

    monkeypatch.setattr("quantlab.research.runner.DailyData.from_snapshot", forbidden)
    with pytest.raises(ValueError, match="cannot open a holdout archive"):
        run_experiment(configuration, tmp_path / "unsafe-output", prefix_only=True)


@pytest.mark.parametrize("provider", ["alpaca", "databento"])
def test_download_worker_receives_only_selected_provider_keys(tmp_path, monkeypatch, provider):
    captured = []
    for key in (
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "DATABENTO_API_KEY",
        "QUANTLAB_ALPACA_PAPER_KEY",
        "QUANTLAB_ALPACA_PAPER_SECRET",
    ):
        monkeypatch.setenv(key, "secret-value-must-not-be-persisted")

    class Process:
        returncode = 0

        def __init__(self, *args, **kwargs):
            captured.append(kwargs["env"])

        def poll(self):
            return 0

    monkeypatch.setattr("quantlab.web.jobs.subprocess.Popen", Process)
    manager = JobManager(tmp_path / "jobs")
    try:
        manager.submit_workflow(
            "download",
            {
                "provider": provider,
                "symbols": ["AAPL"],
                "start": "2018-11-23",
                "end": "2018-11-23",
                "confirmed": True,
            },
            tmp_path / "library",
            tmp_path,
        )
        deadline = time.monotonic() + 5
        while manager.rows()[0]["status"] in ("QUEUED", "RUNNING"):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert len(captured) == 1
        env = captured[0]
        assert ("APCA_API_KEY_ID" in env) == (provider == "alpaca")
        assert ("APCA_API_SECRET_KEY" in env) == (provider == "alpaca")
        assert ("DATABENTO_API_KEY" in env) == (provider == "databento")
        assert "QUANTLAB_ALPACA_PAPER_KEY" not in env
        assert "QUANTLAB_ALPACA_PAPER_SECRET" not in env
        for path in (tmp_path / "jobs/requests").glob("*.json"):
            assert "secret-value-must-not-be-persisted" not in path.read_text()
    finally:
        manager.close()


def test_download_accepts_recent_dates_without_releasing_research_holdout():
    request = DownloadRequest.model_validate(
        {
            "symbols": ["AAPL"],
            "start": "2024-01-02",
            "end": "2024-02-01",
            "confirmed": True,
        }
    )
    assert request.end == date(2024, 2, 1)


def test_research_range_validation():
    for change in (
        {"start": "2020-01-01"},
        {"end": "2021-01-01"},
        {"start": "2021-01-01", "end": "2020-01-01"},
        {"start": "2020-01-01", "end": "2999-01-01"},
    ):
        with pytest.raises(ValueError):
            ResearchRequest.model_validate({**payload(), **change})


@pytest.fixture
def modern_library(tmp_path):
    """Invented prices explicitly marked synthetic, never real market evidence."""
    root = tmp_path / "modern-library"
    days = xcals.get_calendar("XNYS", start="2020-01-01", end="2021-12-31").sessions
    ids = {}
    for index, symbol in enumerate(("AAA", "SPY")):
        rng = np.random.default_rng(index + 42)
        prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
        raw = (
            "Date,Open,High,Low,Close,Volume\n"
            + "\n".join(
                f"{day.date()},{p},{p * 1.01},{p * 0.99},{p},1000000"
                for day, p in zip(days, prices, strict=True)
            )
        ).encode()
        bounds = DataRequest(symbol, days[0].date(), days[-1].date())
        ids[symbol] = SnapshotStore(root).write(
            "explicit-synthetic-test",
            bounds,
            Download(raw, "invented test prices", "synthetic", True),
            normalize_daily(raw, bounds),
        )
    return root, ids


@pytest.mark.parametrize("workflow", ["training", "discovery"])
def test_automatic_range_reaches_engines_without_later_rows(
    modern_library, tmp_path, monkeypatch, workflow
):
    from quantlab.backtesting.data import DailyData

    root, ids = modern_library
    originals = {
        sid: (root / "snapshots" / sid / "source.csv").read_bytes() for sid in ids.values()
    }
    # Test-only synthetic fixture bypass; date selection and engines are real.
    monkeypatch.setattr("quantlab.web.workflow_worker.selected_snapshots", lambda *args: ids)
    original_read = DailyData.from_snapshot
    observed = []

    def bounded_read(store, sid, actions=None):
        assert store.root != root / "snapshots"
        feed = original_read(store, sid, actions)
        assert all(date(2020, 1, 2) <= b.session_date <= date(2020, 12, 31) for b in feed.bars)
        observed.append(feed)
        return feed

    monkeypatch.setattr(DailyData, "from_snapshot", bounded_read)
    output = tmp_path / "ranged-run"
    output.mkdir()
    result = research(
        {**payload(ids, workflow), "start": "2020-01-02", "end": "2020-12-31"}, root, output
    )
    assert result["status"] == "COMPLETED"
    assert observed
    assert result["research_range"] == {"start": "2020-01-02", "end": "2020-12-31"}
    document = yaml.safe_load((output / "experiment.yaml").read_text())
    assert document["data"]["holdout_start"] == "2021-01-01"
    for sid in result["input_snapshot_ids"]:
        metadata = SnapshotStore(output / "inputs").manifest(sid)
        assert metadata["parent_snapshot"] in ids.values()
        assert metadata["request"]["end"] == "2020-12-31"
        assert b"2021-" not in (output / "inputs/snapshots" / sid / "source.csv").read_bytes()
    for sid, raw in originals.items():
        assert (root / "snapshots" / sid / "source.csv").read_bytes() == raw


def test_range_eligibility_retains_quality_checks_and_clips_actions(modern_library, tmp_path):
    from quantlab.web.research_inputs import prepare_research_inputs
    from quantlab.web.workflows import selected_snapshots

    root, synthetic_ids = modern_library
    ids = {}
    for symbol, sid in synthetic_ids.items():
        store = SnapshotStore(root)
        metadata = store.manifest(sid)
        raw = (root / "snapshots" / sid / "source.csv").read_bytes()
        bounds = metadata["request"]
        ids[symbol] = store.write(
            "explicit-unadjusted-test",
            DataRequest(
                symbol, date.fromisoformat(bounds["start"]), date.fromisoformat(bounds["end"])
            ),
            Download(raw, "invented fixture with test-only evidence", "unadjusted", False),
            store.read(sid),
            point_in_time=True,
            universe_membership_included=True,
        )
    request = ResearchRequest.model_validate(
        {**payload(ids), "start": "2020-01-02", "end": "2020-12-31"}
    )
    with pytest.raises(ValueError, match="corporate-action"):
        selected_snapshots(root, request)
    actions = root / "actions"
    actions.mkdir()
    for symbol, sid in ids.items():
        (actions / f"{sid}.json").write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "coverage_start": "2020-01-02",
                    "coverage_end": "2021-12-31",
                    "source": "test-only invented ledger",
                    "complete": True,
                    "splits": [{"date": "2021-06-01", "ratio": "2"}],
                    "dividends": [
                        {"ex_date": "2020-06-01", "pay_date": "2020-06-15", "amount": "1"},
                        {"ex_date": "2021-06-01", "pay_date": "2021-06-15", "amount": "1"},
                    ],
                }
            )
        )
    # Snapshot date coverage alone no longer blocks data selection.
    real_items = [s for s in snapshot_inventory(root)["items"] if s["id"] in ids.values()]
    assert all(s["eligible"] for s in real_items)
    assert set(selected_snapshots(root, request)) == {"AAA", "SPY"}
    with pytest.raises(ValueError, match="within every"):
        selected_snapshots(root, request.model_copy(update={"start": date(2019, 1, 1)}))
    destination = tmp_path / "ranged-inputs"
    derived = prepare_research_inputs(request, root, destination)
    for symbol, entry in derived.items():
        ledger = json.loads(Path(entry["actions"]).read_text())
        assert ledger["coverage_end"] == "2020-12-31"
        assert ledger["splits"] == []
        assert len(ledger["dividends"]) == 1
        metadata = SnapshotStore(destination).manifest(entry["snapshot_id"])
        assert metadata["point_in_time"] and metadata["universe_membership_included"]
        assert metadata["parent_snapshot"] == ids[symbol]


def test_snapshot_inventory_range_filters_and_validates_dates(modern_library, tmp_path):
    root, _ = modern_library
    catalog = tmp_path / "range-catalog.yaml"
    catalog.write_text("artifacts: []\n")
    app = create_app(
        Catalog(catalog, tmp_path), state_root=tmp_path / "range-state", workflow_library=root
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/workflows/snapshots?start=2020-01-02&end=2020-12-31")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        assert all(
            "reserved holdout" not in " ".join(s["blockers"]) for s in response.json()["items"]
        )
        assert client.get("/api/v1/workflows/snapshots?start=2020-01-02").status_code == 400
        assert (
            client.get("/api/v1/workflows/snapshots?start=2021-01-01&end=2020-01-01").status_code
            == 400
        )
