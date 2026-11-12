"""Atomic local simulation, causal event processing and explicit recovery controls."""

import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import exchange_calendars as xcals

from quantlab.backtesting.models import decimal
from quantlab.backtesting.report import dumps
from quantlab.discovery.common import fingerprint
from quantlab.futures.calendar import FuturesCalendar
from quantlab.paper.account import Account
from quantlab.paper.events import instant
from quantlab.paper.orders import TERMINAL, PaperOrder
from quantlab.paper.risk import PaperLimits, check
from quantlab.paper.store import PaperStore


class PaperRuntime:
    time = staticmethod(instant)

    def __init__(
        self,
        path,
        *,
        capital=100000,
        contracts=None,
        symbols=(),
        limits=None,
        mode="replay",
        latency_ms=100,
        participation=0.1,
        slippage_ticks=1,
        stock_fee="0.005",
        futures_fee="3.52",
    ):
        if mode not in ("replay", "realtime", "delayed"):
            raise ValueError("Only simulated execution with an explicit data mode is available")
        if (
            not 0 < participation <= 1
            or latency_ms < 0
            or type(slippage_ticks) is not int
            or slippage_ticks < 0
        ):
            raise ValueError("Invalid simulation settings")
        self.contracts = contracts or {}
        self.instruments = set(symbols) | set(self.contracts)
        if any(not isinstance(s, str) or not s for s in self.instruments):
            raise ValueError("Invalid instrument identifiers")
        self.limits = limits or PaperLimits()
        self.mode = mode
        self.latency = timedelta(milliseconds=latency_ms)
        self.participation = decimal(participation)
        self.slippage_ticks = slippage_ticks
        self.stock_fee = decimal(stock_fee)
        self.futures_fee = decimal(futures_fee)
        if min(self.stock_fee, self.futures_fee) < 0:
            raise ValueError("Nonnegative fees required")
        self.calendar = FuturesCalendar("rth")
        self._session_ends = {}
        self.equity_calendar = xcals.get_calendar("XNYS", start="2000-01-01", end="2035-12-31")
        self.configuration = {
            "capital": str(decimal(capital)),
            "contracts": {k: c.as_dict() for k, c in self.contracts.items()},
            "symbols": sorted(symbols),
            "limits": self.limits.__dict__,
            "mode": mode,
            "latency_ms": latency_ms,
            "participation": str(self.participation),
            "slippage_ticks": slippage_ticks,
            "stock_fee": str(self.stock_fee),
            "futures_fee": str(self.futures_fee),
        }
        self.configuration = json.loads(dumps(self.configuration))
        self.store = PaperStore(path)
        self.state = self.store.load()
        if self.state is None:
            self.state = {
                "configuration": self.configuration,
                "strategies": {},
                "orders": {},
                "fills": [],
                "prices": {},
                "last_events": {},
                "sequences": {},
                "clock": None,
                "connected": False,
                "awaiting_fresh": True,
                "killed": False,
                "peak": str(decimal(capital)),
                "day_start": str(decimal(capital)),
                "day": None,
                "alerts": [],
                "equity_history": [],
                "predictions": [],
                "decisions": {},
            }
            self._restore()
            self._save("initialize", "initialize", {})
        else:
            if fingerprint(self.state["configuration"]) != fingerprint(self.configuration):
                self.store.close()
                raise ValueError(
                    "Paper configuration differs from persisted account; explicit "
                    "migration required"
                )
            self._restore()
            # Restart never resumes order acceptance before a fresh observation and operator
            self.control("disconnect", reason="process_restart_reconciliation_required")

    def _restore(self):
        self.account = Account(self.configuration["capital"], self.contracts)
        for f in self.state["fills"]:
            self.account.fill(
                f["instrument"],
                f["quantity"],
                f["price"],
                f["fee"],
                instant(f["at"]),
                f["client_id"],
                f["strategy"],
            )
        self.account.prices = {k: decimal(v) for k, v in self.state["prices"].items()}
        self.account.view()
        self.orders = {k: PaperOrder(**v) for k, v in self.state["orders"].items()}

    def _save(self, identity, kind, payload):
        self.state["fills"] = deepcopy(self.account.fills)
        self.state["prices"] = {k: str(v) for k, v in self.account.prices.items()}
        self.state["orders"] = {k: o.payload() for k, o in self.orders.items()}
        self.store.commit(identity, kind, payload, self.state)

    def _transaction(self, identity, kind, payload, operation):
        if self.store.contains(identity):
            return False
        prior = deepcopy(self.state)
        try:
            operation()
            self._save(identity, kind, payload)
        except BaseException:
            self.state = prior
            self._restore()
            raise
        return True

    def alert(self, code, detail):
        self.state["alerts"].append(
            {"at": self.state["clock"], "code": code, "detail": str(detail)}
        )

    def register(
        self,
        strategy,
        *,
        capital,
        validation_status="REJECTED",
        approved=False,
        approval_reason=None,
        experimental=False,
        version="1",
        model_hash=None,
    ):
        if not strategy or strategy in self.state["strategies"] or decimal(capital) <= 0:
            raise ValueError("Unique strategy and positive allocation required")
        if sum(decimal(s["capital"]) for s in self.state["strategies"].values()) + decimal(
            capital
        ) > decimal(self.configuration["capital"]):
            raise ValueError("Strategy allocations exceed master capital")
        if experimental:
            if self.mode != "replay":
                raise ValueError(
                    "Unvalidated experimental strategies are restricted to historical replay"
                )
            deployment = "RESEARCH"
        elif validation_status == "VALIDATED" and approved is True and approval_reason:
            # Trusted operator API; caller must bind evidence, not an untrusted strategy input.
            deployment = "APPROVED_FOR_PAPER"
        else:
            raise ValueError("VALIDATED evidence and explicit operator approval required")

        def op():
            self.state["strategies"][strategy] = {
                "capital": str(decimal(capital)),
                "peak": str(decimal(capital)),
                "deployment": deployment,
                "execution": "PAUSED",
                "version": version,
                "model_hash": model_hash,
                "approval_reason": approval_reason,
                "validation_status": validation_status,
                "memory": {},
            }

        self._transaction(
            "register:" + strategy,
            "register",
            {"strategy": strategy, "experimental": experimental},
            op,
        )

    def control(self, action, *, strategy=None, reason=None):
        if (
            action not in ("connect", "disconnect", "kill", "pause", "resume", "stop", "reset_kill")
            or not reason
        ):
            raise ValueError("Supported control and reason required")

        def op():
            if action == "connect":
                if self.state.get("awaiting_fresh", True):
                    raise ValueError(
                        "New valid observation required before reconnect acknowledgement"
                    )
                self.state["connected"] = True
            elif action == "disconnect":
                self.state["connected"] = False
                self.state["awaiting_fresh"] = True
                for s in self.state["strategies"].values():
                    s["execution"] = "PAUSED"
            elif action == "kill":
                self.state["killed"] = True
                for o in self.orders.values():
                    if o.state not in TERMINAL:
                        o.transition("CANCELLED", "global_kill")
                for s in self.state["strategies"].values():
                    s["execution"] = "PAUSED"
            elif action == "reset_kill":
                self.state["killed"] = False
            else:
                if action == "stop" and strategy is None:
                    for item in self.state["strategies"].values():
                        item["execution"] = "STOPPED"
                    for o in self.orders.values():
                        if o.state not in TERMINAL:
                            o.transition("CANCELLED", "global_stop")
                    self.state["connected"] = False
                    return
                s = self.state["strategies"].get(strategy)
                if s is None:
                    raise ValueError("Unknown strategy")
                if action == "resume":
                    if (
                        self.state["killed"]
                        or not self.state["connected"]
                        or not self.state["last_events"]
                    ):
                        raise ValueError(
                            "Fresh data, connection and kill reset required before resume"
                        )
                    s["execution"] = "RUNNING"
                else:
                    s["execution"] = "STOPPED" if action == "stop" else "PAUSED"
                    for o in self.orders.values():
                        if o.strategy == strategy and o.state not in TERMINAL:
                            o.transition("CANCELLED", action)
                if s["deployment"] != "RESEARCH":
                    s["deployment"] = {
                        "RUNNING": "PAPER_RUNNING",
                        "PAUSED": "PAPER_PAUSED",
                        "STOPPED": "PAPER_STOPPED",
                    }[s["execution"]]
            self.alert("control_" + action, reason)

        self._transaction(
            "control:" + uuid.uuid4().hex,
            "control",
            {"action": action, "strategy": strategy, "reason": reason},
            op,
        )

    def in_session(self, symbol, t):
        if symbol in self.contracts:
            return self.calendar.session(t) is not None
        return self.equity_calendar.is_open_on_minute(t.replace(second=0, microsecond=0))

    def session_end(self, symbol, timestamp):
        session = self.session(symbol, timestamp)
        if session is None:
            return None
        key = (symbol in self.contracts, str(session))
        if key not in self._session_ends:
            if symbol in self.contracts:
                expected = self.calendar.expected(session)
                self._session_ends[key] = expected[-1] + timedelta(minutes=1)
            else:
                self._session_ends[key] = self.equity_calendar.session_close(
                    str(session)
                ).to_pydatetime()
        return self._session_ends[key]

    def multiplier(self, symbol):
        return self.contracts[symbol].spec.multiplier if symbol in self.contracts else decimal(1)

    def fee(self, symbol):
        return self.futures_fee if symbol in self.contracts else self.stock_fee

    def strategy_view(self, strategy):
        cashflow = decimal(0)
        quantities = {}
        for f in self.account.fills:
            if f["strategy"] != strategy:
                continue
            cashflow -= decimal(f["quantity"]) * decimal(f["price"]) * self.multiplier(
                f["instrument"]
            ) + decimal(f["fee"])
            quantities[f["instrument"]] = quantities.get(f["instrument"], 0) + f["quantity"]
        values = [
            decimal(q) * self.account.prices[s] * self.multiplier(s)
            for s, q in quantities.items()
            if q
        ]
        return cashflow + sum(values, decimal(0)), sum(map(abs, values), decimal(0))

    def submit(self, order, *, now=None):
        now = instant(now or datetime.now(UTC))
        if (
            self.state["clock"] is None
            or now < instant(self.state["clock"])
            or instant(order.submitted_at) != now
        ):
            raise ValueError(
                "Order clock must equal decision time and cannot precede the observed clock"
            )
        existing = self.orders.get(order.client_id)
        if existing:
            immutable = (
                "strategy",
                "instrument",
                "quantity",
                "submitted_at",
                "order_type",
                "limit",
                "stop",
                "tif",
            )
            if any(getattr(existing, k) != getattr(order, k) for k in immutable):
                raise ValueError("Client ID reused for different order intent")
            return existing
        if order.state != "CREATED" or order.filled or order.triggered_at is not None:
            raise ValueError("Only new order intents accepted")

        def op():
            self.orders[order.client_id] = order
            order.transition("PENDING")
            price = self.account.prices.get(order.instrument)
            reasons = check(self, order, price, now) if price is not None else ["missing_price"]
            recent = sum(
                instant(o.submitted_at) > now - timedelta(minutes=1) for o in self.orders.values()
            )
            if recent > self.limits.max_orders_per_minute:
                reasons.append("order_rate")
            if order.instrument in self.contracts:
                c = self.contracts[order.instrument]
                for x in (order.limit, order.stop):
                    if x is not None:
                        c.validate_price(x)
            order.transition("REJECTED" if reasons else "ACCEPTED", ",".join(reasons) or None)
            if reasons:
                self.alert("order_rejected", order.client_id + ":" + str(reasons))

        self._transaction("order:" + order.client_id, "order", order.payload(), op)
        return self.orders[order.client_id]

    def cancel(self, client_id, reason="operator_cancel"):
        def op():
            o = self.orders[client_id]
            if o.state not in TERMINAL:
                o.transition("CANCELLED", reason)

        self._transaction("cancel:" + client_id, "cancel", {"id": client_id, "reason": reason}, op)

    def replace(self, client_id, replacement, *, now):
        # Deliberately cancel/new: lost priority and a fresh risk decision are explicit.
        self.cancel(client_id, "cancel_for_replacement")
        return self.submit(replacement, now=now)

    def _match(self, event, now):
        if not self.state["connected"] or self.state["killed"]:
            return
        if event.kind != "quote" or not self.in_session(event.instrument, event.event_at):
            return
        liquidity = {
            1: int(decimal(event.ask_size) * self.participation),
            -1: int(decimal(event.bid_size) * self.participation),
        }
        for o in self.orders.values():
            if o.instrument != event.instrument or o.state not in ("ACCEPTED", "PARTIALLY_FILLED"):
                continue
            if self.state["strategies"][o.strategy]["execution"] != "RUNNING":
                continue
            if o.tif == "day" and self.session(
                o.instrument, instant(o.submitted_at)
            ) != self.session(o.instrument, event.event_at):
                o.transition("EXPIRED", "session_ended")
                continue
            if event.event_at <= instant(o.submitted_at) + self.latency:
                continue
            sign = 1 if o.remaining > 0 else -1
            reference = decimal(event.ask if sign > 0 else event.bid)
            if o.order_type in ("stop", "stop_limit") and o.triggered_at is None:
                if reference >= decimal(o.stop) if sign > 0 else reference <= decimal(o.stop):
                    o.triggered_at = event.event_at.isoformat()
                continue  # Triggering observation cannot also fill the order.
            if o.triggered_at is not None and event.event_at <= instant(o.triggered_at):
                continue
            tick = (
                self.contracts[o.instrument].spec.tick_size
                if o.instrument in self.contracts
                else decimal(".01")
            )
            price = reference + sign * tick * self.slippage_ticks
            if price <= 0:
                o.transition("REJECTED", "invalid_execution_price")
                continue
            if o.order_type in ("limit", "stop_limit"):
                if price > decimal(o.limit) if sign > 0 else price < decimal(o.limit):
                    continue
            reasons = check(self, o, price, now)
            if reasons:
                o.transition("REJECTED", ",".join(reasons))
                self.alert("fill_risk_rejected", reasons)
                continue
            quantity = min(abs(o.remaining), liquidity[sign])
            if not quantity:
                continue
            self.account.fill(
                o.instrument,
                sign * quantity,
                price,
                self.fee(o.instrument) * quantity,
                event.event_at,
                o.client_id,
                o.strategy,
            )
            liquidity[sign] -= quantity
            o.filled += quantity
            o.transition("FILLED" if o.remaining == 0 else "PARTIALLY_FILLED")

    def session(self, symbol, t):
        if symbol in self.contracts:
            return self.calendar.session(t)
        try:
            return self.equity_calendar.minute_to_session(
                t.replace(second=0, microsecond=0), direction="none"
            ).date()
        except ValueError:
            return None

    def heartbeat(self, now):
        now = instant(now)
        stale = [
            s
            for s, p in self.state["last_events"].items()
            if (now - instant(p["event_at"])).total_seconds() > self.limits.stale_seconds
        ]
        if stale:
            self.control("disconnect", reason="stale_feed:" + ",".join(stale))
        return stale

    def ingest(self, event, *, now=None):
        now = instant(now or datetime.now(UTC))
        if self.store.contains("event:" + event.identity):
            return False
        if event.mode != self.mode or event.instrument not in self.instruments:
            raise ValueError("Event mode/instrument differs from account configuration")
        if now < event.received_at or event.event_at > now:
            raise ValueError("Future event or receive timestamp")
        if self.state["clock"] and now < instant(self.state["clock"]):
            raise ValueError("Runtime clock cannot move backwards")

        def op():
            self.state["clock"] = now.isoformat()
            seq = ":".join(
                map(
                    str,
                    (
                        event.provider,
                        event.instrument,
                        event.kind,
                        event.event_at.date(),
                        event.sequence,
                    ),
                )
            )
            previous = self.state["sequences"].get(seq)
            if previous and previous != event.identity:
                self.state["connected"] = False
                self.alert("sequence_collision", seq)
                return
            self.state["sequences"][seq] = event.identity
            old = self.state["last_events"].get(event.instrument)
            if old and event.event_at < instant(old["event_at"]):
                self.alert("out_of_order", event.identity)
                return
            if event.kind == "heartbeat":
                return
            if (now - event.event_at).total_seconds() > self.limits.stale_seconds:
                self.state["connected"] = False
                self.alert("stale_event", event.identity)
                return
            # Gaps inside a known session suspend until data recovery and explicit resume.
            if old and self.session(event.instrument, event.event_at) == self.session(
                event.instrument, instant(old["event_at"])
            ):
                if (
                    event.event_at - instant(old["event_at"])
                ).total_seconds() > self.limits.stale_seconds:
                    self.state["connected"] = False
                    self.alert("data_gap", "recovery_and_operator_resume_required")
            self.state["last_events"][event.instrument] = event.payload()
            self.state["awaiting_fresh"] = False
            mark = (
                (decimal(event.bid) + decimal(event.ask)) / 2
                if event.kind == "quote"
                else decimal(event.price)
            )
            self.account.prices[event.instrument] = mark
            v = self.account.view()
            day = str(self.session(event.instrument, event.event_at))
            if self.state["day"] != day:
                self.state["day"] = day
                self.state["day_start"] = (
                    self.state["equity_history"][-1]["equity"]
                    if self.state["equity_history"]
                    else self.configuration["capital"]
                )
            self._match(event, now)
            v = self.account.view()
            self.state["peak"] = str(max(decimal(self.state["peak"]), v["equity"]))
            for sid, s in self.state["strategies"].items():
                pnl, _ = self.strategy_view(sid)
                s["peak"] = str(max(decimal(s["peak"]), decimal(s["capital"]) + pnl))
            self.state["equity_history"].append(
                {
                    "at": event.event_at.isoformat(),
                    "equity": str(v["equity"]),
                    "gross": str(v["gross"]),
                    "margin": str(v["initial_margin"]),
                }
            )
            if (
                v["equity"] < v["maintenance_margin"]
                or v["equity"] < decimal(self.state["peak"]) * (1 - decimal(self.limits.drawdown))
                or v["equity"]
                < decimal(self.state["day_start"]) * (1 - decimal(self.limits.daily_loss))
            ):
                self.state["killed"] = True
                for o in self.orders.values():
                    if o.state not in TERMINAL:
                        o.transition("CANCELLED", "portfolio_risk_halt")
                self.alert(
                    "portfolio_risk_halt",
                    "New orders stopped; positions retained, no automatic liquidation",
                )

        return self._transaction("event:" + event.identity, "market_event", event.payload(), op)

    def close(self):
        self.store.close()
