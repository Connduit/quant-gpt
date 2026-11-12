import math
from dataclasses import dataclass

import numpy as np

from quantlab.backtesting.models import Bar


@dataclass(frozen=True)
class FeatureConfig:
    return_windows: tuple[int, ...] = (1, 3, 5, 10, 20, 60)
    short_window: int = 10
    long_window: int = 20
    atr_window: int = 14
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_window: int = 20

    def __post_init__(self):
        windows = (
            self.short_window,
            self.long_window,
            self.atr_window,
            self.rsi_window,
            self.macd_fast,
            self.macd_slow,
            self.macd_signal,
            self.bollinger_window,
        )
        if any(isinstance(w, bool) or not isinstance(w, int) or w < 2 for w in windows):
            raise ValueError("Indicator windows must be integers >= 2")
        if not self.return_windows or any(type(w) is not int or w < 1 for w in self.return_windows):
            raise ValueError("Return windows must be positive integers")
        if self.short_window >= self.long_window or self.macd_fast >= self.macd_slow:
            raise ValueError("Short/fast windows must precede long/slow windows")
        if len(set(self.return_windows)) != len(self.return_windows):
            raise ValueError("Duplicate return windows")

    @property
    def warmup(self):
        return max(
            max(self.return_windows) + 1,
            self.long_window + 2,
            self.atr_window + 1,
            self.rsi_window + 1,
            self.macd_slow + self.macd_signal - 1,
            self.bollinger_window,
        )


def definitions(config: FeatureConfig, sector: bool = False) -> dict[str, str]:
    result = {f"return_{w}": f"close / close[{w} sessions ago] - 1" for w in config.return_windows}
    result.update(
        {f"log_return_{w}": f"log(close / close[{w} sessions ago])" for w in config.return_windows}
    )
    result.update(
        {
            "log_return": "log(close / previous close)",
            "momentum": "long-window close return",
            "relative_strength": "long-window stock return minus aligned SPY return",
            "ma_distance_short": "close / short SMA - 1",
            "ma_distance_long": "close / long SMA - 1",
            "distance_high": "close / long-window highest high - 1",
            "distance_low": "close / long-window lowest low - 1",
            "rolling_high": "long-window highest high",
            "rolling_low": "long-window lowest low",
            "realized_vol_short": "sample log-return std over short window * sqrt(252)",
            "realized_vol_long": "sample log-return std over long window * sqrt(252)",
            "atr": "simple mean of true ranges over ATR window",
            "volatility_ratio": "short vol / long vol; 1 when both zero",
            "downside_volatility": "sqrt(mean(min(log return,0)^2)) * sqrt(252), long window",
            "volatility_change": "short realized vol minus previous-session short realized vol",
            "relative_volume": "current volume / long-window mean volume",
            "dollar_volume": "current close * current share volume",
            "dollar_volume_ma": "mean(close * volume) over long window",
            "volume_momentum": "volume / volume[short-window sessions ago] - 1",
            "volume_ma": "long-window mean volume",
            "volume_ma_short": "short-window mean volume",
            "rsi": "Wilder-smoothed RSI; 50 if flat, 100 if gains without losses",
            "macd": "SMA-seeded fast EMA minus slow EMA",
            "macd_signal": "SMA-seeded EMA of available MACD values",
            "macd_histogram": "MACD minus MACD signal",
            "bollinger_z": "(close - rolling mean) / population std; 0 when flat",
            "bollinger_bandwidth": "4 * population std / rolling mean (two-sigma bands)",
            "bollinger_mid": "Bollinger-window SMA",
            "bollinger_upper": "Bollinger-window SMA plus two population standard deviations",
            "bollinger_lower": "Bollinger-window SMA minus two population standard deviations",
            "ma_crossover": "short SMA / long SMA - 1",
            "spy_momentum": "aligned SPY long-window return",
            "spy_volatility": "aligned SPY long-window sample log-return vol * sqrt(252)",
            "market_trend": "SPY close / long-window SPY SMA - 1",
        }
    )
    if sector:
        result["sector_relative_strength"] = "stock long-window return minus sector ETF return"
    return result


