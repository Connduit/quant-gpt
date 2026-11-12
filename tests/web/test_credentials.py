import json
import stat
import time

import pytest
from fastapi.testclient import TestClient

from quantlab.web.app import create_app
from quantlab.web.catalog import Catalog
from quantlab.web.credentials import ProviderKeyStore

OPERATOR = "operator-credential-test-0000000000"
RESEARCHER = "researcher-credential-test-00000000"
VIEWER = "viewer-credential-test-00000000000"
KEY = "invented-alpaca-private-key"
SECRET = "invented-alpaca-private-secret"
DBKEY = "invented-databento-private-key"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for key in (
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "DATABENTO_API_KEY",
        "QUANTLAB_CREDENTIALS_MASTER_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "catalog.yaml"
    path.write_text("artifacts: []\n")
    app = create_app(
        Catalog(path, tmp_path),
        state_root=tmp_path / "state",
        tokens={OPERATOR: "operator", RESEARCHER: "researcher", VIEWER: "viewer"},
    )
    return app, tmp_path / "state"


def auth(token=OPERATOR):
    return {"Authorization": "Bearer " + token}


def test_save_status_at_rest_restart_and_removal(setup):
    app, root = setup
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/settings/providers/alpaca",
            headers=auth(),
            json={"key_id": KEY, "secret_key": SECRET, "confirmed": True},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "SAVED", "provider": "alpaca"}
        assert (
            client.put(
                "/api/v1/settings/providers/databento",
                headers=auth(),
                json={"api_key": DBKEY, "confirmed": True},
            ).status_code
            == 200
        )
        for route in ("/settings/providers", "/workflows/providers"):
            response = client.get("/api/v1" + route)
            assert all(item["configured"] for item in response.json()["items"])
            assert KEY not in response.text and SECRET not in response.text
            assert DBKEY not in response.text
        for path in root.rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                assert not any(value.encode() in raw for value in (KEY, SECRET, DBKEY))
        directory = root / "credentials"
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        for path in directory.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        restored = ProviderKeyStore(directory)
        assert restored.credentials("alpaca") == {
            "APCA_API_KEY_ID": KEY,
            "APCA_API_SECRET_KEY": SECRET,
        }
        assert restored.credentials("databento") == {"DATABENTO_API_KEY": DBKEY}
        assert (
            client.request(
                "DELETE",
                "/api/v1/settings/providers/alpaca",
                headers=auth(),
                json={"confirmed": True},
            ).status_code
            == 200
        )
        assert restored.credentials("alpaca") == {}
        assert restored.credentials("databento") == {"DATABENTO_API_KEY": DBKEY}


@pytest.mark.parametrize("token", [None, VIEWER, RESEARCHER])
def test_credentials_require_operator_role(setup, token):
    app, _ = setup
    with TestClient(app) as client:
        headers = auth(token) if token else {}
        assert (
            client.put(
                "/api/v1/settings/providers/alpaca",
                headers=headers,
                json={"key_id": KEY, "secret_key": SECRET, "confirmed": True},
            ).status_code
            == 403
        )
        assert (
            client.request(
                "DELETE",
                "/api/v1/settings/providers/alpaca",
                headers=headers,
                json={"confirmed": True},
            ).status_code
            == 403
        )
        assert not client.get("/api/v1/settings/providers", headers=headers).json()["editable"]


def test_validation_errors_do_not_echo_submitted_keys(setup):
    app, _ = setup
    with TestClient(app) as client:
        for payload in (
            {"key_id": KEY, "secret_key": SECRET},
            {"key_id": KEY, "secret_key": SECRET, "confirmed": False},
            {"key_id": KEY, "secret_key": "bad", "confirmed": True},
            {"key_id": KEY, "secret_key": SECRET, "confirmed": True, "extra": SECRET},
        ):
            response = client.put("/api/v1/settings/providers/alpaca", headers=auth(), json=payload)
            assert response.status_code == 422
            assert KEY not in response.text and SECRET not in response.text
        response = client.put(
            "/api/v1/settings/providers/alpaca",
            headers=auth(),
            json={"key_id": KEY, "secret_key": SECRET + " ", "confirmed": True},
        )
        assert response.status_code == 400 and SECRET not in response.text


