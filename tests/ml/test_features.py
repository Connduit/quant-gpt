import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import numpy as np
import pytest

from quantlab.backtesting.models import Bar
from quantlab.features import FeatureConfig, calculate, definitions


def history(flat=False):
    result = []
    for i in range(80):
        day = date(2020, 1, 1) + timedelta(days=i)
        closing = D(100 if flat else i + 1)
        opening = datetime.combine(day, datetime.min.time(), UTC)
        result.append(
            Bar(
                "TEST",
                day,
                opening,
                opening + timedelta(hours=7),
                opening + timedelta(hours=8),
                closing,
                closing + 1,
                closing - D("0.5"),
                closing,
                100 if flat else 100 + i,
            )
        )
    return tuple(result)


def test_hand_calculated_price_volume_indicators():
    bars = history()
    result = calculate(bars, bars)
    for horizon in (1, 3, 5, 10, 20, 60):
        assert result[f"return_{horizon}"] == pytest.approx(80 / (80 - horizon) - 1)
        assert result[f"log_return_{horizon}"] == pytest.approx(math.log(80 / (80 - horizon)))
    assert result["log_return"] == pytest.approx(math.log(80 / 79))
    assert result["momentum"] == pytest.approx(80 / 60 - 1)
    assert result["relative_strength"] == 0
    assert result["ma_distance_short"] == pytest.approx(80 / 75.5 - 1)
    assert result["ma_distance_long"] == pytest.approx(80 / 70.5 - 1)
    assert result["distance_high"] == pytest.approx(80 / 81 - 1)
    assert result["distance_low"] == pytest.approx(80 / 60.5 - 1)
    assert result["rolling_high"] == 81
    assert result["rolling_low"] == 60.5
    assert result["atr"] == 2
    assert result["rsi"] == 100
    assert result["macd"] == pytest.approx(7)
    assert result["macd_signal"] == pytest.approx(7)
    assert result["macd_histogram"] == pytest.approx(0, abs=1e-12)
    assert result["relative_volume"] == pytest.approx(179 / 169.5)
    assert result["dollar_volume"] == 80 * 179
    assert result["volume_ma"] == 169.5
    assert result["volume_ma_short"] == 174.5
    assert result["volume_momentum"] == pytest.approx(179 / 169 - 1)
    assert result["bollinger_z"] == pytest.approx(9.5 / math.sqrt(33.25))
    assert result["bollinger_bandwidth"] == pytest.approx(4 * math.sqrt(33.25) / 70.5)
    assert result["bollinger_upper"] == pytest.approx(70.5 + 2 * math.sqrt(33.25))
    assert result["bollinger_lower"] == pytest.approx(70.5 - 2 * math.sqrt(33.25))
    assert result["ma_crossover"] == pytest.approx(75.5 / 70.5 - 1)
    assert result["spy_momentum"] == result["momentum"]
    assert result["market_trend"] == result["ma_distance_long"]
    assert set(result) == set(definitions(FeatureConfig()))


def test_realized_downside_volatility_and_changes():
    bars = history()
    values = calculate(bars, bars)
    returns = np.log(np.arange(2, 81) / np.arange(1, 80))
    assert values["realized_vol_short"] == pytest.approx(
        np.std(returns[-10:], ddof=1) * math.sqrt(252)
    )
    assert values["realized_vol_long"] == pytest.approx(
        np.std(returns[-20:], ddof=1) * math.sqrt(252)
    )
    assert values["volatility_change"] == pytest.approx(
        (np.std(returns[-10:], ddof=1) - np.std(returns[-11:-1], ddof=1)) * math.sqrt(252)
    )
    assert values["downside_volatility"] == 0
    falling = tuple(
        replace(
            b,
            open=D(100) - b.close,
            close=D(100) - b.close,
            high=D(101) - b.close,
            low=D(99) - b.close,
        )
        for b in bars
    )
    result = calculate(falling, falling)
    assert result["rsi"] == 0
    assert result["downside_volatility"] > 0


def test_flat_warmup_sector_and_missing_volume():
    bars = history(flat=True)
    result = calculate(bars, bars, sector=bars)
    assert result["rsi"] == 50
    assert result["bollinger_z"] == 0
    assert result["volatility_ratio"] == 1
    assert result["sector_relative_strength"] == 0
    assert all(value is not None for value in result.values())
    assert all(value is None for value in calculate(bars[:10], bars[:10]).values())
    zero_volume = tuple(replace(bar, volume=0) for bar in bars)
    assert calculate(zero_volume, bars)["volume_momentum"] is None


@pytest.mark.parametrize(
    "kwargs",
    [{"rsi_window": 1}, {"return_windows": (1, 1)}, {"short_window": 20}, {"macd_fast": 26}],
)
def test_invalid_feature_config(kwargs):
    with pytest.raises(ValueError):
        FeatureConfig(**kwargs)
