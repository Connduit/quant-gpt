"""Chronological replay with one cash account and explicitly synchronized equity feeds."""

import heapq
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import UTC, datetime, time
from decimal import Context, Decimal, localcontext
from types import MappingProxyType
from zoneinfo import ZoneInfo

from quantlab.backtesting.data import DailyData, MarketData
from quantlab.backtesting.metrics import performance
from quantlab.backtesting.models import (
    ZERO,
    Bar,
    Costs,
    OpeningEvent,
    Order,
    OrderStatus,
    Side,
    decimal,
)
from quantlab.backtesting.portfolio import Portfolio, Position
from quantlab.strategies.base import Signal, Strategy, StrategyContext


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: Decimal = Decimal("100000")
    costs: Costs = Costs()
    sessions_per_year: int = 252

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_cash", decimal(self.initial_cash))
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive and finite")
        if (
            isinstance(self.sessions_per_year, bool)
            or not isinstance(self.sessions_per_year, int)
            or self.sessions_per_year <= 0
        ):
            raise ValueError("sessions_per_year must be a positive integer")


@dataclass
class BacktestResult:
    equity: list[dict]
    trades: list[dict]
    orders: list[dict]
    signals: list[dict]
    actions: list[dict]
    metrics: dict
    metadata: dict
    positions: list[dict] = field(default_factory=list)


def run_backtest(
    data: DailyData | MarketData, strategy: Strategy, config: BacktestConfig | None = None
) -> BacktestResult:
    with localcontext(Context(prec=34)):
        return _replay(data, strategy, config or BacktestConfig())


