"""Deterministic long-only cash-equity risk rules and extensible contract sizing."""

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR

from quantlab.backtesting.models import decimal


@dataclass(frozen=True)
class RiskLimits:
    maximum_gross: float = 0.9
    maximum_net: float = 0.9
    maximum_position: float = 0.35
    maximum_sector: float = 0.6
    maximum_correlated: float = 0.7
    maximum_strategy: float = 0.6
    maximum_leverage: float = 1.0
    maximum_daily_loss: float = 0.03
    maximum_drawdown: float = 0.15
    maximum_strategy_drawdown: float = 0.2
    stress_scale: float = 0.5
    correlation_threshold: float = 0.8

    def __post_init__(self):
        for k in self.__dataclass_fields__:
            v = getattr(self, k)
            if not math.isfinite(v) or v <= 0:
                raise ValueError(f"{k} must be positive and finite")
        if self.maximum_leverage > 1 or self.maximum_gross > 1 or self.maximum_net > 1:
            raise ValueError("Equities adapter is cash-only; leverage > 1 is unsupported")
        if any(
            getattr(self, k) > 1
            for k in (
                "maximum_position",
                "maximum_sector",
                "maximum_correlated",
                "maximum_strategy",
                "maximum_daily_loss",
                "maximum_drawdown",
                "maximum_strategy_drawdown",
                "stress_scale",
                "correlation_threshold",
            )
        ):
            raise ValueError("Fractional limits must not exceed 1")


def size_position(
    equity,
    price,
    *,
    method="target_weight",
    fraction=0.1,
    volatility=None,
    atr=None,
    risk_fraction=0.01,
    multiplier=1,
    lot=1,
    buying_power=None,
    maximum_weight=0.35,
    cost_per_unit=0,
):
    e, p, m, lot_size = map(decimal, (equity, price, multiplier, lot))
    if (
        min(e, p, m, lot_size) <= 0
        or not 0 <= fraction <= 1
        or not 0 < maximum_weight <= 1
        or not 0 < risk_fraction <= 1
    ):
        raise ValueError("Invalid sizing input")
    weight = min(fraction, maximum_weight)
    if method in ("target_weight", "fixed_fractional"):
        budget = e * decimal(weight)
        units = budget / (p * m)
    elif method == "volatility_adjusted":
        if volatility is None or not math.isfinite(volatility) or volatility <= 0:
            raise ValueError("Positive known volatility required")
        units = e * decimal(min(maximum_weight, fraction * 0.15 / volatility)) / (p * m)
    elif method in ("atr", "risk_budget"):
        distance = atr if method == "atr" else p * decimal(volatility or 0)
        if distance is None or decimal(distance) <= 0:
            raise ValueError("Positive known risk distance required")
        units = min(
            e * decimal(risk_fraction) / (decimal(distance) * m),
            e * decimal(maximum_weight) / (p * m),
        )
    else:
        raise ValueError("Unknown sizing method")
    if buying_power is not None:
        units = min(units, decimal(buying_power) / (p * m + decimal(cost_per_unit)))
    return max(decimal(0), (units / lot_size).to_integral_value(rounding=ROUND_FLOOR) * lot_size)


def constrain(targets, prices, equity, limits, sectors=None, correlation_groups=()):
    """Scale entire target book; no greedy ticker priority or unobserved-price fills."""
    if equity <= 0:
        return {s: decimal(0) for s in targets}, ["nonpositive_equity"]
    targets = {s: decimal(q) for s, q in targets.items()}
    if any(q < 0 for q in targets.values()):
        raise ValueError("Equity portfolio is long-only")
    values = {s: float(q * prices[s] / equity) for s, q in targets.items()}
    reasons = []
    scales = {s: 1.0 for s in targets}
    for s, v in values.items():
        if v > limits.maximum_position:
            scales[s] = min(scales[s], limits.maximum_position / v)
            reasons.append(f"position:{s}")
    grouped = {}
    for s in values:
        grouped.setdefault((sectors or {}).get(s, "unknown"), []).append(s)
    for name, symbols in grouped.items():
        exposure = sum(values[s] for s in symbols)
        if exposure > limits.maximum_sector:
            for s in symbols:
                scales[s] = min(scales[s], limits.maximum_sector / exposure)
            reasons.append(f"sector:{name}")
    for group in correlation_groups:
        exposure = sum(values.get(s, 0) for s in group)
        if exposure > limits.maximum_correlated:
            for s in group:
                if s in scales:
                    scales[s] = min(scales[s], limits.maximum_correlated / exposure)
            reasons.append("correlated_exposure")
    total = sum(values.values())
    maximum = min(limits.maximum_gross, limits.maximum_net, limits.maximum_leverage)
    if total > maximum:
        for s in scales:
            scales[s] = min(scales[s], maximum / total)
        reasons.append("gross_net_leverage")
    return {
        s: (q * decimal(scales[s])).to_integral_value(rounding=ROUND_FLOOR)
        for s, q in targets.items()
    }, sorted(set(reasons))
