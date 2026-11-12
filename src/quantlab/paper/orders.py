"""Authoritative transitions shared by simulation and broker control planes."""

from dataclasses import asdict, dataclass

from quantlab.backtesting.models import decimal
from quantlab.paper.events import instant

TERMINAL = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
TRANSITIONS = {
    "CREATED": {"PENDING", "REJECTED"},
    "PENDING": {"ACCEPTED", "REJECTED", "CANCELLED"},
    "ACCEPTED": {"PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED", "REJECTED"},
    "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED", "REJECTED"},
}


@dataclass
class PaperOrder:
    client_id: str
    strategy: str
    instrument: str
    quantity: int
    submitted_at: str
    order_type: str = "market"
    limit: str | None = None
    stop: str | None = None
    tif: str = "day"
    state: str = "CREATED"
    filled: int = 0
    triggered_at: str | None = None
    reason: str | None = None

    def __post_init__(self):
        instant(self.submitted_at)
        if (
            not self.client_id
            or not self.strategy
            or type(self.quantity) is not int
            or not self.quantity
        ):
            raise ValueError("Stable ID, strategy and signed whole units required")
        if self.order_type not in ("market", "limit", "stop", "stop_limit") or self.tif not in (
            "day",
            "gtc",
        ):
            raise ValueError("Unsupported order type/time in force")
        for field in ("limit", "stop"):
            required = self.order_type in (field, "stop_limit")
            if required and (getattr(self, field) is None or decimal(getattr(self, field)) <= 0):
                raise ValueError(f"Positive {field} required")
        if self.state not in set(TRANSITIONS) | TERMINAL:
            raise ValueError("Invalid order state")
        if not 0 <= self.filled <= abs(self.quantity):
            raise ValueError("Invalid filled quantity")

    @property
    def remaining(self):
        return (abs(self.quantity) - self.filled) * (1 if self.quantity > 0 else -1)

    def transition(self, state, reason=None):
        if state not in TRANSITIONS.get(self.state, set()):
            raise ValueError(f"Invalid transition {self.state} -> {state}")
        self.state = state
        self.reason = reason

    def payload(self):
        return asdict(self)
