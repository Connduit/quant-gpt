"""Durable sandbox OMS: risk before submission, uncertain responses never retried."""

import json
import math
import re
import uuid
from copy import deepcopy
from datetime import timedelta

import exchange_calendars as xcals

from quantlab.backtesting.models import decimal
from quantlab.backtesting.report import dumps
from quantlab.discovery.common import code_version, fingerprint
from quantlab.execution.authority import ExecutionDenied
from quantlab.execution.broker import BrokerRejected, BrokerUnavailable, BrokerUncertain
from quantlab.paper.account import Account
from quantlab.paper.events import instant
from quantlab.paper.orders import TERMINAL, PaperOrder
from quantlab.paper.risk import PaperLimits, check
from quantlab.paper.store import PaperStore


class RiskContext:
    time = staticmethod(instant)
    contracts = {}

    def __init__(self, controller):
        self.controller = controller
        self.account = controller.account
        self.orders = controller.orders
        self.state = controller.state
        self.limits = controller.limits
        self.instruments = controller.symbols
        self.calendar = controller.calendar

    def in_session(self, symbol, t):
        return self.calendar.is_open_on_minute(t.replace(second=0, microsecond=0))

    def fee(self, symbol):
        return self.controller.assumed_fee

    def multiplier(self, symbol):
        return decimal(1)

    def strategy_view(self, strategy):
        quantities = {}
        cashflow = decimal(0)
        for fill in self.account.fills:
            if fill["strategy"] != strategy:
                continue
            quantities[fill["instrument"]] = (
                quantities.get(fill["instrument"], 0) + fill["quantity"]
            )
            cashflow -= decimal(fill["quantity"]) * decimal(fill["price"]) + decimal(fill["fee"])
        values = [decimal(q) * self.account.prices[s] for s, q in quantities.items() if q]
        return cashflow + sum(values, decimal(0)), sum(map(abs, values), decimal(0))


