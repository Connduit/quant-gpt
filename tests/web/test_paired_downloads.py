"""Separate training/protected archives and metadata-only selection gates."""

import csv
import io
import json
from datetime import date

import exchange_calendars as xcals
import pytest
from fastapi.testclient import TestClient

from quantlab.data.protection import check_saved_job, reserve_plan
from quantlab.data.providers.base import Download, ProviderError
from quantlab.data.storage import SnapshotStore
from quantlab.web.app import create_app
from quantlab.web.catalog import Catalog
from quantlab.web.workflow_worker import acquire, acquire_pair
from quantlab.web.workflows import (
    PairedDownloadRequest,
    ResearchRequest,
    selected_snapshots,
    snapshot_inventory,
)

TOKEN = "paired-download-researcher-000000000000000"


def payload():
    return dict(
        provider="alpaca",
        alpaca_feed="sip",
        symbols=["AAPL", "SPY"],
        start="2020-01-02",
        split_date="2020-02-03",
        end="2020-02-28",
        confirmed=True,
    )


@pytest.fixture
def provider(monkeypatch):
    class Fake:
        name = "invented-paired-provider"

        def __init__(self):
            self.calls = []
            self.fail = None

        def fetch(self, request):
            self.calls.append(request)
            if self.fail == request.symbol and request.start >= date(2020, 2, 3):
                raise ProviderError("invented test failure")
            days = xcals.get_calendar(
                "XNYS", start="2020-01-01", end="2020-12-31"
            ).sessions_in_range(str(request.start), str(request.end))
            text = io.StringIO()
            writer = csv.writer(text)
            writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            for day in days:
                writer.writerow([str(day.date()), 100, 101, 99, 100, 1000000])
            return Download(
                text.getvalue().encode(),
                "invented fixture, not market evidence",
                "unadjusted",
                False,
            )

    value = Fake()
    monkeypatch.setattr(
        "quantlab.data.providers.factory.create_provider", lambda *args, **kwargs: value
    )
    return value


def test_pair_requests_separate_ranges_roles_and_verified_cache(provider, tmp_path):
    result = acquire_pair(payload(), tmp_path, tmp_path)
    assert result["status"] == "COMPLETED"
    assert len(provider.calls) == 4
    assert all(c.end < date(2020, 2, 3) for c in provider.calls[:2])
    assert all(c.start >= date(2020, 2, 3) for c in provider.calls[2:])
    assert result["dataset_plan"]["state"] == "SEALED"
    assert result["holdout_evaluated"] is False
    for row in result["snapshots"]:
        root = tmp_path / "protected" if row["dataset_role"] == "protected_test" else tmp_path
        metadata = SnapshotStore(root).inspect(row["snapshot_id"])
        assert metadata["dataset_role"] == row["dataset_role"]
        assert metadata["request"]["end"] == (
            "2020-02-28" if row["dataset_role"] == "protected_test" else "2020-02-02"
        )
    again = acquire_pair(payload(), tmp_path, tmp_path)
    assert all(row["status"] == "CACHED" for row in again["snapshots"])
    assert len(provider.calls) == 4
    assert len(json.loads((tmp_path / "dataset-plans.json").read_text())) == 1
    items = snapshot_inventory(tmp_path, research_mode="exploratory")["items"]
    assert len(items) == 4
    assert all(not s["eligible"] for s in items if s["dataset_role"] == "protected_test")
    assert all(s["eligible"] for s in items if s["dataset_role"] == "training")


def test_protected_snapshot_refused_before_price_reads(provider, tmp_path, monkeypatch):
    from quantlab.backtesting.data import DailyData

    result = acquire_pair(payload(), tmp_path, tmp_path)
    protected = next(row for row in result["snapshots"] if row["dataset_role"] == "protected_test")
    store = SnapshotStore(tmp_path / "protected")

    def forbidden(*args, **kwargs):
        pytest.fail("Protected price payload was opened for routine research")

    monkeypatch.setattr(store, "manifest", forbidden)
    with pytest.raises(ValueError, match="Protected test"):
        DailyData.from_snapshot(store, protected["snapshot_id"])
    with pytest.raises(ValueError, match="Protected test"):
        store.prefix_manifest(protected["snapshot_id"], date(2030, 1, 1))


