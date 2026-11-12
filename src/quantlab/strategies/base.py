from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from quantlab.backtesting.models import Bar, decimal
from quantlab.backtesting.portfolio import PortfolioView


@dataclass(frozen=True)
class Signal:
    """Target long share quantity; an execution adapter decides how to reach it."""

    symbol: str
    target_quantity: Decimal

    def __post_init__(self) -> None:
        quantity = decimal(self.target_quantity)
        if quantity < 0:
            raise ValueError("Short positions are not supported")
        object.__setattr__(self, "target_quantity", quantity)


@dataclass(frozen=True)
class StrategyContext:
    now: datetime
    bar: Bar
    history: tuple[Bar, ...]  # only bars available by now, rebased for known splits
    portfolio: PortfolioView
    histories: Mapping[str, tuple[Bar, ...]] | None = None
    prices: Mapping[str, Decimal] | None = None


class Strategy(Protocol):
    def on_bar(self, context: StrategyContext) -> tuple[Signal, ...]: ...
