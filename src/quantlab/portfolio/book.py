"""Multi-strategy targets, netting, shared risk and actual-fill attribution."""

from dataclasses import asdict, dataclass, replace
from decimal import ROUND_FLOOR

from quantlab.backtesting.models import ZERO, Fill, Side, decimal
from quantlab.backtesting.portfolio import Position
from quantlab.portfolio.allocation import allocate
from quantlab.portfolio.ledger import AttributionLedger, distribute_fill, reconcile
from quantlab.portfolio.risk import RiskLimits, constrain, size_position
from quantlab.strategies.base import Signal


@dataclass
class Registration:
    name: str
    strategy: object
    research_status: str = "RESEARCH_ONLY"
    paper_approved: bool = False
    suspended: bool = False


class MultiStrategyBook:
    def __init__(
        self,
        registrations,
        *,
        method="equal",
        mode="research",
        limits=None,
        fixed=None,
        cash_buffer=0.1,
        schedule="weekly",
        threshold=0.01,
        minimum_trade_value=50,
        maximum_turnover=0.4,
        sectors=None,
        target_volatility=0.12,
        minimum_history=20,
        reference_history=(),
        maximum_trade_cost_fraction=0.05,
        maximum_participation=None,
        execution_available=True,
        reject_order_ids=(),
        position_sizing="target_weight",
        risk_fraction=0.01,
    ):
        if mode not in ("research", "paper"):
            raise ValueError("Live portfolio execution is unavailable")
        if not registrations or len({r.name for r in registrations}) != len(registrations):
            raise ValueError("Strategy names must be unique")
        allowed = {
            "RESEARCH_ONLY",
            "REJECTED",
            "INSUFFICIENT_EVIDENCE",
            "REQUIRES_FURTHER_TESTING",
            "VALIDATED_FOR_PAPER_TRADING",
            "SUSPENDED",
        }
        for r in registrations:
            if type(r.paper_approved) is not bool:
                raise ValueError("Paper approval must be an explicit boolean")
            if r.research_status not in allowed:
                raise ValueError("Unknown research status")
            if mode == "paper" and (
                r.research_status != "VALIDATED_FOR_PAPER_TRADING" or not r.paper_approved
            ):
                raise PermissionError(
                    "Paper allocation requires validated status and explicit approval"
                )
            if r.research_status == "SUSPENDED":
                r.suspended = True
        if schedule not in ("daily", "weekly", "monthly", "threshold"):
            raise ValueError("Invalid rebalance schedule")
        if not 0 <= threshold <= 1 or minimum_trade_value < 0 or not 0 < maximum_turnover <= 2:
            raise ValueError("Invalid rebalance thresholds")
        self.registrations = {r.name: r for r in registrations}
        self.method = method
        self.mode = mode
        self.limits = limits or RiskLimits()
        self.fixed = fixed
        self.cash_buffer = cash_buffer
        self.schedule = schedule
        self.threshold = threshold
        self.minimum_trade_value = minimum_trade_value
        self.maximum_turnover = maximum_turnover
        self.sectors = sectors or {}
        self.target_volatility = target_volatility
        self.minimum_history = minimum_history
        self.reference_history = tuple(reference_history)
        if not 0 < maximum_trade_cost_fraction <= 1:
            raise ValueError("Trade cost fraction must be in (0,1]")
        self.maximum_trade_cost_fraction = maximum_trade_cost_fraction
        if maximum_participation is not None and not 0 < maximum_participation <= 1:
            raise ValueError("Participation must be in (0,1]")
        if type(execution_available) is not bool:
            raise ValueError("Execution availability must be boolean")
        self.maximum_participation = maximum_participation
        self.execution_available = execution_available
        self.reject_order_ids = set(reject_order_ids)
        self.known_volume = {}
        self.turnover_day = None
        self.opening_turnover = ZERO
        if position_sizing not in (
            "target_weight",
            "fixed_fractional",
            "volatility_adjusted",
            "atr",
            "risk_budget",
        ):
            raise ValueError("Unsupported position sizing")
        if not 0 < risk_fraction <= 1:
            raise ValueError("Risk fraction must be in (0,1]")
        self.position_sizing = position_sizing
        self.risk_fraction = risk_fraction
        self.ledgers = {}
        self.targets = {r.name: {} for r in registrations}
        self.logs = []
        self.allocations = []
        self.attribution = []
        self.internal_transfers = []
        self.risk_decisions = []
        self.history = []
        self.symbol_history = []
        self.last_day = None
        self.last_rebalance = None
        self.master_peak = None
        self.previous_equity = None
        self.strategy_peak = {}
        self.previous_strategy = {}
        self.stressed = False
        self.daily_halt = False
        self.stress_caps = None
        self.strategy_equities = {r.name: [] for r in registrations}
        self.weights = {r.name: 0 for r in registrations}
        self.last_prices = {}
        self.master = None

    def spec(self):
        return {
            "method": self.method,
            "mode": self.mode,
            "strategies": [
                {
                    "name": r.name,
                    "research_status": r.research_status,
                    "paper_approved": r.paper_approved,
                    "spec": r.strategy.spec() if hasattr(r.strategy, "spec") else repr(r.strategy),
                }
                for r in self.registrations.values()
            ],
            "limits": asdict(self.limits),
            "schedule": self.schedule,
            "cash_buffer": self.cash_buffer,
            "position_sizing": self.position_sizing,
            "risk_fraction": self.risk_fraction,
            "suspension_policy": (
                "block increases; hold existing unless planned stress reduction on rebalance"
            ),
        }

    def on_start(self, portfolio, feeds, config):
        self.master = portfolio
        self.feeds = feeds
        self.costs = config.costs
        names = list(self.registrations)
        for i, name in enumerate(names):
            initial = (
                portfolio.initial_cash / len(names)
                if i < len(names) - 1
                else portfolio.initial_cash - sum(p.initial_cash for p in self.ledgers.values())
            )
            self.ledgers[name] = AttributionLedger(initial)
            self.strategy_peak[name] = initial
            self.previous_strategy[name] = initial
        self.master_peak = self.previous_equity = portfolio.initial_cash

    def on_action(self, kind, payload, now):
        for name, ledger in self.ledgers.items():
            if kind == "split":
                symbol, split = payload
                ledger.split(symbol, split.ratio)
                if symbol in self.targets[name]:
                    self.targets[name][symbol] *= split.ratio
            elif kind == "dividend_ex":
                symbol, identifier, dividend = payload
                ledger.accrue_dividend(identifier, symbol, dividend.amount)
            elif kind == "dividend_pay":
                ledger.pay_dividend(payload[1])

    def reactivate(self, name, *, reason, approved=False):
        if not approved or not reason.strip():
            raise PermissionError("Manual reactivation requires approval and reason")
        registration = self.registrations[name]
        registration.suspended = False
        self.strategy_peak[name] = self.previous_strategy[name]
        self.logs.append({"kind": "manual_reactivation", "strategy": name, "reason": reason})

    def reactivate_portfolio(self, *, reason, approved=False):
        if not approved or not reason.strip():
            raise PermissionError("Manual portfolio reset requires approval and reason")
        self.stressed = False
        self.stress_caps = None
        self.daily_halt = False
        self.master_peak = self.previous_equity
        self.logs.append({"kind": "manual_portfolio_reset", "reason": reason})

    def _due(self, day):
        old = self.last_rebalance
        return (
            old is None
            or self.schedule in ("daily", "threshold")
            or (self.schedule == "weekly" and day.isocalendar()[:2] != old.isocalendar()[:2])
            or (self.schedule == "monthly" and (day.year, day.month) != (old.year, old.month))
        )

    def _correlated_groups(self):
        import numpy as np

        if len(self.symbol_history) < 20:
            return ()
        x = np.asarray(self.symbol_history[-126:])
        names = sorted(self.feeds)
        active = np.std(x, axis=0) > 1e-12
        correlation = np.eye(len(names))
        indices = np.flatnonzero(active)
        if len(indices) > 1:
            correlation[np.ix_(indices, indices)] = np.corrcoef(x[:, indices], rowvar=False)
        groups = []
        for i in range(len(names)):
            group = [
                names[j]
                for j in range(len(names))
                if correlation[i, j] >= self.limits.correlation_threshold
            ]
            if len(group) > 1:
                groups.append(group)
        return groups

    def on_bar(self, context):
        day = context.bar.session_date
        if day == self.last_day or any(
            not h or h[-1].session_date != day for h in context.histories.values()
        ):
            return ()
        self.last_day = day
        self.known_volume = {s: h[-1].volume for s, h in context.histories.items()}
        self.last_prices = dict(context.prices)
        if not self._due(day):
            return ()
        known_history = [
            r["returns"] for r in self.reference_history if r["available_at"] <= context.now
        ]
        history = known_history if self.reference_history else self.history
        allocation = allocate(
            list(self.registrations),
            history,
            method=self.method,
            fixed=self.fixed,
            cash_buffer=self.cash_buffer,
            maximum_weight=self.limits.maximum_strategy,
            target_volatility=self.target_volatility,
            minimum=self.minimum_history,
        )
        self.weights = allocation["weights"]
        self.allocations.append({"at": context.now, **allocation})
        equity = context.portfolio.equity
        if equity <= 0:
            return ()
        proposals = {name: dict(targets) for name, targets in self.targets.items()}
        for name, registration in self.registrations.items():
            ledger = self.ledgers[name]
            view = ledger.view(context.prices)
            budget = equity * decimal(self.weights[name])
            # This view is an allocation budget, not another funded brokerage account.
            virtual = replace(
                view,
                equity=budget,
                cash=budget
                - sum((p.quantity * context.prices[s] for s, p in view.positions.items()), ZERO)
                - view.dividend_receivable,
            )
            for _symbol, history in sorted(context.histories.items()):
                if not history:
                    continue
                scoped = replace(context, bar=history[-1], history=history, portfolio=virtual)
                for signal in registration.strategy.on_bar(scoped):
                    if signal.symbol not in self.feeds:
                        raise ValueError("Unknown strategy instrument")
                    quantity = signal.target_quantity
                    if quantity and budget > 0 and self.position_sizing != "target_weight":
                        import math
                        import statistics

                        observed = context.histories[signal.symbol][-21:]
                        if len(observed) < 3:
                            quantity = min(
                                quantity, view.positions.get(signal.symbol, Position()).quantity
                            )
                        else:
                            returns = [
                                math.log(float(b.close / a.close))
                                for a, b in zip(observed, observed[1:], strict=False)
                            ]
                            volatility = statistics.stdev(returns) * math.sqrt(252)
                            atr = sum(
                                (
                                    max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
                                    for a, b in zip(observed, observed[1:], strict=False)
                                ),
                                ZERO,
                            ) / (len(observed) - 1)
                            if volatility > 0 and atr > 0:
                                fraction = min(
                                    1, float(quantity * context.prices[signal.symbol] / budget)
                                )
                                quantity = size_position(
                                    budget,
                                    context.prices[signal.symbol],
                                    method=self.position_sizing,
                                    fraction=fraction,
                                    volatility=volatility,
                                    atr=atr,
                                    risk_fraction=self.risk_fraction,
                                    maximum_weight=1,
                                )
                            else:
                                quantity = min(
                                    quantity, view.positions.get(signal.symbol, Position()).quantity
                                )
                    proposals[name][signal.symbol] = quantity
            total = sum((q * context.prices[s] for s, q in proposals[name].items()), ZERO)
            scale = min(decimal(1), budget / total) if total else decimal(1)
            for symbol, q in proposals[name].items():
                q = (q * scale).to_integral_value(rounding=ROUND_FLOOR)
                held = view.positions.get(symbol, Position()).quantity
                if registration.suspended or self.daily_halt:
                    q = min(q, held)
                if self.stressed:
                    q = min(q, self.stress_caps[name].get(symbol, ZERO))
                proposals[name][symbol] = q
        combined = {s: sum((p.get(s, ZERO) for p in proposals.values()), ZERO) for s in self.feeds}
        capped, reasons = constrain(
            combined, context.prices, equity, self.limits, self.sectors, self._correlated_groups()
        )
        for symbol, target in capped.items():
            held = context.portfolio.positions.get(symbol, Position()).quantity
            increase = max(ZERO, target - held)
            notional = increase * context.prices[symbol]
            if notional:
                fee = max(
                    self.costs.minimum_commission,
                    self.costs.commission_fixed + increase * self.costs.commission_per_share,
                )
                fee += notional * (self.costs.slippage_bps + self.costs.spread_bps / 2) / 10000
                if fee / notional > decimal(self.maximum_trade_cost_fraction):
                    capped[symbol] = held
                    reasons.append(f"transaction_cost:{symbol}")
        for symbol, target in capped.items():
            total = combined[symbol]
            if target < total:
                remaining = target
                owners = [n for n in proposals if proposals[n].get(symbol, ZERO) > 0]
                for i, name in enumerate(owners):
                    q = (
                        remaining
                        if i == len(owners) - 1
                        else (proposals[name][symbol] * target / total).to_integral_value(
                            rounding=ROUND_FLOOR
                        )
                    )
                    proposals[name][symbol] = q
                    remaining -= q
        # Turnover cap scales all strategy deltas, including internal transfers.
        turnover = sum(
            (
                abs(p.get(s, ZERO) - self.ledgers[n].positions.get(s, Position()).quantity)
                * context.prices[s]
                for n, p in proposals.items()
                for s in self.feeds
            ),
            ZERO,
        )
        turn_scale = (
            min(decimal(1), equity * decimal(self.maximum_turnover) / turnover)
            if turnover
            else decimal(1)
        )
        for name in proposals:
            for symbol in self.feeds:
                held = self.ledgers[name].positions.get(symbol, Position()).quantity
                desired = proposals[name].get(symbol, ZERO)
                target = max(
                    ZERO,
                    (held + (desired - held) * turn_scale).to_integral_value(rounding=ROUND_FLOOR),
                )
                delta_value = abs(target - held) * context.prices[symbol]
                # Risk reductions always pass thresholds; thresholds suppress cosmetic increases.
                if target > held and (
                    delta_value < decimal(self.minimum_trade_value)
                    or float(delta_value / equity) < self.threshold
                ):
                    target = held
                proposals[name][symbol] = target
        self.targets = proposals
        self._cross(context.now, context.prices)
        self.last_rebalance = day
        self.risk_decisions.append(
            {
                "at": context.now,
                "stage": "target",
                "decision": "REDUCED" if reasons else "APPROVED",
                "reasons": reasons,
                "turnover_scale": turn_scale,
            }
        )
        signals = tuple(
            Signal(s, sum((p.get(s, ZERO) for p in self.targets.values()), ZERO))
            for s in sorted(self.feeds)
        )
        self.logs.append(
            {
                "at": context.now,
                "kind": "rebalance",
                "targets": {s.symbol: s.target_quantity for s in signals},
            }
        )
        self.daily_halt = False
        return signals

    def _cross(self, now, prices):
        for symbol in sorted(self.feeds):
            sellers = []
            buyers = []
            for name, ledger in self.ledgers.items():
                delta = (
                    self.targets[name].get(symbol, ZERO)
                    - ledger.positions.get(symbol, Position()).quantity
                )
                if delta < 0:
                    sellers.append([name, -delta])
                elif delta > 0:
                    buyers.append([name, delta])
            for sell in sellers:
                for buy in buyers:
                    quantity = min(sell[1], buy[1])
                    if not quantity:
                        continue
                    for name, side in ((sell[0], Side.SELL), (buy[0], Side.BUY)):
                        self.ledgers[name].apply_fill(
                            Fill(
                                0,
                                symbol,
                                side,
                                quantity,
                                now,
                                prices[symbol],
                                prices[symbol],
                                ZERO,
                                ZERO,
                                ZERO,
                            )
                        )
                    sell[1] -= quantity
                    buy[1] -= quantity
                    self.internal_transfers.append(
                        {
                            "at": now,
                            "symbol": symbol,
                            "seller": sell[0],
                            "buyer": buy[0],
                            "quantity": quantity,
                            "price": prices[symbol],
                        }
                    )
        reconcile(self.ledgers, self.master, prices)

    def before_fill(self, order, opening, prices):
        if self.turnover_day != opening.timestamp.date():
            self.turnover_day = opening.timestamp.date()
            self.opening_turnover = ZERO
        current = self.master.positions.get(order.symbol, Position()).quantity
        approved = order.quantity
        reasons = []
        if not self.execution_available or order.order_id in self.reject_order_ids:
            approved = ZERO
            reasons.append("execution_unavailable_or_simulated_rejection")
        if self.maximum_participation is not None:
            cap = decimal(int(self.known_volume.get(order.symbol, 0) * self.maximum_participation))
            if approved > cap:
                approved = cap
                reasons.append("known_volume_participation")
        opening_equity = self.master.view(prices).equity
        if order.side == Side.BUY and (
            opening_equity <= self.previous_equity * decimal(1 - self.limits.maximum_daily_loss)
            or opening_equity <= self.master_peak * decimal(1 - self.limits.maximum_drawdown)
        ):
            approved = ZERO
            reasons.append("opening_loss_limit")
        if order.side == Side.BUY:
            target = {s: self.master.positions.get(s, Position()).quantity for s in self.feeds}
            target[order.symbol] += approved
            capped, why = constrain(
                target,
                prices,
                self.master.view(prices).equity,
                self.limits,
                self.sectors,
                self._correlated_groups(),
            )
            approved = min(approved, max(ZERO, capped[order.symbol] - current))
            reasons += why
            # Binary-search actual opening costs and available shared cash, including minimum fees.
            low, high = 0, int(approved)
            while low < high:
                mid = (low + high + 1) // 2
                fill = self.costs.fill(replace(order, quantity=decimal(mid)), opening)
                if fill.quantity * fill.price + fill.commission <= self.master.cash:
                    low = mid
                else:
                    high = mid - 1
            if decimal(low) < approved:
                reasons.append("opening_buying_power")
            approved = decimal(low)
        if approved:
            unit = self.costs.fill(replace(order, quantity=approved), opening).price
            remaining = max(
                ZERO, opening_equity * decimal(self.maximum_turnover) - self.opening_turnover
            )
            cap = (remaining / unit).to_integral_value(rounding=ROUND_FLOOR)
            if cap < approved:
                approved = cap
                reasons.append("opening_turnover")
        if approved < order.quantity:
            reasons.append("pre_fill_reduction")
        self.risk_decisions.append(
            {
                "at": opening.timestamp,
                "stage": "opening",
                "order_id": order.order_id,
                "decision": "REJECTED"
                if not approved
                else "REDUCED"
                if approved < order.quantity
                else "APPROVED",
                "requested": order.quantity,
                "approved": approved,
                "reasons": sorted(set(reasons)),
            }
        )
        return approved

    def on_fill(self, fill):
        self.opening_turnover += fill.quantity * fill.price
        demands = {
            n: max(
                ZERO,
                (
                    self.targets[n].get(fill.symbol, ZERO)
                    - p.positions.get(fill.symbol, Position()).quantity
                )
                * (1 if fill.side == Side.BUY else -1),
            )
            for n, p in self.ledgers.items()
        }
        total = sum(demands.values(), ZERO)
        if total < fill.quantity:
            raise ArithmeticError("Fill exceeds attributed demand")
        quantities = {}
        remaining = fill.quantity
        names = [n for n in demands if demands[n]]
        for i, name in enumerate(names):
            q = (
                remaining
                if i == len(names) - 1
                else (fill.quantity * demands[name] / total).quantize(
                    decimal("1e-18"), rounding=ROUND_FLOOR
                )
            )
            quantities[name] = q
            remaining -= q
        for name, portion in distribute_fill(fill, quantities).items():
            self.ledgers[name].apply_fill(portion)

    def on_close(self, now, bars, master):
        prices = {b.symbol: b.close for b in bars}
        reconcile(self.ledgers, self.master, prices)
        views = {name: p.view(prices) for name, p in self.ledgers.items()}
        returns = []
        for name, view in views.items():
            previous = self.previous_strategy[name]
            returns.append(float(view.equity / previous - 1) if previous > 0 else 0.0)
            self.previous_strategy[name] = view.equity
            self.strategy_peak[name] = max(self.strategy_peak[name], view.equity)
            dd = (
                float(1 - view.equity / self.strategy_peak[name])
                if self.strategy_peak[name] > 0
                else 1
            )
            if (
                dd >= self.limits.maximum_strategy_drawdown
                and not self.registrations[name].suspended
            ):
                self.registrations[name].suspended = True
                self.logs.append(
                    {"at": now, "kind": "strategy_suspension", "strategy": name, "drawdown": dd}
                )
            self.strategy_equities[name].append(view.equity)
            rolling_peak = max(self.strategy_equities[name][-63:])
            rolling_drawdown = float(1 - view.equity / rolling_peak) if rolling_peak > 0 else 1
            self.attribution.append(
                {
                    "rolling_drawdown_63_sessions": rolling_drawdown,
                    "at": now,
                    "session_date": bars[0].session_date,
                    "strategy": name,
                    "equity": view.equity,
                    "pnl": view.equity - self.ledgers[name].initial_cash,
                    "cash_claim": view.cash,
                    "market_value": view.equity - view.cash - view.dividend_receivable,
                    "receivables": view.dividend_receivable,
                    "daily_return": returns[-1],
                    "drawdown": dd,
                    "suspended": self.registrations[name].suspended,
                }
            )
        self.history.append(returns)
        if self.last_prices:
            self.symbol_history.append(
                [
                    float(prices[s] / self.last_prices.get(s, prices[s]) - 1)
                    for s in sorted(self.feeds)
                ]
            )
        self.master_peak = max(self.master_peak, master.equity)
        drawdown = float(1 - master.equity / self.master_peak)
        daily = float(master.equity / self.previous_equity - 1) if self.previous_equity > 0 else -1
        self.previous_equity = master.equity
        if drawdown >= self.limits.maximum_drawdown and not self.stressed:
            self.stressed = True
            self.stress_caps = {
                name: {
                    s: (p.quantity * decimal(self.limits.stress_scale)).to_integral_value(
                        rounding=ROUND_FLOOR
                    )
                    for s, p in ledger.positions.items()
                }
                for name, ledger in self.ledgers.items()
            }
            self.logs.append(
                {
                    "at": now,
                    "kind": "portfolio_stress_cap",
                    "policy": "one_time_fractional_cap_hold_until_manual_reset",
                }
            )
        if daily <= -self.limits.maximum_daily_loss:
            self.daily_halt = True
        self.last_prices = prices

    def on_finish(self, prices):
        return reconcile(self.ledgers, self.master, prices)
