import json
import sqlite3
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from quantlab.web.app import create_app
from quantlab.web.catalog import Catalog
from quantlab.web.jobs import JobManager

TOKEN = "operator-test-token-00000000000"
RESEARCH = "researcher-test-token-000000000"


@pytest.fixture
def api(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "account": {"equity": "100000"},
                "killed": True,
                "equity_history": [
                    {"at": "2024-01-01T00:00:00Z", "equity": "100000"},
                    {"at": "2024-01-02T00:00:00Z", "equity": "99000"},
                ],
                "api_key": "must-not-be-exposed",
                "nested": {"password": "also-secret"},
            }
        )
    )
    database = tmp_path / "paper.sqlite"
    from datetime import UTC, datetime, timedelta

    from quantlab.paper.events import MarketEvent
    from quantlab.paper.orders import PaperOrder
    from quantlab.paper.runtime import PaperRuntime

    runtime = PaperRuntime(database, symbols=["SPY"], slippage_ticks=0)
    runtime.register("bad", capital=100000, experimental=True)
    start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)

    def observe(seconds, price):
        t = start + timedelta(seconds=seconds)
        event = MarketEvent(
            "SPY",
            "test",
            t,
            t,
            "quote",
            "replay",
            str(seconds),
            str(price),
            str(price),
            10000,
            10000,
        )
        runtime.ingest(event, now=t)

    observe(0, 100)
    runtime.control("connect", reason="test feed")
    runtime.control("resume", strategy="bad", reason="explicit test replay")
    runtime.submit(PaperOrder("test", "bad", "SPY", 100, start.isoformat()), now=start)
    observe(1, 100)
    observe(2, 90)
    runtime.control("kill", reason="test account halt")
    runtime.close()
    config = tmp_path / "catalog.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "artifacts": [
                    {
                        "id": "paper",
                        "kind": "paper",
                        "label": "Test replay",
                        "mode": "REPLAY",
                        "path": "report.json",
                        "database": "paper.sqlite",
                    }
                ]
            }
        )
    )
    app = create_app(
        Catalog(config, tmp_path),
        state_root=tmp_path / "state",
        tokens={TOKEN: "operator", RESEARCH: "researcher"},
    )
    with TestClient(app) as client:
        yield client, database


def test_list_filter_pagination_schema_and_series(api):
    client, _ = api
    response = client.get("/api/v1/artifacts?kind=paper&limit=1&search=replay")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1 and data["items"][0]["status"] == "HALTED"
    detail = client.get("/api/v1/artifacts/paper").json()
    assert "api_key" not in detail["data"] and detail["data"]["nested"] == {}
    assert detail["series"][-1]["drawdown"] == pytest.approx(-0.010005)
    assert client.get("/api/v1/artifacts?limit=10000").status_code == 422
    assert client.get("/api/v1/artifacts?kind=secrets").status_code == 422
    assert client.get("/api/v1/artifacts/../../.env").status_code == 404


def test_paper_controls_require_role_confirmation_and_do_not_promote(api):
    client, database = api
    body = {"action": "kill", "reason": "operator emergency", "confirmed": True}
    assert client.post("/api/v1/paper/paper/control", json=body).status_code == 403
    headers = {"Authorization": "Bearer " + TOKEN}
    assert (
        client.post(
            "/api/v1/paper/paper/control", json={**body, "confirmed": False}, headers=headers
        ).status_code
        == 422
    )
    response = client.post("/api/v1/paper/paper/control", json=body, headers=headers)
    assert response.status_code == 202 and response.json()["applied"] is False
    body = {"action": "resume", "strategy": "bad", "reason": "attempt promotion", "confirmed": True}
    assert client.post("/api/v1/paper/paper/control", json=body, headers=headers).status_code == 409
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM controls").fetchone()[0] == 1


def test_unauthenticated_nonlocal_and_invalid_token_fail_closed(tmp_path):
    config = tmp_path / "catalog.yaml"
    config.write_text("artifacts: []")
    app = create_app(
        Catalog(config, tmp_path),
        state_root=tmp_path / "state",
        local_reads=False,
        tokens={TOKEN: "operator"},
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 401
        assert (
            client.get("/api/v1/health", headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )
        health = client.get("/api/v1/health", headers={"Authorization": "Bearer " + TOKEN}).json()
        assert health["live_enabled"] is False and health["streaming_verified"] is False
        assert (
            "access-control-allow-origin"
            not in client.options(
                "/api/v1/health", headers={"Origin": "https://evil.example"}
            ).headers
        )


def test_job_allowlist_blocks_arbitrary_commands(api):
    client, _ = api
    headers = {"Authorization": "Bearer " + RESEARCH}
    assert (
        client.post(
            "/api/v1/jobs", json={"name": "sh -c echo insecure", "confirmed": True}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/jobs",
            json={"name": "anything", "confirmed": True, "command": "shell"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/jobs",
            json={"name": "anything", "confirmed": True},
            headers={"Authorization": "Bearer " + TOKEN},
        ).status_code
        == 403
    )


def test_catalog_escape_and_id_validation(tmp_path):
    config = tmp_path / "catalog.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "artifacts": [
                    {"id": "bad", "kind": "research", "label": "x", "path": "../secrets.json"}
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="escapes"):
        Catalog(config, tmp_path)


def test_actual_saved_artifacts_load_without_bar_or_holdout_access(tmp_path):
    workspace = Path(__file__).resolve().parents[2]
    catalog = Catalog(workspace / "configs/dashboard.catalog.yaml", workspace)
    records = catalog.index()
    assert len(records) >= 9
    paper = catalog.document("archival-paper-replay")
    assert paper["holdout_accessed"] is False and paper["restart_reconciled"] is True
    assert catalog.series("equal-portfolio-backtest")
    assert catalog.document("futures-research")["paper_trading_shortlist"] == []


def test_job_restart_never_blindly_retries_uncertain_jobs(tmp_path):
    manager = JobManager(tmp_path)
    with manager.connection() as db:
        db.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?)", ("uncertain", "test", "RUNNING", "2024-01-01", "")
        )
    manager.pool.shutdown()
    recovered = JobManager(tmp_path)
    try:
        assert recovered.rows()[0]["status"] == "RECOVERY_REQUIRED"
        assert "workers" in recovered.rows()[0]["detail"]
    finally:
        recovered.close()


def test_corrupt_paper_state_is_not_presented_as_current_health(api):
    client, database = api
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT payload FROM state").fetchone()[0])
        state["killed"] = False
        db.execute("UPDATE state SET payload=?", (json.dumps(state),))
    assert client.get("/api/v1/artifacts/paper").status_code == 503
    response = client.get("/api/v1/health")
    assert response.status_code == 200 and response.json()["catalog_errors"]
    assert response.headers["cache-control"] == "no-store"


def test_production_spa_refresh_keeps_api_paths_separate(tmp_path):
    config = tmp_path / "catalog.yaml"
    config.write_text("artifacts: []")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>Test app</html>")
    app = create_app(Catalog(config, tmp_path), state_root=tmp_path / "state", frontend=frontend)
    with TestClient(app) as client:
        assert "Test app" in client.get("/research").text
        assert client.get("/api/v1/nonexistent").status_code == 404
