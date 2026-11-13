"""Local development needs no browser secrets; remote requests keep role checks."""

import pytest
from fastapi.testclient import TestClient

from quantlab.web.app import from_environment


@pytest.fixture
def environment(tmp_path, monkeypatch):
    config = tmp_path / "catalog.yaml"
    config.write_text("artifacts: []\n")
    monkeypatch.setenv("QUANTLAB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("QUANTLAB_CATALOG", str(config))
    monkeypatch.setenv("QUANTLAB_BIND_HOST", "127.0.0.1")
    monkeypatch.delenv("QUANTLAB_LOCAL_DEV_AUTH", raising=False)
    for role in ("VIEWER", "OPERATOR", "RESEARCHER"):
        monkeypatch.delenv(f"QUANTLAB_{role}_TOKEN", raising=False)
    return monkeypatch


def test_default_local_access_supports_both_roles_without_exposing_tokens(environment):
    environment.setenv("QUANTLAB_OPERATOR_TOKEN", "ignored-short-placeholder")
    app = from_environment()
    submitted = []
    app.state.jobs.submit_workflow = lambda *args: submitted.append(args) or "test-job"
    with TestClient(app) as client:
        response = client.get("/api/v1/session")
        assert response.json() == {"local_development": True, "role": "local_developer"}
        assert "ignored-short-placeholder" not in response.text
        assert client.get("/api/v1/settings/providers").json()["editable"]
        assert (
            client.put(
                "/api/v1/settings/providers/databento",
                json={
                    "api_key": "invented-test-key",
                    "confirmed": True,
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/workflows/download",
                json={
                    "symbols": ["SPY"],
                    "start": "2024-01-02",
                    "end": "2024-01-31",
                    "confirmed": True,
                },
            ).status_code
            == 202
        )
        assert submitted
        assert client.get("/api/v1/health").json()["live_enabled"] is False


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_foreign_origins_cannot_use_local_access(environment, headers):
    with TestClient(from_environment()) as client:
        assert client.get("/api/v1/session", headers=headers).status_code == 403


def test_foreign_hosts_and_peers_do_not_get_development_roles(environment):
    with TestClient(from_environment(), base_url="http://evil.example") as client:
        assert client.get("/api/v1/session").json()["local_development"] is False
        assert not client.get("/api/v1/settings/providers").json()["editable"]
    with TestClient(from_environment(), client=("203.0.113.10", 1234)) as client:
        assert client.get("/api/v1/session").status_code == 401


def test_strict_local_auth_and_nonlocal_bind_stay_protected(environment):
    environment.setenv("QUANTLAB_LOCAL_DEV_AUTH", "0")
    token = "researcher-token-test-00000000000"
    environment.setenv("QUANTLAB_RESEARCHER_TOKEN", token)
    with TestClient(from_environment()) as client:
        assert not client.get("/api/v1/session").json()["local_development"]
        assert (
            client.get("/api/v1/session", headers={"Authorization": f"Bearer {token}"}).json()[
                "role"
            ]
            == "researcher"
        )
        assert not client.get("/api/v1/settings/providers").json()["editable"]
    environment.setenv("QUANTLAB_BIND_HOST", "0.0.0.0")
    environment.setenv("QUANTLAB_LOCAL_DEV_AUTH", "1")
    with pytest.raises(ValueError, match="loopback bind"):
        from_environment()
    environment.delenv("QUANTLAB_LOCAL_DEV_AUTH")
    with TestClient(from_environment()) as client:
        assert client.get("/api/v1/session").status_code == 401
