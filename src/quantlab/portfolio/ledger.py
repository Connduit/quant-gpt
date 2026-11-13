"""Strategy attribution claims; authoritative buying power remains the shared account."""

from dataclasses import replace

from quantlab.backtesting.models import ZERO, Side, decimal
from quantlab.backtesting.portfolio import Portfolio, Position


class AttributionLedger(Portfolio):
    def apply_fill(self, fill):
        # Virtual cash can borrow internally; it is never an independent buying-power pool.
        old_cash = self.cash
        needed = fill.commission + (fill.quantity * fill.price if fill.side == Side.BUY else ZERO)
        funded = max(old_cash, needed)
        self.cash = funded
        try:
            result = super().apply_fill(fill)
        except BaseException:
            self.cash = old_cash
            raise
        self.cash = old_cash + (self.cash - funded)
        return result


def distribute_fill(fill, quantities):
    total = sum(quantities.values(), ZERO)
    if total != fill.quantity or total <= 0:
        raise ArithmeticError("Fill attribution must equal actual quantity")
    remaining = {
        k: getattr(fill, k)
        for k in ("commission", "spread_cost", "slippage_cost", "market_impact_cost")
    }
    result = {}
    entries = [(s, q) for s, q in sorted(quantities.items()) if q]
    for i, (name, quantity) in enumerate(entries):
        costs = {
            k: remaining[k] if i == len(entries) - 1 else getattr(fill, k) * quantity / total
            for k in remaining
        }
        for k, v in costs.items():
            remaining[k] -= v
        result[name] = replace(fill, quantity=quantity, **costs)
    return result


def reconcile(ledgers, master, prices):
    views = [p.view(prices) for p in ledgers.values()]
    actual = master.view(prices)
    checks = {
        "cash": sum((v.cash for v in views), ZERO) - actual.cash,
        "receivables": sum((v.dividend_receivable for v in views), ZERO)
        - actual.dividend_receivable,
        "equity": sum((v.equity for v in views), ZERO) - actual.equity,
    }
    for symbol in prices:
        checks[f"quantity:{symbol}"] = (
            sum((v.positions.get(symbol, Position()).quantity for v in views), ZERO)
            - actual.positions.get(symbol, Position()).quantity
        )
    tolerance = max(decimal("1e-18"), abs(actual.equity) * decimal("1e-24"))
    if any(abs(v) > tolerance for v in checks.values()):
        raise ArithmeticError(f"Attribution mismatch: {checks}")
    return checks