class SandboxController:
    def __init__(
        self,
        path,
        broker,
        authority,
        *,
        symbols,
        limits=None,
        assumed_fee=".005",
        approval=None,
        strategy_definitions=None,
    ):
        self.broker = broker
        self.authority = authority
        self.symbols = set(symbols)
        if not self.symbols or any(
            not isinstance(s, str) or not s.isascii() or not s.replace(".", "").isalnum()
            for s in self.symbols
        ):
            raise ValueError("Explicit supported equity symbols required")
        if any(re.fullmatch(r"(ES|MES|NQ|MNQ)[HMUZ][0-9]{1,4}", symbol) for symbol in self.symbols):
            raise ExecutionDenied(
                "Futures brokerage adapter unavailable; never route contracts to an equity broker"
            )
        self.limits = limits or PaperLimits(
            gross=0.9, net=0.9, leverage=1, position=0.35, correlated=0.7, strategy=0.6
        )
        self.definitions = strategy_definitions or {
            "test": {"type": "test_control", "version": "test-only-v1"}
        }
        self.assumed_fee = decimal(assumed_fee)
        if self.assumed_fee < 0:
            raise ValueError("Nonnegative explicit fee assumption required")
        self.calendar = xcals.get_calendar("XNYS", start="2000-01-01", end="2035-12-31")
        self.configuration = {
            "account_id": authority.account_id,
            "mode": authority.mode,
            "symbols": sorted(self.symbols),
            "strategy_definitions": self.definitions,
            "risk": self.limits.__dict__,
            "assumed_fee": str(self.assumed_fee),
            "source_sha256": code_version()["source_sha256"],
        }
        self.store = PaperStore(path)
        self.state = self.store.load()
        self.account = None
        self.orders = {}
        if self.state is None:
            self.state = {
                "configuration": self.configuration,
                "initialized": False,
                "capital": None,
                "fills": [],
                "prices": {},
                "orders": {},
                "broker_ids": {},
                "uncertain": [],
                "seen_activities": [],
                "connected": False,
                "awaiting_fresh": True,
                "reconciled": False,
                "killed": False,
                "strategies": {},
                "last_events": {},
                "clock": None,
                "baseline_at": None,
                "last_reconciled": None,
                "peak": "0",
                "day_start": "0",
                "day": None,
                "approval": approval,
                "alerts": [],
                "model_monitor": [],
                "broker_buying_power": "0",
                "fee_coverage": (
                    "Broker-reported activity fees where present; absent fee fields are explicitly "
                    "unverified; cash reconciliation required"
                ),
            }
            self._save("initialize", "initialize", {})
        else:
            if fingerprint(self.configuration) != fingerprint(self.state["configuration"]):
                self.store.close()
                raise ExecutionDenied(
                    "Execution configuration/code changed; operator review/migration required"
                )
            self._restore()
            self._commit(
                "restart", {}, lambda: self._suspend("restart_requires_broker_reconciliation")
            )

    def _restore(self):
        self.account = None
        self.orders = {k: PaperOrder(**v) for k, v in self.state["orders"].items()}
        if self.state["initialized"]:
            self.account = Account(self.state["capital"], {})
            for f in self.state["fills"]:
                self.account.fill(
                    f["instrument"],
                    f["quantity"],
                    f["price"],
                    f["fee"],
                    f["at"],
                    f["client_id"],
                    f["strategy"],
                )
            self.account.prices = {k: decimal(v) for k, v in self.state["prices"].items()}
            self.account.view()

    def _save(self, identity, kind, payload):
        self.state["orders"] = {k: o.payload() for k, o in self.orders.items()}
        if self.account:
            self.state["fills"] = deepcopy(self.account.fills)
            self.state["prices"] = {k: str(v) for k, v in self.account.prices.items()}
        self.state = json.loads(dumps(self.state))
        self.store.commit(identity, kind, payload, self.state)

    def _commit(self, kind, payload, operation, *, identity=None):
        identity = identity or kind + ":" + uuid.uuid4().hex
        if self.store.contains(identity):
            return False
        previous = deepcopy(self.state)
        try:
            operation()
            self._save(identity, kind, payload)
        except BaseException:
            self.state = previous
            self._restore()
            raise
        return True

    def _alert(self, code, detail):
        self.state["alerts"].append(
            {"at": self.state["clock"], "code": code, "detail": str(detail)}
        )

    def _suspend(self, reason):
        self.state["connected"] = False
        self.state["reconciled"] = False
        self.state["awaiting_fresh"] = True
        for strategy in self.state["strategies"].values():
            strategy["execution"] = "PAUSED"
        self._alert("execution_suspended", reason)

    def bootstrap(self, *, now):
        now = instant(now)
        if self.state["initialized"]:
            raise ExecutionDenied("Existing account must be reconciled, never re-funded")
        account = self.broker.account()
        positions = self.broker.positions()
        orders = self.broker.open_orders()
        if (
            account["id"] != self.authority.account_id
            or account.get("currency") != "USD"
            or account.get("status") != "ACTIVE"
            or account.get("trading_blocked")
        ):
            raise ExecutionDenied(
                "Sandbox account status/currency/identity does not permit operation"
            )
        if positions or orders or decimal(account["cash"]) <= 0:
            raise ExecutionDenied(
                "Clean positive-cash sandbox account required for explicit initial baseline"
            )

        def op():
            self.state.update(
                initialized=True,
                capital=str(decimal(account["cash"])),
                baseline_at=now.isoformat(),
                peak=str(decimal(account["cash"])),
                day_start=str(decimal(account["cash"])),
                clock=now.isoformat(),
            )
            self.account = Account(account["cash"], {})
            self._alert(
                "sandbox_bootstrap",
                "Actual sandbox baseline, never a live account or strategy promotion",
            )

        self._commit("bootstrap", {"account_id": account["id"]}, op)

    def approve(self, signed, *, now):
        if not self.account:
            raise ExecutionDenied("Bootstrap required before strategy approval")
        body = self.authority.verify(signed, now=now)
        if (
            body.get("kind") != "SANDBOX_TEST"
            or body.get("risk_hash") != fingerprint(self.limits.__dict__)
            or body.get("source_sha256") != self.configuration["source_sha256"]
        ):
            raise ExecutionDenied("Approval not bound to current sandbox strategy/code/risk policy")
        definition = self.definitions.get(body.get("strategy_id"))
        if (
            definition is None
            or body.get("strategy_definition_hash") != fingerprint(definition)
            or body.get("strategy_version") != definition.get("version")
        ):
            raise ExecutionDenied("Approval is not bound to the exact reviewed strategy definition")
        if (
            set(body.get("symbols", ())) != self.symbols
            or not body.get("actor")
            or not body.get("reason")
        ):
            raise ExecutionDenied("Explicit scoped sandbox approval required")
        if body.get("origin") == "simulated_fixture" and self.broker.kind != "mock":
            raise ExecutionDenied("Simulated fixture approval cannot authorize an external broker")
        if body.get("origin") not in ("human", "simulated_fixture"):
            raise ExecutionDenied("Unrecognized approval origin")

        def op():
            self.state["approval"] = signed
            self.state["strategies"][body["strategy_id"]] = {
                "execution": "PAUSED",
                "deployment": "SANDBOX_TEST",
                "validation_status": "TEST_ONLY_NOT_VALIDATED",
                "capital": self.state["capital"],
                "peak": self.state["capital"],
                "version": body["strategy_version"],
                "model_hash": body.get("model_hash"),
            }

        self._commit(
            "sandbox_approval", {"actor": body["actor"], "strategy": body["strategy_id"]}, op
        )

    def _approval(self, strategy, now):
        signed = self.state.get("approval")
        if not signed:
            raise ExecutionDenied("No explicit sandbox strategy approval")
        body = self.authority.verify(signed, now=now)
        if (
            body.get("strategy_id") != strategy
            or body.get("source_sha256") != self.configuration["source_sha256"]
            or body.get("risk_hash") != fingerprint(self.limits.__dict__)
        ):
            raise ExecutionDenied("Approval strategy/code/risk binding invalid")
        if set(body.get("symbols", ())) != self.symbols:
            raise ExecutionDenied("Approval symbol binding invalid")
        deployed = self.state["strategies"].get(strategy)
        if (
            not deployed
            or deployed["version"] != body.get("strategy_version")
            or deployed["model_hash"] != body.get("model_hash")
        ):
            raise ExecutionDenied("Deployment strategy/model version differs from signed approval")
        return body

    def arm(self, strategy, *, now, reason):
        now = instant(now)
        self._approval(strategy, now)
        if (
            not reason
            or self.state["killed"]
            or not self.state["reconciled"]
            or not self.state["connected"]
        ):
            raise ExecutionDenied("Reviewed reconciliation and kill reset required before arming")
        if (now - instant(self.state["last_reconciled"])).total_seconds() > 30:
            raise ExecutionDenied("Broker reconciliation is stale")
        if not self.state["last_events"] or self.state.get("awaiting_fresh", True):
            raise ExecutionDenied("Fresh market observations required")
        for event in self.state["last_events"].values():
            if (now - instant(event["event_at"])).total_seconds() > self.limits.stale_seconds:
                raise ExecutionDenied("Stale market observations")

        def op():
            self.state["strategies"][strategy]["execution"] = "RUNNING"
            self._alert("sandbox_armed", reason)

        self._commit("arm", {"strategy": strategy, "reason": reason}, op)

    def receive(self, event, *, now):
        now = instant(now)
        if self.state["clock"] and now < instant(self.state["clock"]):
            raise ValueError("Execution clock cannot move backwards")
        if not self.account:
            raise ExecutionDenied("Bootstrap first")
        if event.instrument not in self.symbols or event.kind != "quote":
            raise ValueError("Allowed equity quote required")
        if event.mode == "replay" and self.broker.kind != "mock":
            raise ExecutionDenied("Replay cannot authorize external broker orders")
        if (
            event.received_at > now
            or event.event_at > now
            or (now - event.event_at).total_seconds() > self.limits.stale_seconds
        ):
            self._commit("stale_quote", {}, lambda: self._suspend("stale_or_future_quote"))
            return False
        old = self.state["last_events"].get(event.instrument)
        if old and event.event_at < instant(old["event_at"]):
            self._commit("out_of_order_quote", {}, lambda: self._suspend("out_of_order_quote"))
            return False

        def op():
            self.state["clock"] = now.isoformat()
            self.state["last_events"][event.instrument] = event.payload()
            self.state["awaiting_fresh"] = False
            previous = self.account.view()["equity"]
            if self.state["day"] != str(event.event_at.date()):
                self.state["day"] = str(event.event_at.date())
                self.state["day_start"] = str(previous)
            self.account.prices[event.instrument] = (decimal(event.bid) + decimal(event.ask)) / 2
            value = self.account.view()["equity"]
            self.state["peak"] = str(max(decimal(self.state["peak"]), value))
            for sid, s in self.state["strategies"].items():
                pnl, _ = RiskContext(self).strategy_view(sid)
                s["peak"] = str(max(decimal(s["peak"]), decimal(s["capital"]) + pnl))
            if value < decimal(self.state["day_start"]) * (
                1 - decimal(self.limits.daily_loss)
            ) or value < decimal(self.state["peak"]) * (1 - decimal(self.limits.drawdown)):
                self.state["killed"] = True
                self._suspend("portfolio_loss_limit; no automatic liquidation")

        return self._commit("quote", event.payload(), op, identity="quote:" + event.identity)

    def submit(self, order, *, now):
        now = instant(now)
        if not self.account:
            raise ExecutionDenied("Broker baseline unavailable")
        existing = self.orders.get(order.client_id)
        if existing:
            fields = (
                "strategy",
                "instrument",
                "quantity",
                "submitted_at",
                "order_type",
                "limit",
                "stop",
                "tif",
            )
            if any(getattr(existing, k) != getattr(order, k) for k in fields):
                raise ExecutionDenied("Stable client ID collision")
            return existing
        self._approval(order.strategy, now)
        if order.state != "CREATED" or order.filled or instant(order.submitted_at) != now:
            raise ValueError("New intent with the exact decision timestamp required")
        reasons = []
        for value in (order.limit, order.stop):
            if value is not None and decimal(value) % decimal(".01"):
                reasons.append("invalid_order_tick")
        if (
            not self.state["reconciled"]
            or not self.state["last_reconciled"]
            or (now - instant(self.state["last_reconciled"])).total_seconds() > 30
        ):
            reasons.append("broker_state_uncertain_or_stale")
        if self.state["uncertain"] or any(o.state == "PENDING" for o in self.orders.values()):
            reasons.append("uncertain_prior_order")
        if len([o for o in self.orders.values() if o.state not in TERMINAL]) >= 100:
            reasons.append("open_order_cap")
        if (
            len(
                [
                    o
                    for o in self.orders.values()
                    if now - instant(o.submitted_at) < timedelta(minutes=1)
                ]
            )
            >= self.limits.max_orders_per_minute
        ):
            reasons.append("order_rate")
        for symbol in self.account.view()["positions"]:
            event = self.state["last_events"].get(symbol)
            if (
                not event
                or (now - instant(event["event_at"])).total_seconds() > self.limits.stale_seconds
            ):
                reasons.append("stale_portfolio_valuation")
        price = self.account.prices.get(order.instrument)
        if price is None:
            reasons.append("missing_price")
        else:
            event = self.state["last_events"][order.instrument]
            worst = decimal(event["ask"] if order.quantity > 0 else event["bid"])
            reasons += check(RiskContext(self), order, worst, now)
            if order.quantity > 0 and decimal(order.quantity) * worst + self.assumed_fee * abs(
                order.quantity
            ) > decimal(self.state["broker_buying_power"]):
                reasons.append("broker_buying_power")

        def accepted():
            self.orders[order.client_id] = order
            order.transition("PENDING")
            if reasons:
                order.transition("REJECTED", ",".join(sorted(set(reasons))))

        self._commit(
            "order_intent", order.payload(), accepted, identity="intent:" + order.client_id
        )
        if reasons:
            return order
        # One stable broker ID; send exactly once after the durable intent commit.
        client = "ql-" + fingerprint([self.authority.account_id, order.client_id])[:32]
        payload = {
            "symbol": order.instrument,
            "qty": str(abs(order.quantity)),
            "side": "buy" if order.quantity > 0 else "sell",
            "type": order.order_type,
            "time_in_force": order.tif,
            "client_order_id": client,
            "order_class": "simple",
        }
        if order.limit is not None:
            payload["limit_price"] = order.limit
        if order.stop is not None:
            payload["stop_price"] = order.stop
        try:
            response = self.broker.submit(
                payload, self.authority.permit("submit", payload, now=now), now=now
            )
            if not response or not response.get("id") or response.get("client_order_id") != client:
                raise BrokerUncertain("Missing/mismatched broker acknowledgement")
        except BrokerRejected as exc:
            rejection_reason = str(exc)

            def reject():
                self.orders[order.client_id].transition("REJECTED", rejection_reason)
                self._suspend("broker_rejected:" + rejection_reason)

            self._commit("broker_rejected", {"id": order.client_id, "reason": str(exc)}, reject)
            return self.orders[order.client_id]
        except (BrokerUnavailable, ValueError, KeyError, TypeError) as exc:
            failure_type = type(exc).__name__

            def uncertain():
                self.state["uncertain"].append(order.client_id)
                self._suspend("uncertain_submission:" + failure_type)

            self._commit("submission_uncertain", {"id": order.client_id}, uncertain)
            return self.orders[order.client_id]

        def acknowledgement():
            self.state["broker_ids"][order.client_id] = response["id"]
            order.transition("ACCEPTED")

        self._commit("broker_ack", {"client": client, "broker_id": response["id"]}, acknowledgement)
        return self.orders[order.client_id]

    def reconcile(self, *, now):
        now = instant(now)
        if not self.account:
            raise ExecutionDenied("Explicit bootstrap required")
        try:
            broker_account = self.broker.account()
            positions = self.broker.positions()
            open_orders = self.broker.open_orders()
            responses = {}
            for identity, o in self.orders.items():
                if o.state not in TERMINAL or identity in self.state["uncertain"]:
                    responses[identity] = self.broker.by_client_id(
                        "ql-" + fingerprint([self.authority.account_id, identity])[:32]
                    )
            activities = self.broker.activities(self.state["baseline_at"])
        except (
            BrokerUnavailable,
            BrokerRejected,
            ExecutionDenied,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            failure_type = type(exc).__name__
            self._commit(
                "reconcile_failure",
                {},
                lambda: self._suspend("broker_read_failure:" + failure_type),
            )
            return {"okay": False, "errors": ["broker_read_failure"]}
        errors = []

        def apply():
            self.state["clock"] = now.isoformat()
            for identity, response in responses.items():
                if response is None:
                    if self.orders[identity].state not in TERMINAL:
                        errors.append("order_status_uncertain:" + identity)
                    continue
                o = self.orders[identity]
                expected = "ql-" + fingerprint([self.authority.account_id, identity])[:32]
                if (
                    response.get("client_order_id") != expected
                    or response.get("symbol") != o.instrument
                    or decimal(response["qty"]) != abs(o.quantity)
                    or response.get("side") != ("buy" if o.quantity > 0 else "sell")
                    or response.get("type") != o.order_type
                ):
                    errors.append("broker_order_intent_mismatch:" + identity)
                    continue
                self.state["broker_ids"][identity] = response["id"]
                if identity in self.state["uncertain"]:
                    self.state["uncertain"].remove(identity)
                if o.state == "PENDING":
                    o.transition("ACCEPTED")
            known = {v: k for k, v in self.state["broker_ids"].items()}
            for activity in sorted(
                activities, key=lambda a: (a.get("transaction_time", ""), a["id"])
            ):
                if activity["id"] in self.state["seen_activities"]:
                    continue
                if activity.get("activity_type") != "FILL":
                    errors.append("unreviewed_nonfill_activity:" + activity["id"])
                    continue
                identity = known.get(activity.get("order_id"))
                if identity is None:
                    errors.append("unexpected_fill:" + activity["id"])
                    continue
                o = self.orders[identity]
                if activity.get("symbol") != o.instrument:
                    errors.append("fill_symbol_mismatch:" + activity["id"])
                    continue
                if self.account.fills and instant(activity["transaction_time"]) < instant(
                    self.account.fills[-1]["at"]
                ):
                    errors.append("late_fill_requires_reviewed_rebuild:" + activity["id"])
                    continue
                q = decimal(activity["qty"])
                price = decimal(activity["price"])
                fee = decimal(activity.get("fee", "0"))
                if (
                    q <= 0
                    or q != q.to_integral_value()
                    or price <= 0
                    or fee < 0
                    or q > abs(o.remaining)
                    or o.state not in ("ACCEPTED", "PARTIALLY_FILLED")
                ):
                    errors.append("invalid_or_excess_fill:" + activity["id"])
                    continue
                signed = int(q) * (1 if activity["side"] == "buy" else -1)
                if signed * o.quantity <= 0 or instant(activity["transaction_time"]) > now:
                    errors.append("fill_side_or_time_mismatch:" + activity["id"])
                    continue
                self.account.fill(
                    o.instrument,
                    signed,
                    price,
                    fee,
                    activity["transaction_time"],
                    identity,
                    o.strategy,
                )
                o.filled += int(q)
                o.transition("FILLED" if o.remaining == 0 else "PARTIALLY_FILLED")
                self.state["seen_activities"].append(activity["id"])
            for identity, response in responses.items():
                if response is None:
                    continue
                o = self.orders[identity]
                if decimal(response.get("filled_qty", "0")) != o.filled:
                    errors.append("fill_coverage_mismatch:" + identity)
                state = response.get("status")
                target = {
                    "canceled": "CANCELLED",
                    "expired": "EXPIRED",
                    "rejected": "REJECTED",
                }.get(state)
                if target and o.state not in TERMINAL:
                    o.transition(target, "broker_status")
                if state == "filled" and o.state != "FILLED":
                    errors.append("missing_execution_reports:" + identity)
            if any(
                o["id"] not in known or self.orders[known[o["id"]]].state in TERMINAL
                for o in open_orders
            ):
                errors.append("unexpected_or_inconsistent_open_order")
            actual = {p["symbol"]: decimal(p["qty"]) for p in positions if decimal(p["qty"])}
            expected = {k: decimal(v) for k, v in self.account.view()["positions"].items()}
            if actual != expected:
                errors.append("positions_mismatch")
            value = self.account.view()
            if abs(decimal(broker_account["cash"]) - value["cash"]) > decimal(".01"):
                errors.append("cash_mismatch")
            if abs(decimal(broker_account["equity"]) - value["equity"]) > max(
                decimal(5), decimal(self.state["capital"]) * decimal(".0001")
            ):
                errors.append("equity_mark_mismatch")
            if broker_account.get("trading_blocked") or broker_account.get("status") != "ACTIVE":
                errors.append("broker_account_not_ready")
            self.state["broker_buying_power"] = str(decimal(broker_account["buying_power"]))
            if errors or self.state["uncertain"]:
                self._suspend(",".join(errors) or "uncertain_prior_order")
            else:
                self.state["connected"] = True
                self.state["reconciled"] = True
                self.state["last_reconciled"] = now.isoformat()
                self._alert(
                    "broker_reconciled",
                    (
                        "Account cash, positions, open orders and reported executions agree; "
                        "strategy remains separately gated"
                    ),
                )

        try:
            self._commit("reconcile", {"activity_count": len(activities)}, apply)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            failure_type = type(exc).__name__
            self._commit(
                "reconcile_invalid",
                {},
                lambda: self._suspend("invalid_broker_state:" + failure_type),
            )
            return {"okay": False, "errors": ["invalid_broker_state"]}
        return {"okay": not errors and self.state["reconciled"], "errors": errors}

    def cancel(self, identity, *, now):
        o = self.orders[identity]
        if o.state in TERMINAL:
            return {"already_terminal": True}
        broker_id = self.state["broker_ids"].get(identity)
        if broker_id is None:
            self._commit(
                "cancel_uncertain",
                {},
                lambda: self._suspend("Cannot assume an unacknowledged order was rejected"),
            )
            return {"confirmed": False}
        payload = {"order_id": broker_id}
        try:
            self.broker.cancel(
                broker_id, self.authority.permit("cancel", payload, now=now), now=now
            )
        except (BrokerUnavailable, BrokerRejected) as exc:
            failure_type = type(exc).__name__
            self._commit(
                "cancel_failure",
                {},
                lambda: self._suspend("cancel_status_uncertain:" + failure_type),
            )
            return {"confirmed": False}
        self._commit("cancel_requested", {"id": identity}, lambda: None)
        return {"confirmed": False, "cancel_requested": True}

    def replace(self, identity, replacement, *, now):
        self.cancel(identity, now=now)
        result = self.reconcile(now=now)
        if not result["okay"] or self.orders[identity].state != "CANCELLED":
            raise ExecutionDenied("Replacement waits for confirmed cancellation and reconciliation")
        return self.submit(replacement, now=now)

    def kill(self, *, now, reason, cancel_open=False):
        if not reason:
            raise ValueError("Operator kill reason required")

        def op():
            self.state["killed"] = True
            self._suspend("global_kill:" + reason)

        self._commit("kill", {"reason": reason, "cancel_open": cancel_open}, op)
        if cancel_open:
            for identity, o in list(self.orders.items()):
                if o.state not in TERMINAL:
                    self.cancel(identity, now=now)
        return {
            "new_orders_stopped": True,
            "cancellation_requested": cancel_open,
            "positions_liquidated": False,
        }

    def reset_kill(self, authorization, *, now, reason):
        body = self.authority.verify(authorization, now=now)
        if body.get("operation") != "kill_reset" or not body.get("actor") or not reason:
            raise ExecutionDenied("Separate operator kill-reset authorization required")
        if not self.state["reconciled"] or self.state["uncertain"]:
            raise ExecutionDenied("Reconcile broker state before kill reset")

        def op():
            self.state["killed"] = False
            self._alert("kill_reset", reason + "; strategies remain paused")

        self._commit("kill_reset", {"actor": body["actor"], "reason": reason}, op)

    def pause_strategy(self, strategy, *, reason):
        if not reason:
            raise ValueError("Operator pause reason required")

        def op():
            self.state["strategies"][strategy]["execution"] = "PAUSED"
            self._alert("strategy_paused", strategy + ":" + reason)

        self._commit("strategy_pause", {"strategy": strategy, "reason": reason}, op)

    def model_observation(self, strategy, features, prediction, latency_ms, *, model_hash, now):
        approval = self._approval(strategy, now)
        if model_hash != self.state["strategies"][strategy]["model_hash"] or not model_hash:
            raise ExecutionDenied("Inference model is not deployment-pinned")
        baseline = approval.get("model_baseline", {})
        if (
            set(features) != set(baseline)
            or not math.isfinite(prediction)
            or not math.isfinite(latency_ms)
            or latency_ms < 0
        ):
            raise ValueError("Approved feature schema and finite inference required")
        z = {}
        for key, value in features.items():
            mean, std = baseline[key]["mean"], baseline[key]["std"]
            if (
                not math.isfinite(value)
                or not math.isfinite(mean)
                or not math.isfinite(std)
                or std <= 0
            ):
                raise ValueError("Finite model drift baseline required")
            z[key] = (value - mean) / std

        def op():
            self.state["model_monitor"].append(
                {
                    "at": instant(now).isoformat(),
                    "strategy": strategy,
                    "model_hash": model_hash,
                    "prediction": prediction,
                    "latency_ms": latency_ms,
                    "feature_z": z,
                }
            )
            if any(abs(v) > 5 for v in z.values()):
                self.state["strategies"][strategy]["execution"] = "PAUSED"
                self._alert(
                    "feature_drift",
                    "Threshold diagnostic; model paused, never automatically replaced",
                )

        self._commit("model_monitor", {"strategy": strategy}, op)

    def rollback_model(self, strategy, new_hash, authorization, *, now):
        body = self.authority.verify(authorization, now=now)
        if (
            body.get("operation") != "model_rollback"
            or body.get("strategy_id") != strategy
            or body.get("model_hash") != new_hash
            or not body.get("actor")
            or not body.get("reason")
        ):
            raise ExecutionDenied(
                "Separately reviewed, exact model rollback authorization required"
            )

        def op():
            self.state["strategies"][strategy]["execution"] = "PAUSED"
            self.state["strategies"][strategy]["model_hash"] = new_hash
            self.state["approval"] = None
            self._alert(
                "model_rollback",
                (
                    "Model pin changed; new deployment approval required, no automatic "
                    "replacement/restart"
                ),
            )

        self._commit("model_rollback", {"strategy": strategy, "model_hash": new_hash}, op)

    def report(self):
        return {
            "execution_mode": self.authority.mode,
            "broker": self.broker.kind,
            "live_enabled": False,
            "account": json.loads(dumps(self.account.view())) if self.account else None,
            "orders": [o.payload() for o in self.orders.values()],
            "fills": self.state["fills"],
            "risk": self.limits.__dict__,
            "connected": self.state["connected"],
            "reconciled": self.state["reconciled"],
            "killed": self.state["killed"],
            "uncertain_orders": self.state["uncertain"],
            "strategies": self.state["strategies"],
            "alerts": self.state["alerts"],
            "fee_coverage": self.state["fee_coverage"],
            "model_monitor": self.state["model_monitor"],
            "eligibility": (
                "SANDBOX_TEST engineering approval is not validated-paper or LIVE eligibility"
            ),
            "external_broker_verified": bool(getattr(self.broker, "external_verified", False))
            and self.state["reconciled"],
        }

    def close(self):
        self.store.close()
