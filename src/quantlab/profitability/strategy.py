"""Causal long-only prediction adapter with explicit targets and pre-fill risk limits."""

import math
from dataclasses import asdict, dataclass, replace
from decimal import ROUND_FLOOR
from zoneinfo import ZoneInfo

from quantlab.backtesting.models import Side, decimal
from quantlab.portfolio.risk import RiskLimits, constrain
from quantlab.strategies.base import Signal


@dataclass(frozen=True)
class StrategyPolicy:
    top_n: int = 2
    minimum_prediction: float | None = 0.0
    probability_threshold: float | None = 0.55
    volatility_adjusted: bool = False
    rebalance_sessions: int = 5
    holding_sessions: int = 20
    cash_allocation: float = 0.2
    maximum_position_weight: float = 0.4
    maximum_drawdown: float = 0.2
    maximum_daily_loss: float = 0.05
    minimum_dollar_volume: float = 1000000
    whole_shares: bool = True

    def __post_init__(self):
        for key in ("top_n", "rebalance_sessions", "holding_sessions"):
            if type(getattr(self, key)) is not int or not 1 <= getattr(self, key) <= 252:
                raise ValueError(f"{key} must be a positive bounded session count")
        for key in ("maximum_position_weight", "maximum_drawdown", "maximum_daily_loss"):
            if not math.isfinite(getattr(self, key)) or not 0 < getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in (0,1]")
        if not 0 <= self.cash_allocation < 1 or not math.isfinite(self.minimum_dollar_volume):
            raise ValueError("Invalid cash allocation or liquidity limit")
        if self.minimum_dollar_volume < 0:
            raise ValueError("Liquidity limit must be nonnegative")
        if self.minimum_prediction is not None and not math.isfinite(self.minimum_prediction):
            raise ValueError("Prediction threshold must be finite")
        if self.probability_threshold is not None and not 0 <= self.probability_threshold <= 1:
            raise ValueError("Probability threshold must be in [0,1]")
        if type(self.whole_shares) is not bool or type(self.volatility_adjusted) is not bool:
            raise ValueError("Strategy switches must be boolean")


def verify_prediction_rows(rows):
    seen = set()
    for row in rows:
        clocks = [
            row[k]
            for k in ("train_label_max", "model_available_at", "prediction_at", "execution_at")
        ]
        if any(t.tzinfo is None or t.utcoffset().total_seconds() != 0 for t in clocks):
            raise ValueError("Prediction clocks must be timezone-aware UTC")
        if not clocks[0] < clocks[1] <= clocks[2] < clocks[3]:
            raise ValueError(
                "Look-ahead: training labels, model, signal and execution are misaligned"
            )
        key = row["symbol"], row["session_date"]
        if key in seen:
            raise ValueError("Duplicate prediction for a stock/session")
        seen.add(key)
        for name in (
            "prediction",
            "momentum",
            "ma_distance_long",
            "realized_vol_long",
            "dollar_volume_ma",
        ):
            if not math.isfinite(row[name]):
                raise ValueError("Prediction scores and known features must be finite")
        if row["realized_vol_long"] < 0 or row["dollar_volume_ma"] < 0:
            raise ValueError("Known volatility and liquidity must be nonnegative")


