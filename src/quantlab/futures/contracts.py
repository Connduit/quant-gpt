"""Product specifications and individually expiring CME equity-index contracts."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal

from quantlab.backtesting.models import decimal


@dataclass(frozen=True)
class Product:
    symbol: str
    multiplier: Decimal
    tick_size: Decimal = Decimal(".25")
    exchange: str = "CME"
    currency: str = "USD"
    timezone: str = "America/Chicago"
    hours: str = "Globex, exchange calendar plus explicit maintenance/holiday overrides"
    settlement: str = "cash-settled; official settlement requires dated source prices"
    specification_source: str = "https://www.cmegroup.com/markets/equities.html"

    @property
    def tick_value(self):
        return self.multiplier * self.tick_size


PRODUCTS = {
    s: Product(s, Decimal(m)) for s, m in [("ES", "50"), ("MES", "5"), ("NQ", "20"), ("MNQ", "2")]
}


@dataclass(frozen=True)
class Contract:
    product: str
    identifier: str
    month: int
    year: int
    expiration: datetime
    last_trade: datetime
    metadata_source: str
    initial_margin: Decimal | None = None
    maintenance_margin: Decimal | None = None
    margin_as_of: str | None = None
    margin_source: str | None = None
    provider_symbols: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.product not in PRODUCTS or self.month not in (3, 6, 9, 12) or not self.identifier:
            raise ValueError("Supported quarterly CME equity-index contract required")
        if (
            self.expiration.tzinfo is None
            or self.last_trade.tzinfo is None
            or self.last_trade > self.expiration
        ):
            raise ValueError("Contract expiry/last-trade timestamps must be aware and ordered")
        if not self.metadata_source.strip():
            raise ValueError("Dated contract metadata provenance required")
        if self.expiration.year != self.year or self.expiration.month != self.month:
            raise ValueError("Contract month/year mismatch")
        for name in ("initial_margin", "maintenance_margin"):
            v = getattr(self, name)
            if v is not None:
                object.__setattr__(self, name, decimal(v))
                if getattr(self, name) <= 0:
                    raise ValueError("Margins must be positive")
        if self.initial_margin is not None:
            if not self.margin_source or not self.margin_as_of or self.maintenance_margin is None:
                raise ValueError("Dated initial/maintenance margin assumptions and source required")
            if self.maintenance_margin > self.initial_margin:
                raise ValueError("Maintenance exceeds initial margin")

    @property
    def spec(self):
        return PRODUCTS[self.product]

    def as_dict(self):
        return {
            **asdict(self),
            "specification": asdict(self.spec),
            "tick_value": self.spec.tick_value,
        }

    def validate_price(self, value):
        p = decimal(value)
        if p <= 0 or p % self.spec.tick_size:
            raise ValueError("Price must be positive and tick aligned")
        return p


def contract_from_dict(doc):
    values = {k: v for k, v in doc.items() if k not in ("specification", "tick_value")}
    for key in ("expiration", "last_trade"):
        values[key] = datetime.fromisoformat(str(values[key]))
    return Contract(**values)
