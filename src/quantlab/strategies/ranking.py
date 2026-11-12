"""Causal cross-sectional targets consumed by the existing event replay engine."""

import hashlib
import json
from dataclasses import asdict
from decimal import ROUND_FLOOR, Decimal

from quantlab.research.config import RankingConfig
from quantlab.strategies.base import Signal


class RankingStrategy:
    def __init__(
        self,
        rows: list[dict],
        universe: tuple[str, ...],
        benchmark: str,
        config: RankingConfig,
        mode: str = "ml",
        seed: int = 42,
    ):
        if mode not in (
            "ml",
            "random",
            "momentum",
            "mean_reversion",
            "equal_weight",
            "spy_buy_hold",
        ):
            raise ValueError("Unknown ranking mode")
        self.universe, self.benchmark, self.config, self.mode, self.seed = (
            universe,
            benchmark,
            config,
            mode,
            seed,
        )
        self.book = {}
        for row in rows:
            if mode == "ml" and not (
                row["train_label_max"] < row["model_available_at"] <= row["prediction_at"]
            ):
                raise ValueError("Prediction model was not causally fitted")
            safe = {
                key: row[key]
                for key in (
                    "symbol",
                    "session_date",
                    "prediction_at",
                    "prediction",
                    "dollar_volume_ma",
                    "momentum",
                    "ma_distance_long",
                    "market_trend",
                )
            }
            safe["realized_vol_long"] = row.get("realized_vol_long", 0.0)
            self.book.setdefault(row["session_date"], []).append(safe)
        self._dates = sorted(self.book)
        self._last_day = None
        self._benchmark_entered = False

    def spec(self):
        serialized = json.dumps(self.book_as_rows(), default=str, sort_keys=True)
        return {
            "mode": self.mode,
            "universe": self.universe,
            "benchmark": self.benchmark,
            "configuration": asdict(self.config),
            "seed": self.seed,
            "prediction_book_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        }

    def book_as_rows(self):
        return [r for d in self._dates for r in sorted(self.book[d], key=lambda r: r["symbol"])]

    def on_bar(self, context):
        day = context.bar.session_date
        if day not in self.book or day == self._last_day:
            return ()
        batch = self.book[day]
        if context.now < max(r["prediction_at"] for r in batch):
            return ()
        # Process once only after the cross section and SPY have actually arrived.
        for symbol in context.histories:
            history = context.histories[symbol]
            if not history or history[-1].session_date < day:
                return ()
        self._last_day = day
        if self.mode == "spy_buy_hold":
            if self._benchmark_entered:
                return ()
            self._benchmark_entered = True
            budget = context.portfolio.equity * Decimal(str(1 - self.config.cash_allocation))
            quantity = (budget / context.prices[self.benchmark]).to_integral_value(
                rounding=ROUND_FLOOR
            )
            return (Signal(self.benchmark, quantity),)
        if self._dates.index(day) % self.config.rebalance_sessions:
            return ()
        eligible = [r for r in batch if r["dollar_volume_ma"] >= self.config.minimum_dollar_volume]
        if (
            self.config.regime_filter
            and batch[0]["market_trend"] < self.config.minimum_market_trend
        ):
            eligible = []

        def score(row):
            if self.mode == "random":
                return int(
                    hashlib.sha256(f"{self.seed}:{day}:{row['symbol']}".encode()).hexdigest(), 16
                )
            value = row[
                {
                    "ml": "prediction",
                    "momentum": "momentum",
                    "mean_reversion": "ma_distance_long",
                }.get(self.mode, "prediction")
            ] * (-1 if self.mode == "mean_reversion" else 1)
            if self.mode == "ml":
                value *= -1 if self.config.lower_is_better else 1
                if self.config.volatility_adjusted:
                    value /= max(row["realized_vol_long"], 1e-6)
            return value

        if self.mode == "ml" and self.config.minimum_prediction is not None:
            eligible = [r for r in eligible if score(r) >= self.config.minimum_prediction]

        if self.mode in ("momentum", "mean_reversion"):
            eligible = [r for r in eligible if score(r) > 0]
        selected = sorted(eligible, key=lambda r: (-score(r), r["symbol"]))
        if self.mode != "equal_weight":
            selected = selected[: self.config.top_n]
        inverse = (
            self.config.position_sizing == "inverse_volatility" and self.mode != "equal_weight"
        )
        units = {
            r["symbol"]: 1 / max(r["realized_vol_long"], 1e-6) if inverse else 1 for r in selected
        }
        total = sum(units.values())
        weights = {
            s: min(
                self.config.maximum_position_weight,
                (1 - self.config.cash_allocation) * value / total,
            )
            for s, value in units.items()
        }
        chosen = {r["symbol"] for r in selected}
        signals = []
        for symbol in sorted(self.universe):
            quantity = (
                (
                    (
                        context.portfolio.equity
                        * Decimal(str(weights[symbol]))
                        / context.prices[symbol]
                    ).to_integral_value(rounding=ROUND_FLOOR)
                )
                if symbol in chosen
                else 0
            )
            signals.append(Signal(symbol, quantity))
        return tuple(signals)
