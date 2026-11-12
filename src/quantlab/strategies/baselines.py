from dataclasses import dataclass
from decimal import Decimal

from quantlab.backtesting.models import ZERO, decimal
from quantlab.backtesting.portfolio import Position
from quantlab.strategies.base import Signal, StrategyContext


def validate(lookback: int, shares: Decimal, threshold: Decimal) -> None:
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
        raise ValueError("lookback must be a positive integer")
    if shares <= 0 or not ZERO <= threshold < 1:
        raise ValueError("shares must be positive and threshold must be in [0, 1)")


@dataclass(frozen=True)
class BuyAndHold:
    shares: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        object.__setattr__(self, "shares", decimal(self.shares))
        validate(1, self.shares, ZERO)

    def on_bar(self, context: StrategyContext) -> tuple[Signal, ...]:
        if len(context.history) == 1:
            return (Signal(context.bar.symbol, self.shares),)
        return ()


@dataclass(frozen=True)
class Momentum:
    lookback: int = 20  # return over this many sessions needs lookback+1 closes
    shares: Decimal = Decimal("10")
    threshold: Decimal = ZERO

    def __post_init__(self) -> None:
        object.__setattr__(self, "shares", decimal(self.shares))
        object.__setattr__(self, "threshold", decimal(self.threshold))
        validate(self.lookback, self.shares, self.threshold)

    def on_bar(self, context: StrategyContext) -> tuple[Signal, ...]:
        if len(context.history) <= self.lookback:
            return ()
        change = context.bar.close / context.history[-self.lookback - 1].close - 1
        quantity = context.portfolio.positions.get(context.bar.symbol, Position()).quantity
        if change > self.threshold and not quantity:
            return (Signal(context.bar.symbol, self.shares),)
        if change <= self.threshold and quantity:
            return (Signal(context.bar.symbol, ZERO),)
        return ()


@dataclass(frozen=True)
class MeanReversion:
    lookback: int = 20
    shares: Decimal = Decimal("10")
    threshold: Decimal = Decimal("0.02")

    def __post_init__(self) -> None:
        object.__setattr__(self, "shares", decimal(self.shares))
        object.__setattr__(self, "threshold", decimal(self.threshold))
        validate(self.lookback, self.shares, self.threshold)
        if self.lookback < 2:
            raise ValueError("Mean reversion requires at least two sessions")

    def on_bar(self, context: StrategyContext) -> tuple[Signal, ...]:
        if len(context.history) < self.lookback:
            return ()
        mean = sum((b.close for b in context.history[-self.lookback :]), ZERO) / self.lookback
        quantity = context.portfolio.positions.get(context.bar.symbol, Position()).quantity
        if context.bar.close < mean * (1 - self.threshold) and not quantity:
            return (Signal(context.bar.symbol, self.shares),)
        if context.bar.close >= mean and quantity:
            return (Signal(context.bar.symbol, ZERO),)
        return ()
