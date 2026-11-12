from dataclasses import replace
from decimal import Decimal as D

import pytest

from quantlab.backtesting.actions import CorporateActions, Dividend, Split
from quantlab.backtesting.data import MarketData
from quantlab.backtesting.engine import BacktestConfig, run_backtest
from quantlab.backtesting.models import Costs
from quantlab.research.config import RankingConfig
from quantlab.strategies.base import Signal
from quantlab.strategies.ranking import RankingStrategy


def market_and_rows(feeds):
    market = MarketData(tuple(replace(d, bars=d.bars[:8]) for d in feeds.values()))
    rows = []
    for i in range(6):
        for number, symbol in enumerate(("AAA", "BBB", "CCC")):
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": feeds[symbol].bars[i].session_date,
                    "prediction_at": feeds[symbol].bars[i].available_at,
                    "prediction": 3 - number if i < 2 else number,
                    "dollar_volume_ma": 1e8,
                    "momentum": 0.01,
                    "ma_distance_long": -0.02,
                    "market_trend": 0.01,
                    "train_label_max": feeds[symbol].bars[0].open_time,
                    "model_available_at": feeds[symbol].bars[0].close_time,
                }
            )
    return market, rows


def test_ranking_top_n_cash_rebalancing_and_real_execution(ml_feeds):
    feeds, _, _, _ = ml_feeds
    market, rows = market_and_rows(feeds)
    config = RankingConfig(
        top_n=1, rebalance_sessions=2, maximum_position_weight=0.4, cash_allocation=0.2
    )
    result = run_backtest(
        market,
        RankingStrategy(rows, ("AAA", "BBB", "CCC"), "SPY", config),
        BacktestConfig(D(10000), Costs(0, 0, 0, 0, 0)),
    )
    buys = [t for t in result.trades if t["side"] == "buy"]
    assert buys[0]["symbol"] == "AAA"
    assert any(t["symbol"] == "CCC" for t in buys)
    assert result.positions
    assert all(row["cash"] >= 0 and row["gross_exposure"] <= 1 for row in result.equity)
    submitted_days = sorted({s["session_date"] for s in result.signals})
    assert submitted_days == [feeds["AAA"].bars[i].session_date for i in (0, 2, 4)]
    assert result.trades[0]["timestamp"] > result.orders[0]["submitted_at"]
    # Quantities are capped using only the signal-time available price.
    first_price = feeds["AAA"].bars[0].close
    assert buys[0]["quantity"] <= D(4000) / first_price


def test_liquidity_regime_and_causality_guards(ml_feeds):
    feeds, _, _, _ = ml_feeds
    market, rows = market_and_rows(feeds)
    for config in (
        RankingConfig(minimum_dollar_volume=1e12),
        RankingConfig(regime_filter=True, minimum_market_trend=0.1),
    ):
        result = run_backtest(market, RankingStrategy(rows, ("AAA", "BBB", "CCC"), "SPY", config))
        assert not result.trades
    bad = [dict(r) for r in rows]
    bad[0]["train_label_max"] = bad[0]["prediction_at"]
    with pytest.raises(ValueError, match="causally"):
        RankingStrategy(bad, ("AAA", "BBB", "CCC"), "SPY", RankingConfig())


def test_random_baseline_reproduces_orders(ml_feeds):
    feeds, _, _, _ = ml_feeds
    market, rows = market_and_rows(feeds)
    config = RankingConfig(top_n=1, rebalance_sessions=1)
    one = run_backtest(
        market, RankingStrategy(rows, ("AAA", "BBB", "CCC"), "SPY", config, "random", 7)
    )
    two = run_backtest(
        market, RankingStrategy(rows, ("AAA", "BBB", "CCC"), "SPY", config, "random", 7)
    )
    assert one.orders == two.orders and one.trades == two.trades


def test_shared_cash_sells_fund_buys_without_asset_order_bias(ml_feeds):
    feeds, _, _, _ = ml_feeds
    normalized = []
    for data in feeds.values():
        bars = tuple(
            replace(b, open=D(100), high=D(101), low=D(99), close=D(100)) for b in data.bars[:4]
        )
        normalized.append(replace(data, bars=bars))
    market = MarketData(tuple(normalized))

    class Rotate:
        def __init__(self):
            self.done = set()

        def on_bar(self, context):
            day = context.bar.session_date
            if day in self.done or not all(
                h and h[-1].session_date == day for h in context.histories.values()
            ):
                return ()
            self.done.add(day)
            if len(self.done) == 1:
                return Signal("AAA", 5), Signal("BBB", 5)
            if len(self.done) == 2:
                return Signal("BBB", 10), Signal("AAA", 0)  # buy submitted before funding sell
            return ()

    result = run_backtest(market, Rotate(), BacktestConfig(D(1000), Costs(0, 0, 0, 0, 0)))
    assert [t["side"] for t in result.trades[-2:]] == ["sell", "buy"]
    assert all(order["status"] == "filled" for order in result.orders)
    assert result.equity[-1]["cash"] == 0
    assert result.equity[-1]["equity"] == 1000


def test_multi_stock_actions_do_not_share_entitlements_or_split_other_instruments(ml_feeds):
    feeds, _, dates, _ = ml_feeds
    normalized = []
    for symbol, source in feeds.items():
        bars = tuple(
            replace(
                b,
                open=D(50 if symbol == "AAA" and i >= 2 else 100),
                close=D(50 if symbol == "AAA" and i >= 2 else 100),
                high=D(51 if symbol == "AAA" and i >= 2 else 101),
                low=D(49 if symbol == "AAA" and i >= 2 else 99),
            )
            for i, b in enumerate(source.bars[:4])
        )
        actions = CorporateActions(
            symbol,
            dates[0],
            dates[-1],
            "explicit synthetic action test",
            (Split(dates[2], D(2)),) if symbol == "AAA" else (),
            (Dividend(dates[2], dates[3], D(1 if symbol == "AAA" else 2)),)
            if symbol in ("AAA", "BBB")
            else (),
        )
        normalized.append(replace(source, bars=bars, actions=actions))

    class OwnBoth:
        def __init__(self):
            self.entered = False

        def on_bar(self, context):
            if self.entered or not all(context.histories.values()):
                return ()
            self.entered = True
            return Signal("AAA", 1), Signal("BBB", 1)

    result = run_backtest(
        MarketData(tuple(normalized)), OwnBoth(), BacktestConfig(D(1000), Costs(0, 0, 0, 0, 0))
    )
    assert result.metrics["dividend_income"] == 4
    assert result.equity[-1]["cash"] == 804
    assert result.equity[-1]["equity"] == 1004
    assert result.equity[-1]["dividend_receivable"] == 0
    final = {p["symbol"]: p for p in result.positions if p["session_date"] == dates[3]}
    assert final["AAA"]["quantity"] == 2
    assert final["BBB"]["quantity"] == 1
