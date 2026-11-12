import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol


@dataclass(frozen=True)
class DataRequest:
    symbol: str
    start: date
    end: date

    def __post_init__(self) -> None:
        symbol = self.symbol.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol):
            raise ValueError("Expected a US equity ticker (letters, digits, dots or hyphens)")
        if self.start > self.end:
            raise ValueError("start must be on or before end (both dates are inclusive)")
        if self.end >= datetime.now(UTC).date():
            raise ValueError("Only completed historical dates before today are supported")
        object.__setattr__(self, "symbol", symbol)

    def as_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass(frozen=True)
class Download:
    raw: bytes
    source: str
    price_basis: str
    synthetic: bool


class ProviderError(ValueError):
    """The source did not supply usable market data."""


class HistoricalProvider(Protocol):
    name: str

    def fetch(self, request: DataRequest) -> Download: ...
