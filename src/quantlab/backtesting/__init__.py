"""Deterministic daily-equity replay, independent of brokers and model training."""

from quantlab.backtesting.engine import BacktestConfig, run_backtest

__all__ = ["BacktestConfig", "run_backtest"]
