"""Official Alpaca v2 PAPER endpoints only; no live host or fallback transport."""

import os
import re
from typing import Protocol

import httpx

from quantlab.execution.authority import ExecutionDenied


class BrokerUnavailable(RuntimeError):
    pass


class BrokerRejected(ValueError):
    pass


class BrokerUncertain(BrokerUnavailable):
    pass


class Broker(Protocol):
    kind: str

    def account(self): ...
    def positions(self): ...
    def open_orders(self): ...
    def by_client_id(self, client_id): ...
    def activities(self, since): ...
    def submit(self, payload, permit, *, now): ...
    def cancel(self, order_id, permit, *, now): ...
    def replace(self, order_id, payload, permit, *, now): ...


class AlpacaPaperBroker:
    kind = "alpaca_paper"
    base = "https://paper-api.alpaca.markets"

    def __init__(self, authority, *, client=None, credentials=None):
        self.authority = authority
        key, secret = credentials or (
            os.getenv("QUANTLAB_ALPACA_PAPER_KEY"),
            os.getenv("QUANTLAB_ALPACA_PAPER_SECRET"),
        )
        if not key or not secret:
            raise BrokerUnavailable("Separate Alpaca PAPER credentials unavailable")
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)
        if getattr(self.client, "follow_redirects", False):
            raise ValueError("Broker redirects are prohibited")
        self._real_transport = client is None
        self.external_verified = False

    def _request(self, method, path, *, payload=None, params=None, uncertain=False):
        try:
            r = self.client.request(
                method, self.base + path, headers=self._headers, json=payload, params=params
            )
        except httpx.TransportError as exc:
            error = BrokerUncertain if uncertain else BrokerUnavailable
            raise error("Alpaca paper transport failure: " + type(exc).__name__) from None
        if r.status_code == 404:
            return None
        if r.status_code >= 500 or r.status_code in (408, 429):
            error = BrokerUncertain if uncertain else BrokerUnavailable
            raise error(f"Alpaca paper HTTP {r.status_code}; no automatic order retry")
        if r.status_code not in (200, 201, 204):
            raise BrokerRejected(f"Alpaca paper HTTP {r.status_code}")
        return None if r.status_code == 204 else r.json()

    def account(self):
        account = self._request("GET", "/v2/account")
        if not account or account["id"] != self.authority.account_id:
            raise ExecutionDenied("Unexpected sandbox account identity")
        self.external_verified = self._real_transport
        return account

    def positions(self):
        rows = self._request("GET", "/v2/positions")
        if not isinstance(rows, list):
            raise BrokerUnavailable("Positions response coverage unavailable")
        return rows

    def open_orders(self):
        rows = self._request(
            "GET", "/v2/orders", params={"status": "open", "limit": 500, "nested": "true"}
        )
        if not isinstance(rows, list):
            raise BrokerUnavailable("Open orders unavailable")
        if len(rows) >= 500:
            raise BrokerUnavailable("Open-order coverage cap reached; reconciliation incomplete")
        return rows

    def by_client_id(self, client_id):
        return self._request(
            "GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_id}
        )

    def activities(self, since):
        params = {"after": since, "direction": "asc", "page_size": 100}
        result = []
        for _ in range(100):
            rows = self._request("GET", "/v2/account/activities", params=params)
            if not isinstance(rows, list):
                raise BrokerUnavailable("Activity coverage unavailable")
            result.extend(rows)
            if len(rows) < 100:
                return result
            token = rows[-1]["id"]
            if token == params.get("page_token"):
                raise BrokerUnavailable("Activity cursor did not advance")
            params["page_token"] = token
        raise BrokerUnavailable("Activity pagination budget exhausted; coverage incomplete")

    def submit(self, payload, permit, *, now):
        self.authority.require(permit, "submit", payload, now=now)
        if payload.get("order_class", "simple") != "simple":
            raise BrokerRejected("Only reviewed simple orders supported")
        return self._request("POST", "/v2/orders", payload=payload, uncertain=True)

    def cancel(self, order_id, permit, *, now):
        self._validate_id(order_id)
        body = {"order_id": order_id}
        self.authority.require(permit, "cancel", body, now=now)
        self._request("DELETE", "/v2/orders/" + order_id, uncertain=True)
        return {"cancel_requested": True, "confirmed": False}

    def replace(self, order_id, payload, permit, *, now):
        self._validate_id(order_id)
        body = {"order_id": order_id, "replacement": payload}
        self.authority.require(permit, "replace", body, now=now)
        return self._request("PATCH", "/v2/orders/" + order_id, payload=payload, uncertain=True)

    @staticmethod
    def _validate_id(order_id):
        if not isinstance(order_id, str) or not re.fullmatch("[A-Za-z0-9-]{1,100}", order_id):
            raise BrokerRejected("Invalid broker order identifier")

    def close(self):
        self.client.close()
