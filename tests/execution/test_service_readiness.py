import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from conftest import T, fixture_approval

from quantlab.execution.authority import ExecutionDenied
from quantlab.execution.readiness import readiness
from quantlab.execution.service import configuration


def test_strategy_definition_and_expired_approvals_cannot_be_substituted(controller):
    signed = fixture_approval(controller)
    changed = deepcopy(signed["body"])
    changed["strategy_definition_hash"] = "changed-definition"
    with pytest.raises(ExecutionDenied):
        controller.approve(controller.authority.sign(changed), now=T)
    with pytest.raises(ExecutionDenied):
        controller.approve(signed, now=T + timedelta(days=2))


def test_live_and_unbounded_service_configuration_fail_before_network(tmp_path):
    path = tmp_path / "execution.yaml"
    path.write_text("mode: LIVE\nbroker: alpaca_paper\n")
    with pytest.raises(ExecutionDenied):
        configuration(path)
    root = Path(__file__).resolve().parents[2]
    doc = yaml.safe_load((root / "configs/execution.sandbox.example.yaml").read_text())
    doc["strategy"]["target_units"] = 10000
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError):
        configuration(path)


def test_readiness_does_not_infer_live_eligibility_from_test_artifacts(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "milestone-11-tests.json").write_text(json.dumps({"python_passed": 999}))
    result = readiness(tmp_path)
    assert result["status"] == "NOT_READY_FOR_LIVE" and not result["live_enabled"]
    assert result["eligible_strategy_ids"] == [] and result["holdout_state"] == "UNKNOWN_OR_CHANGED"


def test_deployment_separates_credentials_and_starts_no_broker_by_default():
    root = Path(__file__).resolve().parents[2]
    doc = yaml.safe_load((root / "deploy/compose.yaml").read_text())
    app = doc["services"]["dashboard"]
    broker = doc["services"]["broker-sandbox"]
    assert broker["profiles"] == ["sandbox"]
    assert not any("ALPACA" in key or "AUTHORIZATION_KEY" in key for key in app["environment"])
    assert "--arm-approved-sandbox-test" not in broker["command"]
    assert app["read_only"] and broker["read_only"]


def test_signed_kill_reset_keeps_strategy_paused(controller):
    c = controller
    c.kill(now=T, reason="test kill")
    assert c.reconcile(now=T)["okay"]
    authorization = c.authority.sign(
        {
            "mode": "BROKER_SANDBOX",
            "account_id": c.authority.account_id,
            "operation": "kill_reset",
            "actor": "test operator",
            "expires_at": (T + timedelta(hours=1)).isoformat(),
        }
    )
    c.reset_kill(authorization, now=T, reason="reviewed mock reset")
    assert not c.state["killed"] and c.state["strategies"]["test"]["execution"] == "PAUSED"


def test_monitoring_service_never_submits_or_cancels_without_arming(tmp_path, monkeypatch):
    from conftest import quote

    import quantlab.execution.service as module
    from quantlab.execution.authority import Authority
    from quantlab.execution.mock import MockBroker

    root = Path(__file__).resolve().parents[2]
    doc = yaml.safe_load((root / "configs/execution.sandbox.example.yaml").read_text())
    doc["database"] = str(tmp_path / "service.sqlite")
    doc["approval_file"] = str(tmp_path / "approval.json")
    doc["account_id"] = "mock-paper-account"
    config = tmp_path / "execution.yaml"
    config.write_text(yaml.safe_dump(doc))
    secret = "test-private-key-not-a-real-secret!"
    monkeypatch.setenv("QUANTLAB_SANDBOX_AUTHORIZATION_KEY", secret)
    a = Authority(secret.encode(), mode="BROKER_SANDBOX", account_id=doc["account_id"])
    broker = MockBroker(a)
    broker.mark("SPY", "100.01")
    monkeypatch.setattr(module, "AlpacaPaperBroker", lambda authority: broker)

    class Feed:
        def poll(self):
            return [quote()]

        def close(self):
            pass

    monkeypatch.setattr(module, "AlpacaQuotes", lambda *args, **kwargs: Feed())

    class Clock:
        @staticmethod
        def now(tz):
            return T

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    signed = module.approval_document(
        doc, a, actor="test-only operator", reason="monitoring test", now=T
    )
    Path(doc["approval_file"]).write_text(json.dumps(signed))
    module.run_service(config, arm=False, max_cycles=1)
    assert broker.submit_calls == 0 and not broker.orders
