"""Contract-aware pre-trade futures risk uses portfolio sizing and generic limit rules."""

from dataclasses import dataclass

from quantlab.backtesting.models import decimal
from quantlab.portfolio.risk import limit_breaches


@dataclass(frozen=True)
class FuturesRisk:
    maximum_contracts: int = 1
    maximum_notional: float = 200000
    maximum_margin_utilization: float = 0.5
    maximum_leverage: float = 2
    maximum_daily_loss: float = 0.03
    maximum_drawdown: float = 0.15
    maximum_strategy_drawdown: float = 0.15

    def __post_init__(self):
        import math

        if type(self.maximum_contracts) is not int or self.maximum_contracts < 1:
            raise ValueError("Positive whole contract cap required")
        for k in self.__dataclass_fields__:
            value = getattr(self, k)
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Risk limits must be positive and finite")
        if (
            self.maximum_margin_utilization > 1
            or self.maximum_daily_loss > 1
            or self.maximum_drawdown > 1
            or self.maximum_strategy_drawdown > 1
        ):
            raise ValueError("Fractional risk bounds must not exceed 1")

    def approve(self, ledger, identifier, target, prices, *, fees=0, halted=False):
        if type(target) is not int:
            raise ValueError("Whole target contracts required")
        held = ledger.positions.get(identifier)
        current = held.quantity if held else 0
        reducing = abs(target) <= abs(current) and target * current >= 0
        if reducing:
            return target, []
        if halted:
            return current, ["trading_suspended"]
        view = ledger.view(prices)
        equity = view["equity"] - decimal(fees)
        contract = ledger.contracts[identifier]
        if contract.initial_margin is None:
            raise ValueError("Explicit margin metadata required")
        reasons = []
        others = sum(
            abs(p.quantity)
            for k, p in ledger.positions.items()
            if k != identifier and ledger.contracts[k].product == contract.product
        )
        cap = max(0, self.maximum_contracts - others)
        approved = max(-cap, min(cap, target))
        if approved != target:
            reasons.append("contract_count")
        while abs(approved) > 0:
            gross = (
                view["gross_notional"]
                - abs(current) * prices[identifier] * contract.spec.multiplier
                + abs(approved) * prices[identifier] * contract.spec.multiplier
            )
            margin = (
                view["initial_margin"]
                - abs(current) * contract.initial_margin
                + abs(approved) * contract.initial_margin
            )
            observed = {
                "notional": float(gross),
                "margin_utilization": float(margin / equity) if equity > 0 else float("inf"),
                "leverage": float(gross / equity) if equity > 0 else float("inf"),
            }
            breaches = limit_breaches(
                observed,
                {
                    "notional": self.maximum_notional,
                    "margin_utilization": self.maximum_margin_utilization,
                    "leverage": self.maximum_leverage,
                },
            )
            if not breaches:
                break
            reasons += breaches
            approved -= 1 if approved > 0 else -1
        if abs(approved) < abs(current) and approved * current >= 0:
            # A reversal that cannot fund the new side may still close the existing position.
            approved = 0
        return approved, sorted(set(reasons))