def test_remote_credentials_require_https(setup):
    app, _ = setup
    with TestClient(
        app, base_url="http://dashboard.example", client=("203.0.113.2", 5000)
    ) as client:
        assert (
            client.put(
                "/api/v1/settings/providers/databento",
                headers=auth(),
                json={"api_key": DBKEY, "confirmed": True},
            ).status_code
            == 403
        )
    with TestClient(
        app, base_url="https://dashboard.example", client=("203.0.113.2", 5000)
    ) as client:
        assert (
            client.put(
                "/api/v1/settings/providers/databento",
                headers=auth(),
                json={"api_key": DBKEY, "confirmed": True},
            ).status_code
            == 200
        )


def test_saved_pair_overrides_environment_and_delete_restores_it(setup, monkeypatch):
    _, root = setup
    monkeypatch.setenv("APCA_API_KEY_ID", "environment-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "environment-secret")
    store = ProviderKeyStore(root / "credentials")
    assert store.status()["items"][0]["source"] == "environment"
    store.save("alpaca", {"APCA_API_KEY_ID": KEY, "APCA_API_SECRET_KEY": SECRET})
    assert store.credentials("alpaca")["APCA_API_KEY_ID"] == KEY
    assert store.status()["items"][0]["source"] == "dashboard"
    store.remove("alpaca")
    assert store.credentials("alpaca")["APCA_API_KEY_ID"] == "environment-key"
    assert store.status()["items"][0]["source"] == "environment"


def test_corrupt_store_fails_closed_without_environment_fallback(setup, monkeypatch):
    _, root = setup
    store = ProviderKeyStore(root / "credentials")
    store.save("databento", {"DATABENTO_API_KEY": DBKEY})
    (root / "credentials/providers.enc").write_bytes(b"broken ciphertext")
    monkeypatch.setenv("DATABENTO_API_KEY", "environment-key")
    with pytest.raises(ValueError, match="cannot be decrypted"):
        store.credentials("databento")


def test_saved_keys_reach_only_download_worker_without_persisting_plaintext(setup, monkeypatch):
    app, root = setup
    captured = []

    class Process:
        returncode = 0

        def __init__(self, *args, **kwargs):
            captured.append(kwargs["env"])

        def poll(self):
            return 0

    monkeypatch.setattr("quantlab.web.jobs.subprocess.Popen", Process)
    with TestClient(app) as client:
        client.put(
            "/api/v1/settings/providers/alpaca",
            headers=auth(),
            json={"key_id": KEY, "secret_key": SECRET, "confirmed": True},
        )
        response = client.post(
            "/api/v1/workflows/download",
            headers=auth(RESEARCHER),
            json={
                "symbols": ["AAPL"],
                "start": "2018-12-03",
                "end": "2018-12-04",
                "confirmed": True,
            },
        )
        assert response.status_code == 202
        deadline = time.monotonic() + 5
        while app.state.jobs.rows()[0]["status"] in ("QUEUED", "RUNNING"):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert captured[0]["APCA_API_KEY_ID"] == KEY
        assert captured[0]["APCA_API_SECRET_KEY"] == SECRET
        assert "DATABENTO_API_KEY" not in captured[0]
        assert "QUANTLAB_CREDENTIALS_MASTER_KEY" not in captured[0]
        for path in root.rglob("*.json*"):
            assert KEY not in path.read_text() and SECRET not in path.read_text()
        audit = [json.loads(line) for line in (root / "api-audit.jsonl").read_text().splitlines()]
        assert audit[0]["detail"] == {"provider": "alpaca"}
