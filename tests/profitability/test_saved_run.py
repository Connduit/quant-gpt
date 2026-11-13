"""Invented fixtures exercise the full saved-run path, not empirical profitability."""

import json
from datetime import date

import pytest

from quantlab.data.providers.base import DataRequest, Download
from quantlab.data.storage import SnapshotStore
from quantlab.profitability.runner import run_profitability
from quantlab.research.synthetic import synthetic_snapshots
from quantlab.web.workflow_worker import execute
from quantlab.web.workflows import ProfitabilityRequest


@pytest.fixture
def saved_run(tmp_path):
    library = tmp_path / "library"
    originals, days = synthetic_snapshots(library, 250)
    ids = []
    for symbol, sid in originals.items():
        store = SnapshotStore(library)
        raw = (store.root / sid / "source.csv").read_bytes()
        ids.append(
            store.write(
                "mock-raw-provider",
                DataRequest(symbol, days[0], days[-1]),
                Download(raw, "INVENTED test fixture, not market evidence", "unadjusted", False),
                store.read(sid),
            )
        )
    payload = dict(
        workflow="training",
        research_mode="exploratory",
        name="Test-only predictions",
        snapshot_ids=ids,
        models=["ridge", "logistic"],
        start=str(days[0]),
        end=str(days[-1]),
        horizon=5,
        training_sessions=60,
        validation_sessions=20,
        test_sessions=60,
        top_n=2,
        confirmed=True,
    )
    source = tmp_path / "source"
    result = execute({"workflow": "training", "library": str(library), "payload": payload}, source)
    assert result["status"] == "COMPLETED", result
    request = ProfitabilityRequest(
        source_job_id="a" * 32,
        model="ridge",
        start=days[0],
        end=days[-1],
        research_mode="exploratory",
        confirmed=True,
    )
    return source, request


def test_full_profitability_path_retains_limits_and_exports(saved_run, tmp_path):
    source, request = saved_run
    report = run_profitability(source, request, tmp_path / "evaluation", tmp_path / "registry")
    assert report["performance_kind"] == "exploratory_backtest"
    assert (
        not report["qualified"] and not report["promotion_allowed"] and not report["live_enabled"]
    )
    assert report["data_limitations"]
    assert set(report["scenarios"]) == {"low", "baseline", "high"}
    base = report["scenarios"]["baseline"]["strategies"]
    assert set(base) == {"ml", "spy_buy_hold", "equal_weight", "momentum", "mean_reversion", "cash"}
    assert base["cash"]["net"]["total_return"] == 0
    assert base["ml"]["net"]["fill_count"] > 0
    assert base["ml"]["costs"]["total"] > 0
    assert base["ml"]["monthly_returns"] and base["ml"]["yearly_returns"]
    assert base["ml"]["net"]["market_impact_cost"] > 0
    assert report["statistical_validation"]["status"] == "NOT_VALIDATED"
    assert report["statistical_validation"]["final_holdout"] == "NOT_READ_OR_EVALUATED"
    assert len(report["parameter_sensitivity"]) == 4
    for scenario in report["scenarios"]:
        for strategy in base:
            path = tmp_path / "evaluation" / scenario / strategy
            assert (path / "trades.csv").is_file()
            assert (path / "signals.csv").is_file()
            assert (path / "positions.csv").is_file()
    assert report["equity_curve"][-1]["date"] == str(request.end)
    assert float(base["ml"]["net"]["final_equity"]) == pytest.approx(
        report["equity_curve"][-1]["net_equity"]
    )


