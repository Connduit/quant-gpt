"""Research-only event replay on actual contracts, with margin and delayed execution."""

import heapq
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING

from quantlab.backtesting.metrics import performance
from quantlab.backtesting.models import ZERO, decimal
from quantlab.futures.accounting import FuturesLedger
from quantlab.futures.calendar import calendar_definition, calendar_from_dict
from quantlab.futures.risk import FuturesRisk


@dataclass(frozen=True)
class FuturesCosts:
    commission: object = "2.25"
    exchange_fee: object = "1.25"
    regulatory_fee: object = ".02"
    slippage_ticks: int = 1
    spread_ticks: int = 0

    def __post_init__(self):
        for key in ("commission", "exchange_fee", "regulatory_fee"):
            object.__setattr__(self, key, decimal(getattr(self, key)))
            if getattr(self, key) < 0:
                raise ValueError("Costs cannot be negative")
        for key in ("slippage_ticks", "spread_ticks"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError("Tick costs must be nonnegative integers")

    def execution(self, contract, row, delta):
        sign = 1 if delta > 0 else -1
        reference = decimal(row["open"])
        quote = row.get("ask_open" if delta > 0 else "bid_open")
        if quote is not None:
            base = contract.validate_price(quote)
            impact = decimal(self.slippage_ticks) * contract.spec.tick_size
            model = "actual_open_quote_plus_slippage"
        else:
            ticks = (
                decimal(self.slippage_ticks) + decimal(self.spread_ticks) / 2
            ).to_integral_value(rounding=ROUND_CEILING)
            base = reference
            impact = ticks * contract.spec.tick_size
            model = "trade_open_assumed_adverse_ticks"
        price = contract.validate_price(base + sign * impact)
        fee = abs(delta) * (self.commission + self.exchange_fee + self.regulatory_fee)
        return price, fee, reference, model


@dataclass(frozen=True)
class FuturesBacktestConfig:
    initial_cash: object = "100000"
    costs: FuturesCosts = FuturesCosts()
    risk: FuturesRisk = FuturesRisk()
    overnight: str = "flat_rth"
    settlement_policy: str = "last_bar_proxy"
    expiry_buffer_minutes: int = 2
    maximum_participation: float = 0.01
    mode: str = "research"

    def __post_init__(self):
        object.__setattr__(self, "initial_cash", decimal(self.initial_cash))
        if self.initial_cash <= 0 or self.mode != "research":
            raise ValueError("Positive capital and research-only mode required")
        if self.overnight not in (
            "hold",
            "flat_rth",
            "flat_session",
        ) or self.settlement_policy not in (
            "none",
            "last_bar_proxy",
            "official",
        ):
            raise ValueError("Unknown session/settlement policy")
        if type(self.expiry_buffer_minutes) is not int or self.expiry_buffer_minutes < 1:
            raise ValueError("Positive expiry buffer required")
        if not 0 < self.maximum_participation <= 1:
            raise ValueError("Participation must be in (0,1]")


def run_futures_backtest(frame, contracts, strategy, *, config=None, metadata=None, calendar=None):
    config = config or FuturesBacktestConfig()
    calendar = calendar or calendar_from_dict((metadata or {}).get("calendar", {}))
    rth_calendar = calendar_from_dict({**calendar_definition(calendar), "mode": "rth"})
    if (
        not metadata
        or metadata.get("tradable") is not True
        or metadata.get("price_basis") != "actual_contract_unadjusted"
    ):
        raise ValueError(
            "Execution requires actual tradable contract "
            "snapshots, never adjusted continuous prices"
        )
    if frame.is_empty() or any(t.tzinfo is None for t in frame["timestamp"].to_list()):
        raise ValueError("Aware contract bars required")
    if frame["available_at"].min() < frame["timestamp"].min():
        raise ValueError("Invalid data availability")
    if config.settlement_policy == "official" and (
        "settlement_price" not in frame.columns
        or "settlement_known_at" not in frame.columns
        or not metadata.get("settlement_source")
    ):
        raise ValueError("Official settlement requires sourced explicit settlement prices")
    first = frame["timestamp"].min()
    end = frame["available_at"].max()
    for c in contracts.values():
        if c.initial_margin is None or c.margin_as_of is None:
            raise ValueError("Dated margin metadata/assumptions required")
        if date.fromisoformat(str(c.margin_as_of)) > first.date():
            raise ValueError("Future margin information cannot price a historical decision")
    ledger = FuturesLedger(config.initial_cash, contracts)
    events = []
    serial = 0

    def schedule(at, priority, kind, payload):
        nonlocal serial
        serial += 1
        heapq.heappush(events, (at, priority, serial, kind, payload))

    rows = frame.sort("timestamp", "contract").to_dicts()
    openings = {}
    closings = {}
    for row in rows:
        c = contracts.get(row["contract"])
        if c is None:
            raise ValueError("Unknown contract")
        if calendar.session(row["timestamp"]) != row["session_date"]:
            raise ValueError("Futures bar is outside its declared exchange session")
        if row["timestamp"] >= c.last_trade:
            raise ValueError("Expired contract bar")
        for key in ("open", "high", "low", "close"):
            c.validate_price(row[key])
        if not row["timestamp"] < row["available_at"]:
            raise ValueError("Bar must be published after its opening")
        openings.setdefault(row["timestamp"], []).append(row)
        closings.setdefault(row["available_at"], []).append(row)
    for t, payload in openings.items():
        schedule(t, 1, "open", payload)
    for t, payload in closings.items():
        schedule(t, 0, "close", payload)
    for session in frame["session_date"].unique():
        expected = calendar.expected(session)
        if expected:
            close = expected[-1] + timedelta(minutes=1)
            if first <= close <= end:
                if config.overnight in ("flat_rth", "flat_session"):
                    flat_expected = (
                        rth_calendar.expected(session)
                        if config.overnight == "flat_rth"
                        else expected
                    )
                    if flat_expected:
                        schedule(
                            flat_expected[-1] - timedelta(microseconds=1),
                            -1,
                            "session_flat",
                            session,
                        )
                if config.settlement_policy == "last_bar_proxy":
                    schedule(close, 2, "settle", session)
    for identifier, c in contracts.items():
        deadline = c.last_trade - timedelta(minutes=config.expiry_buffer_minutes)
        if first <= deadline <= end:
            schedule(deadline - timedelta(microseconds=1), -1, "expiry_flat", identifier)
    if config.settlement_policy == "official":
        for row in rows:
            if row.get("settlement_price") is None:
                continue
            known = row["settlement_known_at"]
            known = datetime.fromisoformat(known) if isinstance(known, str) else known
            if known is None or known.tzinfo is None or known < row["available_at"]:
                raise ValueError("Official settlement publication timestamp is invalid")
            if metadata.get("holdout_start") and known >= datetime.fromisoformat(
                metadata["holdout_start"]
            ):
                raise ValueError("Protected settlement publication cannot enter research")
            schedule(known, 2, "official_settle", row)
    pending = {}
    staged = {}
    orders = []
    curve = []
    risk_log = []
    prices = {}
    known_volume = {}
    last_rows = {}
    halts = []
    locked_sessions = set()
    expired = set()
    peak = config.initial_cash
    day_open = config.initial_cash
    current_day = None
    halted = False

    def submit(identifier, target, now, reason):
        if type(target) is not int:
            raise ValueError("Strategies emit whole signed target contracts")
        if kind == "close" and now in openings:
            staged.setdefault(now, {})[identifier] = (target, reason)
            return
        held_position = ledger.positions.get(identifier)
        held_quantity = held_position.quantity if held_position else 0
        requested = target
        fees = abs(target - held_quantity) * (
            config.costs.commission + config.costs.exchange_fee + config.costs.regulatory_fee
        )
        target, reasons = config.risk.approve(
            ledger, identifier, target, prices, fees=fees, halted=halted
        )
        risk_log.append(
            {
                "at": now,
                "stage": "admission",
                "decision": "REJECTED"
                if target == held_quantity and requested != held_quantity
                else "REDUCED"
                if target != requested
                else "APPROVED",
                "contract": identifier,
                "requested": requested,
                "approved": target,
                "reasons": reasons,
            }
        )
        if target == held_quantity and requested != held_quantity:
            orders.append(
                {
                    "id": len(orders) + 1,
                    "contract": identifier,
                    "target": requested,
                    "submitted_at": now,
                    "resolved_at": now,
                    "status": "REJECTED_SIGNAL_RISK",
                    "reason": ";".join(reasons),
                }
            )
        existing = pending.get(identifier)
        if existing is not None and existing["target"] == target:
            return
        old = pending.pop(identifier, None)
        if old is not None:
            old["status"] = "CANCELLED"
            old["resolved_at"] = now
        held = ledger.positions.get(identifier)
        quantity = held.quantity if held else 0
        if target != quantity:
            order = {
                "id": len(orders) + 1,
                "contract": identifier,
                "target": target,
                "submitted_at": now,
                "status": "PENDING",
                "reason": reason,
            }
            pending[identifier] = order
            orders.append(order)

    while events:
        now, _, _, kind, payload = heapq.heappop(events)
        if kind == "session_flat":
            locked_sessions.add(payload)
            for identifier in contracts:
                submit(identifier, 0, now, "scheduled_session_flat")
        elif kind == "expiry_flat":
            expired.add(payload)
            submit(payload, 0, now, "scheduled_expiry_exit")
        elif kind == "open":
            available = {r["contract"]: r for r in payload}
            prices.update({identifier: decimal(r["open"]) for identifier, r in available.items()})
            session = payload[0]["session_date"]
            view = ledger.view(prices)
            if current_day != session:
                current_day = session
                day_open = view["equity"]
            peak = max(peak, view["equity"])
            opening_loss = view["equity"] < day_open * decimal(
                1 - config.risk.maximum_daily_loss
            ) or view["equity"] < peak * decimal(
                1 - min(config.risk.maximum_drawdown, config.risk.maximum_strategy_drawdown)
            )

            def reduction(order):
                p = ledger.positions.get(order["contract"])
                held = p.quantity if p else 0
                return abs(order["target"]) < abs(held) and order["target"] * held >= 0

            for order in sorted(list(pending.values()), key=lambda o: (not reduction(o), o["id"])):
                identifier = order["contract"]
                if identifier not in available or order["submitted_at"] >= now:
                    continue
                c = contracts[identifier]
                if now >= c.last_trade:
                    order["status"] = "EXPIRED_UNFILLED"
                    pending.pop(identifier)
                    continue
                row = available[identifier]
                p = ledger.positions.get(identifier)
                held = p.quantity if p else 0
                delta = order["target"] - held
                if not delta:
                    pending.pop(identifier)
                    order["status"] = "NO_CHANGE"
                    continue
                price, fee, reference, model = config.costs.execution(c, row, delta)
                impact = (
                    max(ZERO, (price - reference) * (1 if delta > 0 else -1))
                    * c.spec.multiplier
                    * abs(delta)
                )
                target, reasons = config.risk.approve(
                    ledger,
                    identifier,
                    order["target"],
                    prices,
                    fees=fee + impact,
                    halted=halted or opening_loss or identifier in expired and order["target"] != 0,
                )
                desired = target - held
                # Forced reductions still require actual quotes; stops never guarantee loss caps.
                cap = int(known_volume.get(identifier, 0) * config.maximum_participation)
                if abs(desired) > cap:
                    desired = (1 if desired > 0 else -1) * cap
                    target = held + desired
                    reasons.append("prior_published_volume_participation")
                decision = (
                    "REJECTED"
                    if not desired
                    else "REDUCED"
                    if target != order["target"]
                    else "APPROVED"
                )
                risk_log.append(
                    {
                        "at": now,
                        "order_id": order["id"],
                        "decision": decision,
                        "reasons": reasons,
                        "requested": order["target"],
                        "approved": target,
                    }
                )
                if desired:
                    price, fee, reference, model = config.costs.execution(c, row, desired)
                    trade = ledger.fill(
                        identifier,
                        desired,
                        price,
                        fee=fee,
                        reference_price=reference,
                        timestamp=now,
                        reason=order["reason"],
                    )
                    trade["execution_model"] = model
                    trade["commission"] = abs(desired) * config.costs.commission
                    trade["exchange_fee"] = abs(desired) * config.costs.exchange_fee
                    trade["regulatory_fee"] = abs(desired) * config.costs.regulatory_fee
                    order["status"] = "FILLED" if decision == "APPROVED" else "FILLED_REDUCED"
                else:
                    order["status"] = "REJECTED"
                order["resolved_at"] = now
                pending.pop(identifier, None)
            view = ledger.view(prices)
            if view["maintenance_breach"] or opening_loss:
                halted = True
                halts.append(
                    {
                        "at": now,
                        "reason": "maintenance_margin_or_opening_loss",
                        "equity": view["equity"],
                    }
                )
                for identifier, p in ledger.positions.items():
                    if p.quantity:
                        submit(identifier, 0, now, "margin_or_loss_liquidate_next_eligible_open")
            for identifier, (target, reason) in staged.pop(now, {}).items():
                if not halted or target == 0:
                    submit(identifier, target, now, reason)
        elif kind == "close":
            prices.update({r["contract"]: decimal(r["close"]) for r in payload})
            for row in payload:
                known_volume[row["contract"]] = row["volume"]
                last_rows[row["contract"]] = row
            view = ledger.view(prices)
            peak = max(peak, view["equity"])
            dd = 1 - float(view["equity"] / peak) if peak > 0 else 1
            if dd >= min(config.risk.maximum_drawdown, config.risk.maximum_strategy_drawdown):
                halted = True
                halts.append({"at": now, "reason": "drawdown_suspend", "drawdown": dd})
                for identifier, p in ledger.positions.items():
                    if p.quantity:
                        submit(identifier, 0, now, "drawdown_reduce_next_eligible_open")
            for row in payload:
                if row["session_date"] in locked_sessions or halted:
                    continue
                if (
                    config.overnight == "flat_rth"
                    and rth_calendar.session(row["timestamp"]) is None
                ):
                    continue
                context = {
                    "now": now,
                    "row": {
                        k: v
                        for k, v in row.items()
                        if k not in ("settlement_price", "settlement_known_at")
                    },
                    "prices": prices.copy(),
                    "positions": {k: asdict(v) for k, v in ledger.positions.items()},
                    "portfolio": view,
                    "halted": halted,
                    "contracts": contracts,
                }
                targets = strategy.on_bar(context)
                for identifier, target in targets.items():
                    if identifier not in contracts:
                        raise ValueError("Unknown target contract")
                    if identifier in expired and target:
                        continue
                    roll = next(
                        (r for r in getattr(strategy, "roll_events", []) if r["at"] == now), None
                    )
                    reason = (
                        ("roll_close" if target == 0 and identifier == roll["old"] else "roll_open")
                        if roll and identifier in (roll["old"], roll["new"])
                        else "strategy_target"
                    )
                    submit(identifier, target, now, reason)
            curve.append(
                {
                    "timestamp": now,
                    "session_date": payload[0]["session_date"],
                    "equity": view["equity"],
                    "cash": view["cash"],
                    "quantity": sum(abs(p.quantity) for p in ledger.positions.values()),
                    "gross_exposure": view["gross_notional"] / view["equity"]
                    if view["equity"] > 0
                    else ZERO,
                    "margin_utilization": view["margin_utilization"],
                    "initial_margin": view["initial_margin"],
                    "realized_pnl": ledger.realized_gross - ledger.fees,
                    "unrealized_pnl": view["lifetime_unrealized"],
                    "unrealized_since_settlement": view["unrealized_since_settlement"],
                    "dividend_income": ZERO,
                    "commissions": ledger.fees,
                    "spread_cost": ZERO,
                    "slippage_cost": ledger.execution_cost,
                    "drawdown": -dd,
                    "bar_return": (
                        float(
                            view["equity"] / (curve[-1]["equity"] if curve else config.initial_cash)
                            - 1
                        )
                        if not curve or curve[-1]["equity"] > 0
                        else None
                    ),
                }
            )
        elif kind == "official_settle":
            ledger.settle(
                payload["contract"],
                payload["settlement_price"],
                timestamp=now,
                source=metadata["settlement_source"],
            )
        elif kind == "settle":
            for identifier, row in last_rows.items():
                if row["session_date"] != payload:
                    continue
                price = (
                    row.get("settlement_price")
                    if config.settlement_policy == "official"
                    else row["close"]
                )
                if price is None:
                    raise ValueError("Missing required settlement price")
                ledger.settle(
                    identifier,
                    price,
                    timestamp=now,
                    source=metadata.get("settlement_source")
                    if config.settlement_policy == "official"
                    else (
                        "explicit research proxy: final observed "
                        "configured-session close, not official CME settlement"
                    ),
                )
    if not curve:
        raise ValueError("No available bars to mark")
    for order in pending.values():
        order["status"] = "EXPIRED_END_OF_DATA"
    daily = {r["session_date"]: r.copy() for r in curve}
    exits = [
        {
            "side": "sell" if t["closed_contracts"] else "buy",
            "realized_pnl": t["closed_net_pnl"],
            "price": t["price"],
            "quantity": abs(t["signed_quantity"]),
        }
        for t in ledger.trades
    ]
    if any(r["equity"] <= 0 for r in daily.values()):
        metrics = {
            "sessions": len(daily),
            "total_return": float(curve[-1]["equity"] / config.initial_cash - 1),
            "final_equity": curve[-1]["equity"],
            "annualized_return": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "annualized_volatility": None,
            "maximum_drawdown": min(r["drawdown"] for r in curve),
            "fill_count": len(ledger.trades),
            "exit_fill_count": sum(t["closed_contracts"] > 0 for t in ledger.trades),
            "win_rate": None,
            "profit_factor": None,
            "average_exit_pnl": None,
            "account_status": "INSOLVENT",
            "commissions": ledger.fees,
            "slippage_cost": ledger.execution_cost,
            "spread_cost": ZERO,
        }
        for row in daily.values():
            row["daily_return"] = None
    else:
        metrics = performance(list(daily.values()), exits, config.initial_cash, 252)
        metrics["account_status"] = "FUNDED"

    valid_exposure = [float(r["gross_exposure"]) for r in curve if r["equity"] > 0]
    metrics["average_gross_exposure"] = (
        sum(valid_exposure) / len(valid_exposure) if valid_exposure else None
    )
    metrics["time_in_market"] = sum(r["quantity"] > 0 for r in curve) / len(curve)
    if metrics["sessions"] < 2:
        metrics["sharpe_ratio"] = None
        metrics["sortino_ratio"] = None
        metrics["annualized_volatility"] = None
    metrics["daily_close_drawdown"] = metrics["maximum_drawdown"]
    metrics["maximum_drawdown"] = min(r["drawdown"] for r in curve)
    metrics["gross_turnover"] = float(
        sum((t["notional"] for t in ledger.trades), ZERO)
        / decimal(sum(float(r["equity"]) for r in curve) / len(curve))
    )
    metrics["net_pnl"] = float(curve[-1]["equity"] - config.initial_cash)
    metrics["fees"] = float(ledger.fees)
    metrics["execution_cost_vs_trade_open"] = float(ledger.execution_cost)
    metrics["gross_before_fees_and_execution_cost"] = (
        metrics["net_pnl"] + metrics["fees"] + float(ledger.execution_cost)
    )
    closed = sum(t["closed_contracts"] for t in ledger.trades)
    metrics["roll_costs"] = float(
        sum(
            (
                t["fees"]
                + (t["price"] - decimal(t["reference_price"]))
                * (1 if t["signed_quantity"] > 0 else -1)
                * contracts[t["contract"]].spec.multiplier
                * abs(t["signed_quantity"])
                for t in ledger.trades
                if t["reason"].startswith("roll_")
            ),
            ZERO,
        )
    )
    metrics["fills_per_session"] = len(ledger.trades) / len(daily)
    metrics["closed_contracts"] = closed
    metrics["average_profit_per_closed_contract"] = (
        float(sum((t["closed_net_pnl"] for t in ledger.trades), ZERO) / closed) if closed else None
    )
    metrics["maximum_margin_utilization"] = max(
        (float(r["margin_utilization"]) for r in curve if r["margin_utilization"] is not None),
        default=0,
    )
    metrics["long_closed_pnl"] = float(
        sum(
            (
                t["closed_net_pnl"]
                for t in ledger.trades
                if t["closed_contracts"] and t["signed_quantity"] < 0
            ),
            ZERO,
        )
    )
    metrics["short_closed_pnl"] = float(
        sum(
            (
                t["closed_net_pnl"]
                for t in ledger.trades
                if t["closed_contracts"] and t["signed_quantity"] > 0
            ),
            ZERO,
        )
    )
    by_hour = {}
    for t in ledger.trades:
        hour = t["timestamp"].astimezone(calendar.calendar.tz).hour
        by_hour.setdefault(str(hour), {"fills": 0, "closed_pnl": 0.0})
        by_hour[str(hour)]["fills"] += 1
        by_hour[str(hour)]["closed_pnl"] += float(t["closed_net_pnl"])
    return {
        "performance": metrics,
        "equity": curve,
        "daily_equity": list(daily.values()),
        "trades": ledger.trades,
        "orders": orders,
        "risk_decisions": risk_log,
        "settlements": ledger.settlements,
        "halts": halts,
        "time_of_day": by_hour,
        "configuration": asdict(config),
        "source": metadata,
        "final_account": ledger.view(prices),
        "final_positions": {k: asdict(v) for k, v in ledger.positions.items()},
        "warnings": [
            "Research-only; no live orders or empirical edge certification.",
            (
                "Costs and dated margins are declared "
                "research assumptions unless independently sourced."
            ),
            "Settlement proxy is not authoritative exchange settlement.",
            "Close-triggered stop/forced orders execute at a later eligible open and may gap.",
        ],
    }
