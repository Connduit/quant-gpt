"""Execution and accounting values. Monetary arithmetic never uses binary floats."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

ZERO = Decimal("0")


def decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a monetary or quantity value")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("Monetary and quantity values must be finite")
    return result


@dataclass(frozen=True)
class EquityInstrument:
    symbol: str
    currency: str = "USD"
    calendar: str = "XNYS"


@dataclass(frozen=True)
class Bar:
    symbol: str
    session_date: date
    open_time: datetime
    close_time: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | Decimal


@dataclass(frozen=True)
class OpeningEvent:
    """Execution policies see the opening print, never the completed daily bar."""

    symbol: str
    timestamp: datetime
    price: Decimal


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class Order:
    order_id: int
    symbol: str
    side: Side
    quantity: Decimal
    submitted_at: datetime
    original_quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    status: OrderStatus = OrderStatus.PENDING
    resolved_at: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Fill:
    order_id: int
    symbol: str
    side: Side
    quantity: Decimal
    timestamp: datetime
    reference_price: Decimal
    price: Decimal
    commission: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal


@dataclass(frozen=True)
class Costs:
    commission_per_share: Decimal = Decimal("0.005")
    commission_fixed: Decimal = ZERO
    minimum_commission: Decimal = ZERO
    slippage_bps: Decimal = Decimal("1")
    spread_bps: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = decimal(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
            object.__setattr__(self, name, value)
        if self.slippage_bps + self.spread_bps / 2 >= 10000:
            raise ValueError("Execution price impact must be below 100%")

    def fill(self, order: Order, opening: OpeningEvent) -> Fill:
        if order.order_type != OrderType.MARKET:
            raise ValueError("Only market orders are implemented")
        if order.submitted_at >= opening.timestamp:
            raise ValueError("Orders must exist strictly before the execution open")
        if order.symbol != opening.symbol or order.quantity <= 0:
            raise ValueError("Invalid order for this bar")
        spread = opening.price * self.spread_bps / 20000
        slippage = opening.price * self.slippage_bps / 10000
        direction = 1 if order.side == Side.BUY else -1
        price = opening.price + direction * (spread + slippage)
        commission = max(
            self.minimum_commission,
            self.commission_fixed + order.quantity * self.commission_per_share,
        )
        return Fill(
            order.order_id,
            order.symbol,
            order.side,
            order.quantity,
            opening.timestamp,
            opening.price,
            price,
            commission,
            spread * order.quantity,
            slippage * order.quantity,
        )
