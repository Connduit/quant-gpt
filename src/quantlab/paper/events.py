"""Timestamped observable quotes/trades with explicit transport provenance."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from quantlab.backtesting.models import decimal
from quantlab.discovery.common import fingerprint


def instant(value):
    t = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(t, datetime) or t.tzinfo is None:
        raise ValueError("Aware timestamp required")
    return t.astimezone(UTC)


@dataclass(frozen=True)
class MarketEvent:
    instrument: str
    provider: str
    event_at: datetime
    received_at: datetime
    kind: str
    mode: str
    sequence: str
    bid: str | None = None
    ask: str | None = None
    bid_size: int = 0
    ask_size: int = 0
    price: str | None = None
    volume: int = 0
    session: str | None = None
    liquidity_basis: str = "displayed_quote"

    def __post_init__(self):
        for key in ("event_at", "received_at"):
            object.__setattr__(self, key, instant(getattr(self, key)))
        if self.received_at < self.event_at or not self.instrument or not self.provider:
            raise ValueError("Invalid market timestamps/provenance")
        if self.mode not in ("replay", "realtime", "delayed"):
            raise ValueError("Explicit data mode required")
        if self.liquidity_basis not in ("displayed_quote", "bar_volume_proxy"):
            raise ValueError("Explicit liquidity basis required")
        if self.kind not in ("quote", "trade", "heartbeat"):
            raise ValueError("Unsupported event type")
        if any(type(x) is not int or x < 0 for x in (self.bid_size, self.ask_size, self.volume)):
            raise ValueError("Nonnegative integer liquidity required")
        if self.kind == "quote":
            if (
                self.bid is None
                or self.ask is None
                or not 0 < decimal(self.bid) <= decimal(self.ask)
            ):
                raise ValueError("Invalid quote")
        if self.kind == "trade" and (self.price is None or decimal(self.price) <= 0):
            raise ValueError("Invalid trade")

    def payload(self):
        p = asdict(self)
        p["event_at"] = self.event_at.isoformat()
        p["received_at"] = self.received_at.isoformat()
        return p

    @property
    def identity(self):
        # Receive time is transport metadata, not a new market observation.
        p = self.payload()
        p.pop("received_at")
        return fingerprint(p)
