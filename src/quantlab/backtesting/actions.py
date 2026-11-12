"""Explicit split and cash-dividend ledgers, with declared coverage and provenance."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from quantlab.backtesting.models import decimal


@dataclass(frozen=True)
class Split:
    date: date
    ratio: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "ratio", decimal(self.ratio))
        if self.ratio <= 0:
            raise ValueError("Split ratio must be positive (new shares per old share)")


@dataclass(frozen=True)
class Dividend:
    ex_date: date
    pay_date: date | None
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", decimal(self.amount))
        if self.amount < 0 or self.pay_date is not None and self.pay_date < self.ex_date:
            raise ValueError("Dividend must be nonnegative with pay date on/after ex date")


@dataclass(frozen=True)
class CorporateActions:
    symbol: str
    coverage_start: date
    coverage_end: date
    source: str
    splits: tuple[Split, ...] = ()
    dividends: tuple[Dividend, ...] = ()
    complete: bool = True
    coverage_method: str = "provided_events"
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip() or self.coverage_start > self.coverage_end:
            raise ValueError("Corporate actions require a source and valid coverage dates")
        if self.coverage_method not in ("provided_events", "factor_file_proxy"):
            raise ValueError("Unsupported action coverage method")
        if self.complete is not True and not (
            self.complete is False
            and self.coverage_method == "factor_file_proxy"
            and self.limitations
        ):
            raise ValueError("Corporate-action coverage must be explicitly complete")
        if self.coverage_method == "factor_file_proxy" and self.complete:
            raise ValueError(
                "Factor-file proxies cannot claim independently complete event coverage"
            )
        if self.coverage_method == "provided_events" and any(
            d.pay_date is None for d in self.dividends
        ):
            raise ValueError("Unknown pay dates require an explicit factor-file alternative")
        dates = [a.date for a in self.splits]
        dividend_keys = [(a.ex_date, a.pay_date, a.amount) for a in self.dividends]
        if len(set(dates)) != len(dates) or len(set(dividend_keys)) != len(dividend_keys):
            raise ValueError("Duplicate corporate actions")
        effective = dates + [a.ex_date for a in self.dividends]
        if any(not self.coverage_start <= day <= self.coverage_end for day in effective):
            raise ValueError("Corporate action is outside declared coverage")

    @classmethod
    def load(cls, path: Path) -> "CorporateActions":
        values = json.loads(path.read_text(), parse_float=Decimal)
        expected = {
            "symbol",
            "coverage_start",
            "coverage_end",
            "source",
            "complete",
            "splits",
            "dividends",
        }
        if not expected <= set(values) or set(values) - expected - {
            "coverage_method",
            "limitations",
        }:
            raise ValueError(f"Action ledger must contain exactly: {', '.join(sorted(expected))}")
        try:
            if any(set(a) != {"date", "ratio"} for a in values["splits"]):
                raise ValueError("Split fields must be exactly date and ratio")
            if any(set(a) != {"ex_date", "pay_date", "amount"} for a in values["dividends"]):
                raise ValueError("Dividend fields must be exactly ex_date, pay_date and amount")
            return cls(
                values["symbol"],
                date.fromisoformat(values["coverage_start"]),
                date.fromisoformat(values["coverage_end"]),
                values["source"],
                tuple(
                    Split(date.fromisoformat(a["date"]), decimal(a["ratio"]))
                    for a in values["splits"]
                ),
                tuple(
                    Dividend(
                        date.fromisoformat(a["ex_date"]),
                        date.fromisoformat(a["pay_date"]) if a["pay_date"] is not None else None,
                        decimal(a["amount"]),
                    )
                    for a in values["dividends"]
                ),
                values["complete"],
                values.get("coverage_method", "provided_events"),
                tuple(values.get("limitations", [])),
            )
        except KeyError as exc:
            raise ValueError(f"Missing corporate-action field: {exc}") from exc