def _ema(values, span):
    if len(values) < span:
        return np.array([])
    result = [float(np.mean(values[:span]))]
    alpha = 2 / (span + 1)
    for value in values[span:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return np.array(result)


def calculate(
    history: tuple[Bar, ...],
    benchmark: tuple[Bar, ...],
    config: FeatureConfig | None = None,
    sector: tuple[Bar, ...] | None = None,
) -> dict:
    """Caller supplies only available history, already rebased for effective splits."""
    config = config or FeatureConfig()
    names = definitions(config, sector is not None)
    if (
        min(len(history), len(benchmark), len(sector) if sector is not None else len(history))
        < config.warmup
    ):
        return dict.fromkeys(names)
    if history[-1].session_date != benchmark[-1].session_date or (
        sector is not None and history[-1].session_date != sector[-1].session_date
    ):
        raise ValueError("Market/sector context must share the feature session")
    close = np.array([float(b.close) for b in history])
    high = np.array([float(b.high) for b in history])
    low = np.array([float(b.low) for b in history])
    volume = np.array([b.volume for b in history], dtype=float)
    spy = np.array([float(b.close) for b in benchmark])
    short, long = config.short_window, config.long_window
    logs = np.diff(np.log(close))
    vol_short = np.std(logs[-short:], ddof=1) * math.sqrt(252)
    vol_long = np.std(logs[-long:], ddof=1) * math.sqrt(252)
    true_range = np.maximum.reduce(
        [high[1:] - low[1:], abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])]
    )
    gains, losses = np.maximum(np.diff(close), 0), np.maximum(-np.diff(close), 0)
    w = config.rsi_window
    gain, loss = np.mean(gains[:w]), np.mean(losses[:w])
    for upward, downward in zip(gains[w:], losses[w:], strict=True):
        gain, loss = ((w - 1) * gain + upward) / w, ((w - 1) * loss + downward) / w
    rsi = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
    fast, slow = _ema(close, config.macd_fast), _ema(close, config.macd_slow)
    macds = fast[-len(slow) :] - slow
    macd_signal = _ema(macds, config.macd_signal)[-1]
    mean, std = (
        np.mean(close[-config.bollinger_window :]),
        np.std(close[-config.bollinger_window :]),
    )
    spy_momentum = spy[-1] / spy[-long - 1] - 1
    momentum = close[-1] / close[-long - 1] - 1
    result = {f"return_{w}": close[-1] / close[-w - 1] - 1 for w in config.return_windows}
    result.update(
        {f"log_return_{w}": math.log(close[-1] / close[-w - 1]) for w in config.return_windows}
    )
    result.update(
        {
            "log_return": logs[-1],
            "momentum": momentum,
            "relative_strength": momentum - spy_momentum,
            "ma_distance_short": close[-1] / np.mean(close[-short:]) - 1,
            "ma_distance_long": close[-1] / np.mean(close[-long:]) - 1,
            "distance_high": close[-1] / max(high[-long:]) - 1,
            "distance_low": close[-1] / min(low[-long:]) - 1,
            "rolling_high": max(high[-long:]),
            "rolling_low": min(low[-long:]),
            "realized_vol_short": vol_short,
            "realized_vol_long": vol_long,
            "atr": np.mean(true_range[-config.atr_window :]),
            "volatility_ratio": vol_short / vol_long if vol_long else 1.0,
            "downside_volatility": np.sqrt(np.mean(np.minimum(logs[-long:], 0) ** 2))
            * math.sqrt(252),
            "volatility_change": vol_short - np.std(logs[-short - 1 : -1], ddof=1) * math.sqrt(252),
            "relative_volume": volume[-1] / np.mean(volume[-long:])
            if np.mean(volume[-long:])
            else 0,
            "dollar_volume": close[-1] * volume[-1],
            "dollar_volume_ma": np.mean(close[-long:] * volume[-long:]),
            "volume_momentum": volume[-1] / volume[-short - 1] - 1 if volume[-short - 1] else None,
            "volume_ma": np.mean(volume[-long:]),
            "volume_ma_short": np.mean(volume[-short:]),
            "rsi": rsi,
            "macd": macds[-1],
            "macd_signal": macd_signal,
            "macd_histogram": macds[-1] - macd_signal,
            "bollinger_z": (close[-1] - mean) / std if std else 0,
            "bollinger_bandwidth": 4 * std / mean,
            "bollinger_mid": mean,
            "bollinger_upper": mean + 2 * std,
            "bollinger_lower": mean - 2 * std,
            "ma_crossover": np.mean(close[-short:]) / np.mean(close[-long:]) - 1,
            "spy_momentum": spy_momentum,
            "spy_volatility": np.std(np.diff(np.log(spy))[-long:], ddof=1) * math.sqrt(252),
            "market_trend": spy[-1] / np.mean(spy[-long:]) - 1,
        }
    )
    if sector is not None:
        result["sector_relative_strength"] = momentum - float(
            sector[-1].close / sector[-long - 1].close - 1
        )
    return {
        name: float(value) if value is not None and np.isfinite(value) else None
        for name, value in result.items()
    }
