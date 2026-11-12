"""Shared Milestone 6 limit checks with conservative outstanding-order reservations."""

import math
from dataclasses import asdict, dataclass
from datetime import date

from quantlab.backtesting.models import decimal
from quantlab.portfolio.risk import limit_breaches


@dataclass(frozen=True)
class PaperLimits:
    gross: float = 1.8
    net: float = 1.8
    leverage: float = 1.8
    position: float = 1.0
    correlated: float = 1.8
    strategy: float = 1.0
    margin: float = 0.5
    daily_loss: float = 0.02
    drawdown: float = 0.1
    strategy_drawdown: float = 0.1
    max_contracts: int = 2
    max_order_units: int = 100
    max_order_notional: float = 100000
    stale_seconds: float = 120
    max_orders_per_minute: int = 20

    def __post_init__(self):
        if any(
            isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in asdict(self).values()
        ):
            raise ValueError("Risk bounds must be positive and finite")
        if any(
            getattr(self, k) > 1 for k in ("margin", "daily_loss", "drawdown", "strategy_drawdown")
        ):
            raise ValueError("Fractional loss/margin limits must not exceed one")
        for key in ("max_contracts", "max_order_units", "max_orders_per_minute"):
            if type(getattr(self, key)) is not int:
                raise ValueError("Integer risk limit required")


def check(runtime, order, price, now):
    a = runtime.account
    v = a.view()
    e = v["equity"]
    limits = runtime.limits
    reasons = []
    if runtime.state["killed"] or not runtime.state["connected"]:
        reasons.append("killed_or_disconnected")
    strategy = runtime.state["strategies"].get(order.strategy)
    if not strategy or strategy["execution"] != "RUNNING":
        reasons.append("strategy_not_running")
    if order.instrument not in runtime.instruments:
        return reasons + ["instrument_not_allowed"]
    if e <= 0:
        return reasons + ["nonpositive_equity"]
    mark = runtime.state["last_events"].get(order.instrument)
    if not mark or (now - runtime.time(mark["event_at"])).total_seconds() > limits.stale_seconds:
        reasons.append("stale_data")
    if not runtime.in_session(order.instrument, now):
        reasons.append("closed_session")
    if abs(order.remaining) > limits.max_order_units:
        reasons.append("order_units")
    m = runtime.multiplier(order.instrument)
    if abs(order.remaining) * price * m > decimal(limits.max_order_notional):
        reasons.append("order_notional")
    if v["equity"] < v["maintenance_margin"]:
        reasons.append("maintenance_margin")
    pending = [
        o
        for o in runtime.orders.values()
        if o.state in ("ACCEPTED", "PARTIALLY_FILLED") and o.client_id != order.client_id
    ]
    pending.append(order)
    gross = net_bound = margin = decimal(0)
    buy_cash = decimal(0)
    position = decimal(0)
    symbols = set(v["positions"]) | {o.instrument for o in pending}
    for s in symbols:
        p = price if s == order.instrument else a.prices[s]
        q = a.quantity(s)
        buys = sum(max(0, o.remaining) for o in pending if o.instrument == s)
        sells = sum(min(0, o.remaining) for o in pending if o.instrument == s)
        worst = max(abs(q + buys), abs(q + sells))
        value = worst * p * runtime.multiplier(s)
        gross += value
        net_bound += value
        position = max(position, value / e)
        if s in a.futures.contracts:
            c = a.futures.contracts[s]
            if (
                c.initial_margin is None
                or c.margin_as_of is None
                or date.fromisoformat(str(c.margin_as_of)) > now.date()
            ):
                reasons.append("missing_or_future_margin")
            else:
                margin += decimal(worst) * c.initial_margin
            if worst > limits.max_contracts:
                reasons.append("contract_count")
            if now >= c.last_trade:
                reasons.append("contract_expired")
        else:
            buy_cash += decimal(buys) * p
            if q + sells < 0:
                reasons.append("insufficient_stock_position")
    # Unspecified correlations conservatively place every instrument in one group.
    observed = {
        "gross": float(gross / e),
        "net": float(net_bound / e),
        "leverage": float(gross / e),
        "position": float(position),
        "correlated": float(gross / e),
        "margin": float(margin / e),
        "daily_loss": max(0, 1 - float(e / decimal(runtime.state["day_start"]))),
        "drawdown": max(0, 1 - float(e / decimal(runtime.state["peak"]))),
    }
    reasons += limit_breaches(observed, {k: getattr(limits, k) for k in observed})
    # Reserve fees for every remaining unit, and stock purchases plus futures margin.
    fees = sum(abs(o.remaining) * runtime.fee(o.instrument) for o in pending)
    if buy_cash + margin + fees > v["cash"]:
        reasons.append("cash_and_margin_reservation")
    if strategy:
        pnl, _ = runtime.strategy_view(order.strategy)
        capital = decimal(strategy["capital"])
        nav = capital + pnl
        owned = {}
        for fill in runtime.account.fills:
            if fill["strategy"] == order.strategy:
                symbol = fill["instrument"]
                owned[symbol] = owned.get(symbol, 0) + fill["quantity"]
        relevant = [o for o in pending if o.strategy == order.strategy]
        projected = decimal(0)
        for symbol in set(owned) | {o.instrument for o in relevant}:
            q = owned.get(symbol, 0)
            buys = sum(max(0, o.remaining) for o in relevant if o.instrument == symbol)
            sells = sum(min(0, o.remaining) for o in relevant if o.instrument == symbol)
            worst = max(abs(q + buys), abs(q + sells))
            p = price if symbol == order.instrument else a.prices[symbol]
            projected += decimal(worst) * p * runtime.multiplier(symbol)
            if symbol not in runtime.contracts and q + sells < 0:
                reasons.append("strategy_stock_short")
        if projected / e > decimal(limits.strategy):
            reasons.append("strategy_exposure")
        if nav < decimal(strategy["peak"]) * (1 - decimal(limits.strategy_drawdown)):
            reasons.append("strategy_drawdown")
    return sorted(set(reasons))