class PredictionStrategy:
    def __init__(self, rows, universe, policy=None, mode="ml", *, probability=False):
        if mode not in ("ml", "spy_buy_hold", "equal_weight", "momentum", "mean_reversion", "cash"):
            raise ValueError("Unsupported executable strategy")
        policy = policy or StrategyPolicy()
        verify_prediction_rows(rows)
        if probability and any(not 0 <= r["prediction"] <= 1 for r in rows):
            raise ValueError("Classifier outputs must be probabilities")
        self.rows, self.universe, self.policy, self.mode, self.probability = (
            rows,
            universe,
            policy,
            mode,
            probability,
        )
        self.book = {}
        for row in rows:
            self.book.setdefault(row["session_date"], []).append(row)
        self.seen, self.opened, self.decisions = set(), {}, []
        self.stopped = False
        self._last_rebalance = None

    def spec(self):
        return {
            "mode": self.mode,
            "policy": asdict(self.policy),
            "probability": self.probability,
            "signal_rules": "available OOS scores; long-only targets; no same-bar execution",
            "decisions": self.decisions,
        }

    def on_start(self, portfolio, feeds, config):
        self.portfolio, self.config = portfolio, config
        self.calendar = [b.session_date for b in next(iter(feeds.values())).bars]
        self.indices = {d: i for i, d in enumerate(self.calendar)}
        self.peak = self.previous_close = portfolio.initial_cash
        self.limits = RiskLimits(
            maximum_gross=1 - self.policy.cash_allocation,
            maximum_net=1 - self.policy.cash_allocation,
            maximum_position=self.policy.maximum_position_weight,
            maximum_sector=1,
            maximum_strategy=1,
            maximum_drawdown=self.policy.maximum_drawdown,
            maximum_daily_loss=self.policy.maximum_daily_loss,
        )

    def on_close(self, now, bars, view):
        self.peak = max(self.peak, view.equity)
        if view.equity / self.peak - 1 <= -decimal(
            self.policy.maximum_drawdown
        ) or view.equity / self.previous_close - 1 <= -decimal(self.policy.maximum_daily_loss):
            self.stopped = True  # Stop persists; exits wait for the next market open.
        self.previous_close = view.equity

    def on_fill(self, fill):
        if fill.side == Side.BUY and fill.symbol not in self.opened:
            self.opened[fill.symbol] = self.indices[
                fill.timestamp.astimezone(ZoneInfo("America/New_York")).date()
            ]
        if fill.side == Side.SELL and not self.portfolio.positions[fill.symbol].quantity:
            self.opened.pop(fill.symbol, None)

    def before_fill(self, order, opening, prices):
        if order.side == Side.SELL:
            return order.quantity
        if self.stopped:
            return decimal(0)
        view = self.portfolio.view(prices)
        gross = sum(p.quantity * prices[s] for s, p in view.positions.items())
        position = view.positions.get(order.symbol)
        value = position.quantity * opening.price if position else decimal(0)
        room = min(
            view.equity * decimal(1 - self.policy.cash_allocation) - gross,
            view.equity * decimal(self.policy.maximum_position_weight) - value,
        )
        unit_fill = self.config.costs.fill(replace(order, quantity=decimal(1)), opening)
        costs = self.config.costs
        affordable = min(
            (view.cash - costs.commission_fixed) / (unit_fill.price + costs.commission_per_share),
            (view.cash - costs.minimum_commission) / unit_fill.price,
        )
        quantity = max(decimal(0), min(order.quantity, room / opening.price, affordable))
        return (
            quantity.to_integral_value(rounding=ROUND_FLOOR)
            if self.policy.whole_shares
            else quantity
        )

    def on_bar(self, context):
        day = context.bar.session_date
        if day in self.seen or not all(
            h and h[-1].session_date == day for h in context.histories.values()
        ):
            return ()
        index = self.indices[day]
        batch = self.book.get(day, [])
        if batch and context.now < max(r["prediction_at"] for r in batch):
            return ()
        self.seen.add(day)
        expired = {
            s
            for s, entry in self.opened.items()
            if index - entry >= self.policy.holding_sessions - 1
        }
        if self.mode == "spy_buy_hold":
            expired = set()
        first = bool(batch) and self._last_rebalance is None
        rebalance = bool(batch) and (
            first or index - self._last_rebalance >= self.policy.rebalance_sessions
        )
        targets = {s: p.quantity for s, p in context.portfolio.positions.items() if p.quantity}
        for symbol in expired:
            targets[symbol] = decimal(0)
        if self.stopped or self.mode == "cash":
            targets = {s: decimal(0) for s in self.universe + ("SPY",)}
        elif rebalance and (self.mode != "spy_buy_hold" or first):
            if any(context.now >= r["execution_at"] for r in batch):
                raise ValueError("Signal became available too late for its declared execution")
            self._last_rebalance = index
            candidates = [
                r
                for r in batch
                if r["dollar_volume_ma"] >= self.policy.minimum_dollar_volume
                and r["symbol"] not in expired
            ]
            if self.mode == "ml":
                threshold = (
                    self.policy.probability_threshold
                    if self.probability
                    else self.policy.minimum_prediction
                )
                if threshold is not None:
                    candidates = [r for r in candidates if r["prediction"] >= threshold]
            if self.mode == "momentum":
                candidates = [r for r in candidates if r["momentum"] > 0]
            if self.mode == "mean_reversion":
                candidates = [r for r in candidates if r["ma_distance_long"] < 0]

            def score(row):
                value = (
                    row["momentum"]
                    if self.mode == "momentum"
                    else (
                        -row["ma_distance_long"]
                        if self.mode == "mean_reversion"
                        else row["prediction"]
                    )
                )
                return (
                    value / max(row["realized_vol_long"], 1e-6)
                    if (self.mode == "ml" and self.policy.volatility_adjusted)
                    else value
                )

            selected = sorted(candidates, key=lambda r: (-score(r), r["symbol"]))
            names = [r["symbol"] for r in selected[: self.policy.top_n]]
            if self.mode == "equal_weight":
                names = sorted(self.universe)
            if self.mode == "spy_buy_hold":
                names = ["SPY"]
            weight = (
                min(
                    self.policy.maximum_position_weight,
                    (1 - self.policy.cash_allocation) / len(names),
                )
                if names
                else 0
            )
            targets = {s: decimal(0) for s in self.universe + ("SPY",)}
            for symbol in names:
                targets[symbol] = (
                    context.portfolio.equity * decimal(weight) / context.prices[symbol]
                )
            targets, _ = constrain(
                targets,
                context.prices,
                context.portfolio.equity,
                self.limits,
                whole_shares=self.policy.whole_shares,
            )
        elif not expired:
            return ()
        signals = []
        for symbol, quantity in sorted(targets.items()):
            if self.policy.whole_shares:
                quantity = quantity.to_integral_value(rounding=ROUND_FLOOR)
            before = context.portfolio.positions.get(symbol)
            current = before.quantity if before else decimal(0)
            decision = (
                "HOLD"
                if quantity == current
                else "EXIT"
                if not quantity
                else "BUY"
                if quantity > current
                else "SELL"
            )
            self.decisions.append(
                {
                    "timestamp": context.now,
                    "symbol": symbol,
                    "decision": decision,
                    "target_quantity": quantity,
                }
            )
            signals.append(Signal(symbol, quantity))
        return tuple(signals)
