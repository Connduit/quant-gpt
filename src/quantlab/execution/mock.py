"""Explicit deterministic test broker, never an external broker verification."""

import json
from copy import deepcopy
from pathlib import Path

from quantlab.backtesting.models import decimal
from quantlab.backtesting.report import dumps
from quantlab.execution.broker import BrokerRejected, BrokerUnavailable, BrokerUncertain
from quantlab.paper.account import Account


class MockBroker:
    kind = "mock"
    external_verified = False

    def __init__(self, authority, path=None, *, capital=100000):
        self.authority = authority
        self.path = Path(path) if path else None
        self.connected = True
        self.timeout_after_accept = False
        self.malformed_ack = False
        self.cash_discrepancy = decimal(0)
        self.submit_calls = 0
        self.duplicate_callbacks = False
        self.orders = {}
        self.records = []
        self.accounting = Account(capital, {})
        if self.path and self.path.exists():
            state = json.loads(self.path.read_text())
            self.orders = state["orders"]
            self.records = state["records"]
            self.accounting = Account(state["capital"], {})
            for fill in state["fills"]:
                self.accounting.fill(
                    fill["instrument"],
                    fill["quantity"],
                    fill["price"],
                    fill["fee"],
                    fill["at"],
                    fill["client_id"],
                    fill["strategy"],
                )
            self.accounting.prices = {k: decimal(v) for k, v in state["prices"].items()}

    def _require(self):
        if not self.connected:
            raise BrokerUnavailable("Simulated broker connection failure")

    def _save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            value = {
                "capital": str(self.accounting.stocks.initial_cash),
                "orders": self.orders,
                "records": self.records,
                "fills": self.accounting.fills,
                "prices": {k: str(v) for k, v in self.accounting.prices.items()},
            }
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(dumps(value))
            temporary.replace(self.path)

    def account(self):
        self._require()
        v = self.accounting.view()
        return {
            "id": self.authority.account_id,
            "currency": "USD",
            "status": "ACTIVE",
            "trading_blocked": False,
            "cash": str(v["cash"] + self.cash_discrepancy),
            "equity": str(v["equity"] + self.cash_discrepancy),
            "buying_power": str(v["buying_power"]),
        }

    def positions(self):
        self._require()
        return [
            {"symbol": s, "qty": str(q)}
            for s, q in self.accounting.view()["positions"].items()
            if q
        ]

    def open_orders(self):
        self._require()
        return [
            deepcopy(o)
            for o in self.orders.values()
            if o["status"] not in ("filled", "canceled", "expired", "rejected")
        ]

    def by_client_id(self, client_id):
        self._require()
        return deepcopy(self.orders.get(client_id))

    def activities(self, since):
        self._require()
        return deepcopy(self.records * (2 if self.duplicate_callbacks else 1))

    def submit(self, payload, permit, *, now):
        self._require()
        self.authority.require(permit, "submit", payload, now=now)
        self.submit_calls += 1
        client = payload["client_order_id"]
        if client in self.orders:
            raise BrokerRejected("Duplicate client ID; no retry needed")
        order = {
            **payload,
            "id": "mock-" + client,
            "status": "new",
            "filled_qty": "0",
            "created_at": str(now),
        }
        self.orders[client] = order
        self._save()
        if self.timeout_after_accept:
            self.timeout_after_accept = False
            raise BrokerUncertain("Simulated response lost after acceptance")
        if self.malformed_ack:
            return {"client_order_id": client}
        return deepcopy(order)

    def mark(self, symbol, price):
        self.accounting.prices[symbol] = decimal(price)
        self._save()

    def publish_fill(self, client_id, quantity, price, *, now, fee_per_unit=".005"):
        self._require()
        o = self.orders[client_id]
        q = decimal(quantity)
        if (
            q <= 0
            or q != q.to_integral_value()
            or q + decimal(o["filled_qty"]) > decimal(o["qty"])
            or o["status"] in ("canceled", "expired", "rejected", "filled")
        ):
            raise BrokerRejected("Invalid explicit mock fill")
        signed = int(q) * (1 if o["side"] == "buy" else -1)
        fee = decimal(fee_per_unit) * q
        self.accounting.fill(o["symbol"], signed, price, fee, now, client_id, "mock-broker")
        o["filled_qty"] = str(decimal(o["filled_qty"]) + q)
        o["status"] = (
            "filled" if decimal(o["filled_qty"]) == decimal(o["qty"]) else "partially_filled"
        )
        self.records.append(
            {
                "id": "mock-fill-" + str(len(self.records) + 1),
                "activity_type": "FILL",
                "order_id": o["id"],
                "symbol": o["symbol"],
                "side": o["side"],
                "qty": str(q),
                "price": str(price),
                "fee": str(fee),
                "transaction_time": now.isoformat(),
            }
        )
        self._save()

    def cancel(self, order_id, permit, *, now):
        self._require()
        self.authority.require(permit, "cancel", {"order_id": order_id}, now=now)
        order = next((o for o in self.orders.values() if o["id"] == order_id), None)
        if order is None:
            raise BrokerRejected("Unknown mock order")
        if order["status"] != "filled":
            order["status"] = "canceled"
        self._save()
        return {"cancel_requested": True, "confirmed": False}

    def replace(self, order_id, payload, permit, *, now):
        self._require()
        self.authority.require(
            permit, "replace", {"order_id": order_id, "replacement": payload}, now=now
        )
        raise BrokerRejected(
            "Mock/controller uses confirmed cancel then new intent; no priority preservation"
        )

    def close(self):
        self._save()
