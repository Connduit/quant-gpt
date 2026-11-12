"""Long-only cash account; dividends are receivables from ex date until payment."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from quantlab.backtesting.models import ZERO, Fill, Side, decimal


@dataclass(frozen=True)
class Position:
    quantity: Decimal = ZERO
    average_cost: Decimal = ZERO  # includes allocated entry commission


@dataclass(frozen=True)
class PortfolioView:
    cash: Decimal
    positions: Mapping[str, Position]
    dividend_receivable: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    dividend_income: Decimal
    equity: Decimal


class Portfolio:
    def __init__(self, initial_cash: Decimal) -> None:
        self.initial_cash = decimal(initial_cash)
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.cash = self.initial_cash
        self.positions: dict[str, Position] = {}
        self.receivables: dict[int, Decimal] = {}
        self.realized_pnl = ZERO
        self.dividend_income = ZERO
        self.commissions = ZERO
        self.spread_cost = ZERO
        self.slippage_cost = ZERO

    def apply_fill(self, fill: Fill) -> Decimal:
        quantity, price, fee = fill.quantity, fill.price, fill.commission
        if quantity <= 0 or price <= 0 or fee < 0:
            raise ValueError("Invalid fill")
        position = self.positions.get(fill.symbol, Position())
        realized = ZERO
        if fill.side == Side.BUY:
            total = quantity * price + fee
            if total > self.cash:
                raise ValueError("insufficient_cash")
            new_quantity = position.quantity + quantity
            average = (position.quantity * position.average_cost + total) / new_quantity
            self.positions[fill.symbol] = Position(new_quantity, average)
            self.cash -= total
        elif fill.side == Side.SELL:
            if quantity > position.quantity:
                raise ValueError("insufficient_position")
            proceeds = quantity * price - fee
            if self.cash + proceeds < 0:
                raise ValueError("insufficient_cash_for_commission")
            realized = (price - position.average_cost) * quantity - fee
            remaining = position.quantity - quantity
            self.positions[fill.symbol] = Position(
                remaining, position.average_cost if remaining else ZERO
            )
            self.cash += proceeds
            self.realized_pnl += realized
        else:
            raise ValueError("Unsupported fill side")
        self.commissions += fee
        self.spread_cost += fill.spread_cost
        self.slippage_cost += fill.slippage_cost
        return realized

    def split(self, symbol: str, ratio: Decimal) -> None:
        if ratio <= 0:
            raise ValueError("Split ratio must be positive")
        position = self.positions.get(symbol, Position())
        if position.quantity:
            self.positions[symbol] = Position(
                position.quantity * ratio, position.average_cost / ratio
            )

    def accrue_dividend(self, action_id: int, symbol: str, amount: Decimal) -> Decimal:
        if action_id in self.receivables:
            raise ValueError("Duplicate dividend entitlement")
        entitlement = self.positions.get(symbol, Position()).quantity * amount
        self.receivables[action_id] = entitlement
        self.dividend_income += entitlement
        return entitlement

    def pay_dividend(self, action_id: int) -> Decimal:
        amount = self.receivables.pop(action_id, ZERO)
        self.cash += amount
        return amount

    def view(self, prices: Mapping[str, Decimal]) -> PortfolioView:
        market_value = ZERO
        unrealized = ZERO
        for symbol, position in self.positions.items():
            if position.quantity:
                if symbol not in prices:
                    raise ValueError(f"No available valuation price for {symbol}")
                market_value += position.quantity * prices[symbol]
                unrealized += position.quantity * (prices[symbol] - position.average_cost)
        receivable = sum(self.receivables.values(), ZERO)
        equity = self.cash + market_value + receivable
        expected = self.initial_cash + self.realized_pnl + unrealized + self.dividend_income
        if abs(equity - expected) > max(Decimal("1e-18"), abs(equity) * Decimal("1e-24")):
            raise ArithmeticError("Portfolio accounting identity failed")
        return PortfolioView(
            self.cash,
            MappingProxyType(self.positions.copy()),
            receivable,
            self.realized_pnl,
            unrealized,
            self.dividend_income,
            equity,
        )