def test_saved_hash_and_strict_data_gates(saved_run, tmp_path):
    source, request = saved_run
    with pytest.raises(ValueError, match="Strict profitability"):
        run_profitability(
            source,
            request.model_copy(update={"research_mode": "strict"}),
            tmp_path / "strict",
            tmp_path / "registry",
        )
    prediction = source / "research/out_of_sample_predictions.parquet"
    prediction.write_bytes(prediction.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        run_profitability(source, request, tmp_path / "bad-hash", tmp_path / "registry")


def test_protected_source_rejected_before_prediction_read(saved_run, tmp_path):
    source, request = saved_run
    result = json.loads((source / "result.json").read_text())
    result["request"]["start"] = "2016-01-01"
    result["request"]["end"] = "2019-12-31"
    (source / "result.json").write_text(json.dumps(result))
    (source / "research/out_of_sample_predictions.parquet").unlink()
    with pytest.raises(ValueError, match="protected 2019"):
        run_profitability(source, request, tmp_path / "protected", tmp_path / "registry")
    with pytest.raises(ValueError, match="protected 2019"):
        ProfitabilityRequest(
            source_job_id="a" * 32, start=date(2018, 1, 1), end=date(2019, 2, 1), confirmed=True
        )


def test_profitability_dashboard_role_queue_and_real_worker(saved_run, tmp_path):
    import shutil
    import time

    from fastapi.testclient import TestClient

    from quantlab.web.app import create_app
    from quantlab.web.catalog import Catalog

    source, request = saved_run
    state = tmp_path / "dashboard-state"
    destination = state / "jobs" / request.source_job_id / "artifacts"
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("artifacts: []\n")
    token = "phase12c-researcher-0000000000000000"
    app = create_app(Catalog(catalog, tmp_path), state_root=state, tokens={token: "researcher"})
    with app.state.jobs.connection() as connection:
        connection.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?)",
            (request.source_job_id, "training-retained", "COMPLETED", "2026-01-01", "fixture"),
        )
    headers = {"Authorization": "Bearer " + token}
    with TestClient(app) as client:
        body = request.model_dump(mode="json")
        assert client.post("/api/v1/workflows/profitability", json=body).status_code == 403
        assert (
            client.post(
                "/api/v1/workflows/profitability",
                json={**body, "path": "/tmp/evil"},
                headers=headers,
            ).status_code
            == 422
        )
        queued = client.post("/api/v1/workflows/profitability", json=body, headers=headers)
        assert queued.status_code == 202, queued.text
        identity = queued.json()["id"]
        deadline = time.monotonic() + 45
        while next(r for r in app.state.jobs.rows() if r["id"] == identity)["status"] in (
            "QUEUED",
            "RUNNING",
        ):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        result = client.get(f"/api/v1/workflows/jobs/{identity}").json()["result"]
        assert result["status"] == "COMPLETED", result
        assert not result["report"]["qualified"]
        download = client.get(f"/api/v1/workflows/jobs/{identity}/profitability.zip")
        assert download.status_code == 200
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert "baseline/ml/trades.csv" in archive.namelist()
            assert "profitability_report.json" in archive.namelist()
            assert not any("model.joblib" in name for name in archive.namelist())


def test_input_manifest_holdout_checked_before_prediction_payload(saved_run, tmp_path):
    from quantlab.data.storage import digest

    source, request = saved_run
    result = json.loads((source / "result.json").read_text())
    sid = result["input_snapshot_ids"][0]
    old = source / "inputs/snapshots" / sid
    metadata = json.loads((old / "manifest.json").read_text())
    metadata["request"].update(start="2018-01-01", end="2019-12-31")
    new_sid = digest(json.dumps(metadata, sort_keys=True).encode())
    new = old.parent / new_sid
    new.mkdir()
    (new / "manifest.json").write_text(json.dumps(metadata))
    result["input_snapshot_ids"][0] = new_sid
    (source / "result.json").write_text(json.dumps(result))
    (source / "research/out_of_sample_predictions.parquet").unlink()
    with pytest.raises(ValueError, match="protected 2019"):
        run_profitability(source, request, tmp_path / "blocked-manifest", tmp_path / "registry")


def test_fold_clock_evidence_is_cross_checked(saved_run, tmp_path):
    source, request = saved_run
    result = json.loads((source / "result.json").read_text())
    result["report"]["folds"][0]["fitted_at"] = "2021-01-01T00:00:00+00:00"
    (source / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="fold evidence"):
        run_profitability(source, request, tmp_path / "clock-mismatch", tmp_path / "registry")
