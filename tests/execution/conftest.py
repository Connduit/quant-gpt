from datetime import UTC, datetime, timedelta

import pytest

from quantlab.discovery.common import fingerprint
from quantlab.execution.authority import Authority
from quantlab.execution.controller import SandboxController
from quantlab.execution.mock import MockBroker
from quantlab.paper.events import MarketEvent

T = datetime(2024, 6, 3, 13, 30, tzinfo=UTC)


def quote(n=0, *, bid="100", ask="100.02"):
    at = T + timedelta(seconds=n)
    return MarketEvent(
        "SPY", "explicit_mock", at, at, "quote", "replay", str(n), bid, ask, 1000, 1000
    )


def fixture_approval(controller, *, model_hash=None, baseline=None):
    return controller.authority.sign(
        {
            "mode": "BROKER_SANDBOX",
            "account_id": controller.authority.account_id,
            "kind": "SANDBOX_TEST",
            "strategy_id": "test",
            "strategy_version": "test-only-v1",
            "strategy_definition_hash": fingerprint(controller.definitions["test"]),
            "model_hash": model_hash,
            "source_sha256": controller.configuration["source_sha256"],
            "risk_hash": fingerprint(controller.limits.__dict__),
            "symbols": ["SPY"],
            "actor": "simulated_test_operator",
            "reason": "Explicit mock engineering demonstration only",
            "origin": "simulated_fixture",
            "model_baseline": baseline or {},
            "expires_at": (T + timedelta(days=1)).isoformat(),
        }
    )


@pytest.fixture
def controller(tmp_path):
    authority = Authority(
        b"test-only-authorization-key-32bytes!",
        mode="BROKER_SANDBOX",
        account_id="mock-paper-account",
    )
    broker = MockBroker(authority, tmp_path / "broker.json")
    controller = SandboxController(tmp_path / "oms.sqlite", broker, authority, symbols=["SPY"])
    controller.bootstrap(now=T)
    controller.approve(fixture_approval(controller), now=T)
    broker.mark("SPY", "100.01")
    controller.receive(quote(), now=T)
    assert controller.reconcile(now=T)["okay"]
    controller.arm("test", now=T, reason="Explicit mock-only test approval")
    yield controller
    controller.close()
    broker.close()