def test_reservations_cannot_be_moved_into_training_or_manually_redownloaded(provider, tmp_path):
    acquire_pair(payload(), tmp_path, tmp_path)
    with pytest.raises(ValueError, match="reserved test dates"):
        reserve_plan(
            tmp_path,
            PairedDownloadRequest.model_validate({**payload(), "split_date": "2020-02-10"}),
        )
    single = {k: v for k, v in payload().items() if k != "split_date"}
    count = len(provider.calls)
    with pytest.raises(ValueError, match="reserved test dates"):
        acquire(single, tmp_path, tmp_path)
    assert len(provider.calls) == count


def test_partial_failure_keeps_successful_test_data_sealed(provider, tmp_path):
    provider.fail = "AAPL"
    result = acquire_pair(payload(), tmp_path, tmp_path)
    assert result["status"] == "PARTIAL"
    assert len(result["snapshots"]) == 4
    assert result["dataset_plan"]["state"] == "SEALED"
    spy = next(
        s
        for s in snapshot_inventory(tmp_path, research_mode="exploratory")["items"]
        if s["symbol"] == "SPY" and s["dataset_role"] == "protected_test"
    )
    assert not spy["eligible"]


def test_older_saved_job_is_blocked_by_new_reservation(provider, tmp_path):
    root = tmp_path / "library"
    single = {k: v for k, v in payload().items() if k != "split_date"}
    result = acquire(single, root, tmp_path)
    source = tmp_path / "old-job"
    (source / "inputs").mkdir(parents=True)
    import shutil

    shutil.copytree(root / "snapshots", source / "inputs/snapshots")
    (source / "result.json").write_text(
        json.dumps({"input_snapshot_ids": [r["snapshot_id"] for r in result["snapshots"]]})
    )
    reserve_plan(root, PairedDownloadRequest.model_validate(payload()))
    with pytest.raises(ValueError, match="protected test reservation"):
        check_saved_job(source, root)
    ids = [r["snapshot_id"] for r in result["snapshots"]]
    request = ResearchRequest(
        workflow="training",
        research_mode="exploratory",
        name="Old input test",
        models=["ridge"],
        snapshot_ids=ids,
        start="2020-01-02",
        end="2020-01-31",
        confirmed=True,
    )
    with pytest.raises(ValueError, match="reserved test dates"):
        selected_snapshots(root, request)


def test_paired_api_roles_bounds_and_no_browser_paths(tmp_path, monkeypatch):
    config = tmp_path / "catalog.yaml"
    config.write_text("artifacts: []\n")
    app = create_app(
        Catalog(config, tmp_path), state_root=tmp_path / "state", tokens={TOKEN: "researcher"}
    )
    captured = []
    monkeypatch.setattr(
        app.state.jobs, "submit_workflow", lambda *args: captured.append(args) or "queued-pair"
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/workflows/download-pair", json=payload()).status_code == 403
        headers = {"Authorization": "Bearer " + TOKEN}
        response = client.post("/api/v1/workflows/download-pair", json=payload(), headers=headers)
        assert response.status_code == 202
        assert captured[0][0] == "download_pair"
        for change in (
            {"split_date": "2020-01-02"},
            {"split_date": "2020-03-01"},
            {"path": "/tmp/evil"},
            {"provider": "databento"},
        ):
            assert (
                client.post(
                    "/api/v1/workflows/download-pair", json={**payload(), **change}, headers=headers
                ).status_code
                == 422
            )


def test_paired_worker_receives_data_keys_without_broker_keys(tmp_path, monkeypatch):
    from quantlab.web.jobs import JobManager

    captured = []
    for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "QUANTLAB_ALPACA_PAPER_KEY"):
        monkeypatch.setenv(key, "test-secret-not-persisted")

    class Process:
        returncode = 0

        def __init__(self, *args, **kwargs):
            captured.append(kwargs["env"])

        def poll(self):
            return 0

    monkeypatch.setattr("quantlab.web.jobs.subprocess.Popen", Process)
    manager = JobManager(tmp_path / "jobs")
    try:
        manager.submit_workflow("download_pair", payload(), tmp_path / "library", tmp_path)
    finally:
        manager.close()
    assert captured and "APCA_API_KEY_ID" in captured[0] and "APCA_API_SECRET_KEY" in captured[0]
    assert "QUANTLAB_ALPACA_PAPER_KEY" not in captured[0]
    assert "test-secret-not-persisted" not in "".join(
        p.read_text() for p in (tmp_path / "jobs/requests").glob("*.json")
    )
