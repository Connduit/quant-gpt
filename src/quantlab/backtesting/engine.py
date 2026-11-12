"""Chronological replay. Strategy observations never receive the full input dataset."""

import heapq
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime, time
from decimal import Context, Decimal, localcontext
from zoneinfo import ZoneInfo

from quantlab.backtesting.data import DailyData
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
        if self.initial_cash <= 0 or not self.initial_cash.is_finite():
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


def run_backtest(
    data: DailyData, strategy: Strategy, config: BacktestConfig | None = None
) -> BacktestResult:
    # Stable accounting precision independent of the calling research process.
    with localcontext(Context(prec=34)):
        return _replay(data, strategy, config or BacktestConfig())


def _replay(data: DailyData, strategy: Strategy, config: BacktestConfig) -> BacktestResult:
    if not data.bars:
        raise ValueError("Cannot replay empty data")
    if data.instrument.currency != "USD" or data.instrument.calendar != "XNYS":
        raise ValueError("Only USD cash equities on the XNYS session convention are supported")
    bars = data.bars
    symbol = data.instrument.symbol
    portfolio = Portfolio(config.initial_cash)
    orders: list[Order] = []
    trades: list[dict] = []
    signals: list[dict] = []
    action_log: list[dict] = []
    equity: list[dict] = []
    history: list[Bar] = []
    applied_splits = []
    observed_price = None
    observed_time = None
    events: list[tuple[datetime, int, int, str, object]] = []
    serial = 0
    end = bars[-1].close_time
    by_date = {bar.session_date: bar for bar in bars}

    def schedule(when, priority, kind, payload):
        nonlocal serial
        if when <= end:
            heapq.heappush(events, (when, priority, serial, kind, payload))
            serial += 1

    for bar in bars:
        schedule(bar.open_time, 3, "open", bar)
        schedule(bar.close_time, 4, "close", bar)
        schedule(bar.available_at, 5, "available", bar)
    for split in data.actions.splits:
        if bars[0].session_date <= split.date <= bars[-1].session_date:
            if split.date not in by_date:
                raise ValueError("Split effective date must be a trading session")
            schedule(by_date[split.date].open_time, 0, "split", split)
    for action_id, dividend in enumerate(data.actions.dividends):
        if bars[0].session_date <= dividend.ex_date <= bars[-1].session_date:
            if dividend.ex_date not in by_date:
                raise ValueError("Dividend ex date must be a trading session")
            ex_time = by_date[dividend.ex_date].open_time
            schedule(ex_time, 1, "dividend_ex", (action_id, dividend))
            pay_time = datetime.combine(
                dividend.pay_date, time(), ZoneInfo("America/New_York")
            ).astimezone(UTC)
            schedule(max(pay_time, ex_time), 2, "dividend_pay", (action_id, dividend))

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
            split = payload
            before = portfolio.positions.get(symbol, Position())
            portfolio.split(symbol, split.ratio)
            history = [rebase(bar, split.ratio) for bar in history]
            applied_splits.append(split)
            if observed_price is not None:
                observed_price /= split.ratio
            for order in orders:
                if order.status == OrderStatus.PENDING:
                    order.quantity *= split.ratio
            action_log.append(
                {
                    "timestamp": now,
                    "kind": kind,
                    "ratio": split.ratio,
                    "quantity_before": before.quantity,
                    "quantity_after": portfolio.positions.get(symbol, Position()).quantity,
                }
            )
        elif kind == "dividend_ex":
            action_id, dividend = payload
            amount = portfolio.accrue_dividend(action_id, symbol, dividend.amount)
            action_log.append(
                {
                    "timestamp": now,
                    "kind": kind,
                    "action_id": action_id,
                    "per_share": dividend.amount,
                    "entitlement": amount,
                }
            )
        elif kind == "dividend_pay":
            action_id, _ = payload
            amount = portfolio.pay_dividend(action_id)
            action_log.append(
                {"timestamp": now, "kind": kind, "action_id": action_id, "paid": amount}
            )
        elif kind == "open":
            bar = payload
            opening = OpeningEvent(bar.symbol, now, bar.open)
            # Today's open is observable now; today's close/high/low/volume are not.
            observed_price, observed_time = bar.open, bar.open_time
            for order in orders:
                if order.status != OrderStatus.PENDING or order.submitted_at >= now:
                    continue
                fill = config.costs.fill(order, opening)
                try:
                    realized = portfolio.apply_fill(fill)
                except ValueError as exc:
                    order.status, order.reason = OrderStatus.REJECTED, str(exc)
                else:
                    order.status = OrderStatus.FILLED
                    trades.append({**asdict(fill), "realized_pnl": realized})
                order.resolved_at = now
        elif kind == "close":
            bar = payload
            view = portfolio.view({symbol: bar.close})
            position = view.positions.get(symbol, Position())
            market_value = position.quantity * bar.close
            equity.append(
                {
                    "session_date": bar.session_date,
                    "timestamp": now,
                    "cash": view.cash,
                    "quantity": position.quantity,
                    "average_cost": position.average_cost,
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
        elif kind == "available":
            bar = payload
            for split in applied_splits:
                if bar.session_date < split.date:
                    bar = rebase(bar, split.ratio)
            history.append(bar)
            # Late publication must not replace a newer observable open with a stale close.
            if observed_time is None or bar.close_time >= observed_time:
                observed_price, observed_time = bar.close, bar.close_time
            context = StrategyContext(
                now, bar, tuple(history), portfolio.view({symbol: observed_price})
            )
            proposed = strategy.on_bar(context)
            seen = set()
            for signal in proposed:
                if not isinstance(signal, Signal):
                    raise ValueError("Strategies must return Signal values")
                if signal.symbol != symbol or signal.symbol in seen:
                    raise ValueError("A callback may emit at most one target for this instrument")
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
                    if order.status == OrderStatus.PENDING:
                        order.status = OrderStatus.CANCELLED
                        order.resolved_at, order.reason = now, "superseded_by_target"
                quantity = portfolio.positions.get(symbol, Position()).quantity
                difference = signal.target_quantity - quantity
                if difference:
                    orders.append(
                        Order(
                            len(orders) + 1,
                            symbol,
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
    metadata = {
        "snapshot_id": data.snapshot_id,
        "data_manifest": data.manifest,
        "corporate_actions": asdict(data.actions),
        "strategy": type(strategy).__name__,
        "strategy_parameters": asdict(strategy) if is_dataclass(strategy) else {},
        "strategy_parameters_complete": is_dataclass(strategy),
        "configuration": asdict(config),
        "synthetic": data.manifest["synthetic"],
        "performance_kind": "hypothetical_backtest",
        "execution": "next_eligible_open_strictly_after_signal",
        "position_policy": "long_only_cash_no_leverage",
        "final_positions": "marked_at_final_close_not_liquidated",
    }
    return BacktestResult(
        equity, trades, [asdict(order) for order in orders], signals, action_log, metrics, metadata
    )
