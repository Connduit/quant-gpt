"""Campaign acquisition must fail closed before any protected request or snapshot."""

import importlib.util
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from quantlab.data.providers.base import DataRequest

spec = importlib.util.spec_from_file_location(
    "phase12a", Path(__file__).parents[1] / "examples/phase12a_connectivity.py"
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def test_protected_request_rejected():
    with pytest.raises(ValueError, match="reserved equity holdout"):
        campaign.require_safe(DataRequest("AAPL", date(2018, 1, 2), date(2019, 1, 2)))


def test_challenge_does_not_create_snapshot(tmp_path, monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.params["d2"] == "20180110"
        return httpx.Response(200, content=b"<html>verify your browser</html>")

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), timeout=30),
    )
    monkeypatch.setattr(campaign, "ROOT", tmp_path)
    monkeypatch.setattr(campaign.subprocess, "check_output", lambda *a, **kw: "test-commit")
    (tmp_path / "docs/phase12").mkdir(parents=True)
    assert campaign.main() == 2
    report = json.loads((tmp_path / "docs/phase12/phase12a-connectivity.json").read_text())
    assert len(requests) == 2  # Direct client and the actual application provider.
    assert report["application_provider"]["error_type"] == "ProviderError"
    assert report["snapshots"] == []
    assert not (tmp_path / "data/phase12a/snapshots").exists()