def _replay(data, strategy, config):
    feeds = {
        d.instrument.symbol: d for d in (data.feeds if isinstance(data, MarketData) else (data,))
    }
    if any(
        d.instrument.currency != "USD" or d.instrument.calendar != "XNYS" for d in feeds.values()
    ):
        raise ValueError("Only USD cash equities on the XNYS session convention are supported")
    first = next(iter(feeds.values()))
    end = first.bars[-1].close_time
    portfolio = Portfolio(config.initial_cash)
    orders: list[Order] = []
    trades, signals, action_log, equity, positions = [], [], [], [], []
    histories: dict[str, list[Bar]] = {s: [] for s in feeds}
    applied_splits = {s: [] for s in feeds}
    observed_prices, observed_times = {}, {}
    events = []
    serial = 0

    def schedule(when, priority, kind, payload):
        nonlocal serial
        if when <= end:
            heapq.heappush(events, (when, priority, serial, kind, payload))
            serial += 1

    for i, reference in enumerate(first.bars):
        batch = tuple(feeds[s].bars[i] for s in sorted(feeds))
        schedule(reference.open_time, 3, "open", batch)
        schedule(reference.close_time, 4, "close", batch)
        for bar in batch:
            schedule(bar.available_at, 5, "available", bar)
    dividend_id = 0
    for symbol, feed in sorted(feeds.items()):
        by_date = {bar.session_date: bar for bar in feed.bars}
        for split in feed.actions.splits:
            if feed.bars[0].session_date <= split.date <= feed.bars[-1].session_date:
                if split.date not in by_date:
                    raise ValueError("Split effective date must be a trading session")
                schedule(by_date[split.date].open_time, 0, "split", (symbol, split))
        for dividend in feed.actions.dividends:
            if feed.bars[0].session_date <= dividend.ex_date <= feed.bars[-1].session_date:
                if dividend.ex_date not in by_date:
                    raise ValueError("Dividend ex date must be a trading session")
                ex_time = by_date[dividend.ex_date].open_time
                payload = (symbol, dividend_id, dividend)
                schedule(ex_time, 1, "dividend_ex", payload)
                pay_time = datetime.combine(
                    dividend.pay_date, time(), ZoneInfo("America/New_York")
                ).astimezone(UTC)
                schedule(max(pay_time, ex_time), 2, "dividend_pay", payload)
                dividend_id += 1

    def rebase(bar, ratio):
        return replace(
            bar,
            open=bar.open / ratio,
            high=bar.high / ratio,
            low=bar.low / ratio,
            close=bar.close / ratio,
        )

    while events:
        now, _, _, kind, payload = heapq.heappop(events)
        if kind == "split":
            symbol, split = payload
            before = portfolio.positions.get(symbol, Position())
            portfolio.split(symbol, split.ratio)
            histories[symbol] = [rebase(bar, split.ratio) for bar in histories[symbol]]
            applied_splits[symbol].append(split)
            if symbol in observed_prices:
                observed_prices[symbol] /= split.ratio
            for order in orders:
                if order.symbol == symbol and order.status == OrderStatus.PENDING:
                    order.quantity *= split.ratio
            action_log.append(
                {
                    "timestamp": now,
                    "kind": kind,
                    "symbol": symbol,
                    "ratio": split.ratio,
                    "quantity_before": before.quantity,
                    "quantity_after": portfolio.positions.get(symbol, Position()).quantity,
                }
            )
        elif kind == "dividend_ex":
            symbol, action_id, dividend = payload
            amount = portfolio.accrue_dividend(action_id, symbol, dividend.amount)
            action_log.append(
                {
                    "timestamp": now,
                    "kind": kind,
                    "symbol": symbol,
                    "action_id": action_id,
                    "per_share": dividend.amount,
                    "entitlement": amount,
                }
            )
        elif kind == "dividend_pay":
            symbol, action_id, _ = payload
            amount = portfolio.pay_dividend(action_id)
            action_log.append(
                {
                    "timestamp": now,
                    "kind": kind,
                    "symbol": symbol,
                    "action_id": action_id,
                    "paid": amount,
                }
            )
        elif kind == "open":
            openings = {b.symbol: OpeningEvent(b.symbol, now, b.open) for b in payload}
            for symbol, opening in openings.items():
                observed_prices[symbol], observed_times[symbol] = opening.price, now
            # Opening prints are simultaneous; liquidations fund buys, then stable IDs break ties.
            for order in sorted(orders, key=lambda o: (o.side != Side.SELL, o.order_id)):
                if order.status != OrderStatus.PENDING or order.submitted_at >= now:
                    continue
                fill = config.costs.fill(order, openings[order.symbol])
                try:
                    realized = portfolio.apply_fill(fill)
                except ValueError as exc:
                    order.status, order.reason = OrderStatus.REJECTED, str(exc)
                else:
                    order.status = OrderStatus.FILLED
                    trades.append({**asdict(fill), "realized_pnl": realized})
                order.resolved_at = now
        elif kind == "close":
            marks = {b.symbol: b.close for b in payload}
            view = portfolio.view(marks)
            market_value = sum((p.quantity * marks[s] for s, p in view.positions.items()), ZERO)
            quantity = sum((p.quantity for p in view.positions.values()), ZERO)
            average_cost = (
                next(iter(view.positions.values()), Position()).average_cost
                if len(feeds) == 1
                else ZERO
            )
            equity.append(
                {
                    "session_date": payload[0].session_date,
                    "timestamp": now,
                    "cash": view.cash,
                    "quantity": quantity,
                    "average_cost": average_cost,
                    "market_value": market_value,
                    "dividend_receivable": view.dividend_receivable,
                    "equity": view.equity,
                    "realized_pnl": view.realized_pnl,
                    "unrealized_pnl": view.unrealized_pnl,
                    "dividend_income": view.dividend_income,
                    "gross_exposure": market_value / view.equity if view.equity else ZERO,
                    "commissions": portfolio.commissions,
                    "spread_cost": portfolio.spread_cost,
                    "slippage_cost": portfolio.slippage_cost,
                }
            )
            for symbol in sorted(feeds):
                position = view.positions.get(symbol, Position())
                positions.append(
                    {
                        "session_date": payload[0].session_date,
                        "symbol": symbol,
                        "quantity": position.quantity,
                        "average_cost": position.average_cost,
                        "market_value": position.quantity * marks[symbol],
                    }
                )
        elif kind == "available":
            bar = payload
            symbol = bar.symbol
            for split in applied_splits[symbol]:
                if bar.session_date < split.date:
                    bar = rebase(bar, split.ratio)
            histories[symbol].append(bar)
            if symbol not in observed_times or bar.close_time >= observed_times[symbol]:
                observed_prices[symbol], observed_times[symbol] = bar.close, bar.close_time
            context = StrategyContext(
                now,
                bar,
                tuple(histories[symbol]),
                portfolio.view(observed_prices),
                MappingProxyType({s: tuple(h) for s, h in histories.items()}),
                MappingProxyType(observed_prices.copy()),
            )
            seen = set()
            for signal in strategy.on_bar(context):
                if not isinstance(signal, Signal):
                    raise ValueError("Strategies must return Signal values")
                if signal.symbol not in feeds or signal.symbol in seen:
                    raise ValueError("A callback may emit at most one target per known instrument")
                seen.add(signal.symbol)
                signals.append(
                    {
                        "timestamp": now,
                        "session_date": bar.session_date,
                        "symbol": signal.symbol,
                        "target_quantity": signal.target_quantity,
                    }
                )
                for order in orders:
                    if order.symbol == signal.symbol and order.status == OrderStatus.PENDING:
                        order.status = OrderStatus.CANCELLED
                        order.resolved_at, order.reason = now, "superseded_by_target"
                quantity = portfolio.positions.get(signal.symbol, Position()).quantity
                difference = signal.target_quantity - quantity
                if difference:
                    orders.append(
                        Order(
                            len(orders) + 1,
                            signal.symbol,
                            Side.BUY if difference > 0 else Side.SELL,
                            abs(difference),
                            now,
                            abs(difference),
                        )
                    )
    for order in orders:
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.EXPIRED
            order.resolved_at, order.reason = end, "end_of_data"
    metrics = performance(equity, trades, config.initial_cash, config.sessions_per_year)
    parameters = (
        strategy.spec()
        if hasattr(strategy, "spec")
        else (asdict(strategy) if is_dataclass(strategy) else {})
    )
    metadata = {
        "snapshot_id": data.snapshot_id,
        "data_manifest": data.manifest,
        "corporate_actions": asdict(first.actions)
        if len(feeds) == 1
        else {s: asdict(d.actions) for s, d in feeds.items()},
        "strategy": type(strategy).__name__,
        "strategy_parameters": parameters,
        "strategy_parameters_complete": is_dataclass(strategy) or hasattr(strategy, "spec"),
        "configuration": asdict(config),
        "synthetic": data.manifest["synthetic"],
        "performance_kind": "hypothetical_backtest",
        "execution": "next_eligible_open_strictly_after_signal",
        "position_policy": "long_only_cash_no_leverage",
        "final_positions": "marked_at_final_close_not_liquidated",
        "replay_start": first.bars[0].session_date,
        "replay_end": first.bars[-1].session_date,
    }
    return BacktestResult(
        equity,
        trades,
        [asdict(o) for o in orders],
        signals,
        action_log,
        metrics,
        metadata,
        positions,
    )
