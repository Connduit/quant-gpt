"""Futures variation-margin cash and lifetime trade attribution; no notional cash debit."""

from dataclasses import dataclass

from quantlab.backtesting.models import ZERO, decimal


@dataclass
class FuturesPosition:
    quantity: int = 0
    basis: object = ZERO
    entry: object = ZERO
    entry_fee: object = ZERO
    opened_at: object = None


class FuturesLedger:
    def __init__(self, initial_cash, contracts):
        self.initial_cash = decimal(initial_cash)
        if self.initial_cash <= 0:
            raise ValueError("Positive initial futures equity required")
        self.cash = self.initial_cash
        self.contracts = contracts
        self.positions = {}
        self.fees = ZERO
        self.execution_cost = ZERO
        self.settlement_variation = ZERO
        self.realized_gross = ZERO
        self.trades = []
        self.settlements = []

    def fill(
        self,
        identifier,
        signed_quantity,
        price,
        *,
        fee=0,
        reference_price=None,
        timestamp=None,
        reason="strategy",
    ):
        if type(signed_quantity) is not int or not signed_quantity:
            raise ValueError("Whole signed contracts required")
        contract = self.contracts[identifier]
        price = contract.validate_price(price)
        fee = decimal(fee)
        if fee < 0:
            raise ValueError("Fees cannot be negative")
        p = self.positions.setdefault(identifier, FuturesPosition())
        old = p.quantity
        new = old + signed_quantity
        closing = min(abs(old), abs(signed_quantity)) if old * signed_quantity < 0 else 0
        direction = 1 if old > 0 else -1
        lifetime_gross = (
            (price - p.entry) * contract.spec.multiplier * closing * direction if closing else ZERO
        )
        variation = (
            (price - p.basis) * contract.spec.multiplier * closing * direction if closing else ZERO
        )
        cost_per = fee / abs(signed_quantity)
        net_closed = lifetime_gross - (p.entry_fee + cost_per) * closing
        self.cash += variation - fee
        self.fees += fee
        self.realized_gross += lifetime_gross
        if reference_price is not None:
            self.execution_cost += (
                (price - decimal(reference_price))
                * (1 if signed_quantity > 0 else -1)
                * contract.spec.multiplier
                * abs(signed_quantity)
            )
        if old == 0:
            p.opened_at = timestamp
        if old == 0 or old * signed_quantity > 0:
            total = abs(new)
            p.basis = (p.basis * abs(old) + price * abs(signed_quantity)) / total
            p.entry = (p.entry * abs(old) + price * abs(signed_quantity)) / total
            p.entry_fee = (p.entry_fee * abs(old) + fee) / total
        elif old * new < 0:
            p.opened_at = timestamp
            p.basis = p.entry = price
            p.entry_fee = cost_per
        elif not new:
            p.opened_at = None
            p.basis = p.entry = p.entry_fee = ZERO
        p.quantity = new
        trade = {
            "timestamp": timestamp,
            "contract": identifier,
            "product": contract.product,
            "signed_quantity": signed_quantity,
            "price": price,
            "reference_price": reference_price,
            "fees": fee,
            "closed_contracts": closing,
            "realized_gross": lifetime_gross,
            "closed_net_pnl": net_closed,
            "cash_variation": variation,
            "notional": price * contract.spec.multiplier * abs(signed_quantity),
            "reason": reason,
        }
        self.trades.append(trade)
        return trade

    def settle(self, identifier, price, *, timestamp, source):
        if not source:
            raise ValueError("Settlement price provenance required")
        contract = self.contracts[identifier]
        price = contract.validate_price(price)
        p = self.positions.get(identifier, FuturesPosition())
        variation = (price - p.basis) * contract.spec.multiplier * p.quantity
        self.cash += variation
        self.settlement_variation += variation
        if p.quantity:
            p.basis = price
        self.settlements.append(
            {
                "timestamp": timestamp,
                "contract": identifier,
                "price": price,
                "variation": variation,
                "source": source,
            }
        )
        return variation

    def view(self, prices):
        unreal = lifetime_unreal = gross = net = initial = maintenance = ZERO
        for identifier, p in self.positions.items():
            if not p.quantity:
                continue
            c = self.contracts[identifier]
            if identifier not in prices:
                raise ValueError("Missing contract valuation price")
            price = decimal(prices[identifier])
            m = c.spec.multiplier
            unreal += (price - p.basis) * m * p.quantity
            lifetime_unreal += (price - p.entry) * m * p.quantity
            gross += abs(p.quantity) * price * m
            net += p.quantity * price * m
            if c.initial_margin is None or c.maintenance_margin is None:
                raise ValueError("Explicit dated margin requirements/assumptions required")
            initial += abs(p.quantity) * c.initial_margin
            maintenance += abs(p.quantity) * c.maintenance_margin
        equity = self.cash + unreal
        expected = self.initial_cash + self.realized_gross + lifetime_unreal - self.fees
        if abs(equity - expected) > max(decimal("1e-18"), abs(equity) * decimal("1e-24")):
            raise ArithmeticError("Futures accounting identity failed")
        return {
            "cash": self.cash,
            "equity": equity,
            "unrealized_since_settlement": unreal,
            "lifetime_unrealized": lifetime_unreal,
            "gross_notional": gross,
            "net_notional": net,
            "initial_margin": initial,
            "maintenance_margin": maintenance,
            "available_buying_power": equity - initial,
            "margin_utilization": initial / equity if equity > 0 else None,
            "maintenance_breach": equity < maintenance,
        }
