import httpx
import pytest
from conftest import T

from quantlab.execution.authority import Authority, ExecutionDenied
from quantlab.execution.backup import backup, restore
from quantlab.execution.broker import (
    AlpacaPaperBroker,
    BrokerRejected,
    BrokerUnavailable,
    BrokerUncertain,
)
from quantlab.execution.controller import SandboxController


def authority():
    return Authority(
        b"test-private-key-not-a-real-secret!", mode="BROKER_SANDBOX", account_id="paper-id"
    )


def test_official_paper_endpoints_and_mutation_capabilities():
    requests = []

    def respond(request):
        assert request.url.host == "paper-api.alpaca.markets" and request.url.scheme == "https"
        assert request.headers["APCA-API-SECRET-KEY"] == "test-paper-secret"
        requests.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/v2/account":
            return httpx.Response(200, json={"id": "paper-id"})
        if (
            request.url.path in ("/v2/positions", "/v2/account/activities")
            or request.method == "GET"
            and request.url.path == "/v2/orders"
        ):
            return httpx.Response(200, json=[])
        if request.url.path == "/v2/orders:by_client_order_id":
            return httpx.Response(404)
        return httpx.Response(200, json={"id": "paper-order", "status": "new"})

    a = authority()
    broker = AlpacaPaperBroker(
        a,
        credentials=("test-paper-key", "test-paper-secret"),
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    assert broker.account()["id"] == "paper-id" and not broker.external_verified
    assert (
        broker.positions() == []
        and broker.open_orders() == []
        and broker.activities(T.isoformat()) == []
    )
    assert broker.by_client_id("stable") is None
    payload = {
        "symbol": "SPY",
        "qty": "1",
        "type": "market",
        "side": "buy",
        "time_in_force": "day",
        "client_order_id": "stable",
    }
    with pytest.raises(ExecutionDenied):
        broker.submit(payload, {}, now=T)
    broker.submit(payload, a.permit("submit", payload, now=T), now=T)
    body = {"order_id": "paper-order"}
    broker.cancel("paper-order", a.permit("cancel", body, now=T), now=T)
    replacement = {"qty": "2"}
    body = {"order_id": "paper-order", "replacement": replacement}
    broker.replace("paper-order", replacement, a.permit("replace", body, now=T), now=T)
    assert ("POST", "/v2/orders") in requests and ("PATCH", "/v2/orders/paper-order") in requests
    broker.close()


def test_transport_and_auth_failures_never_fall_back_or_retry():
    a = authority()
    calls = []

    def timeout(request):
        calls.append(request.url.host)
        raise httpx.ReadTimeout("simulated uncertain response")

    broker = AlpacaPaperBroker(
        a, credentials=("test", "test"), client=httpx.Client(transport=httpx.MockTransport(timeout))
    )
    payload = {"symbol": "SPY", "qty": "1"}
    with pytest.raises(BrokerUncertain):
        broker.submit(payload, a.permit("submit", payload, now=T), now=T)
    assert calls == ["paper-api.alpaca.markets"]
    broker.close()
    broker = AlpacaPaperBroker(
        a,
        credentials=("test", "test"),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))),
    )
    with pytest.raises(BrokerRejected, match="401"):
        broker.account()
    broker.close()


def test_account_identity_redirect_and_missing_coverage_fail_closed():
    a = authority()
    broker = AlpacaPaperBroker(
        a,
        credentials=("test", "test"),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"id": "wrong-account"})
            )
        ),
    )
    with pytest.raises(ExecutionDenied):
        broker.account()
    broker.close()
    with pytest.raises(ValueError, match="redirects"):
        AlpacaPaperBroker(
            a, credentials=("test", "test"), client=httpx.Client(follow_redirects=True)
        )
    broker = AlpacaPaperBroker(
        a,
        credentials=("test", "test"),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))),
    )
    with pytest.raises(BrokerUnavailable):
        broker.positions()
    broker.close()


def test_consistent_backup_restore_stays_disarmed(controller, tmp_path):
    database = controller.store.path
    destination = tmp_path / "backup.sqlite"
    manifest = backup(database, destination)
    assert not manifest["credentials_included"] and not manifest["authorization_key_included"]
    restored = tmp_path / "restored.sqlite"
    restore(destination, restored)
    c = SandboxController(restored, controller.broker, controller.authority, symbols=["SPY"])
    try:
        assert c.account.view() == controller.account.view()
        assert not c.state["connected"] and not c.state["reconciled"]
    finally:
        c.close()
    with destination.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        restore(destination, tmp_path / "bad.sqlite")
