"""One funded master account backed by the existing equity and futures ledgers."""

from quantlab.backtesting.models import Fill, Side, decimal
from quantlab.backtesting.portfolio import Portfolio
from quantlab.futures.accounting import FuturesLedger


class Account:
    def __init__(self, capital, contracts):
        self.stocks = Portfolio(decimal(capital))
        self.futures = FuturesLedger(0, contracts, unfunded_component=True)
        self.prices = {}
        self.fills = []
        self.transfers = []

    def quantity(self, symbol):
        if symbol in self.futures.contracts:
            p = self.futures.positions.get(symbol)
        else:
            p = self.stocks.positions.get(symbol)
        return p.quantity if p else 0

    def fill(self, symbol, quantity, price, fee, timestamp, client_id, strategy):
        price, fee = decimal(price), decimal(fee)
        if symbol in self.futures.contracts:
            trade = self.futures.fill(symbol, quantity, price, fee=fee, timestamp=timestamp)
            realized = trade["closed_net_pnl"] if trade["closed_contracts"] else None
        else:
            # Transfer only existing master funds, never create new capital.
            needed = (
                max(decimal(0), quantity * price + fee - self.stocks.cash)
                if quantity > 0
                else decimal(0)
            )
            if needed:
                if needed > self.futures.cash:
                    raise ValueError("insufficient_master_cash")
                self.stocks.cash += needed
                self.stocks.net_funding += needed
                self.futures.cash -= needed
                self.futures.net_funding -= needed
                self.transfers.append({"at": str(timestamp), "amount": str(needed)})
            realized = self.stocks.apply_fill(
                Fill(
                    len(self.fills) + 1,
                    symbol,
                    Side.BUY if quantity > 0 else Side.SELL,
                    decimal(abs(quantity)),
                    timestamp,
                    price,
                    price,
                    fee,
                    decimal(0),
                    decimal(0),
                )
            )
        self.prices.setdefault(symbol, price)
        self.fills.append(
            {
                "instrument": symbol,
                "quantity": quantity,
                "price": str(price),
                "fee": str(fee),
                "at": str(timestamp),
                "client_id": client_id,
                "strategy": strategy,
                "realized_closed_pnl": str(realized) if realized is not None else None,
            }
        )

    def view(self):
        s = self.stocks.view(self.prices)
        f = self.futures.view(self.prices)
        stock_values = {
            k: p.quantity * self.prices[k] for k, p in s.positions.items() if p.quantity
        }
        future_values = {
            k: decimal(p.quantity) * self.prices[k] * self.futures.contracts[k].spec.multiplier
            for k, p in self.futures.positions.items()
            if p.quantity
        }
        values = stock_values | future_values
        cash = s.cash + f["cash"]
        equity = s.equity + f["equity"]
        assert self.stocks.net_funding + self.futures.net_funding == 0
        return {
            "initial_capital": self.stocks.initial_cash,
            "cash": cash,
            "equity": equity,
            "buying_power": max(decimal(0), cash - f["initial_margin"]),
            "initial_margin": f["initial_margin"],
            "maintenance_margin": f["maintenance_margin"],
            "gross": sum(map(abs, values.values()), decimal(0)),
            "net": sum(values.values(), decimal(0)),
            "positions": {k: self.quantity(k) for k in values},
            "values": values,
            "realized_pnl": s.realized_pnl + self.futures.realized_gross - self.futures.fees,
            "unrealized_pnl": s.unrealized_pnl + f["lifetime_unrealized"],
            "fees": self.stocks.commissions + self.futures.fees,
        }
