import numpy as np
import pytest

from quantlab.backtesting.models import decimal
from quantlab.portfolio.allocation import allocate, covariance, diversification
from quantlab.portfolio.risk import RiskLimits, constrain, size_position


def history():
    return np.tile(np.array([[-0.01, -0.02], [0.01, -0.02], [-0.01, 0.02], [0.01, 0.02]]), (10, 1))


def test_known_inverse_vol_and_risk_parity_weights():
    for method in ("inverse_volatility", "risk_parity"):
        result = allocate(["a", "b"], history(), method=method, cash_buffer=0, maximum_weight=1)
        assert result["weights"] == pytest.approx({"a": 2 / 3, "b": 1 / 3}, rel=1e-5)
    fixed = allocate(["a", "b"], history(), method="fixed", fixed={"a": 0.2, "b": 0.3})
    assert fixed["cash_weight"] == pytest.approx(0.5)
    capped = allocate(["a", "b"], history(), method="equal", maximum_weight=0.2)
    assert capped["cash_weight"] == pytest.approx(0.6)


def test_covariance_regularized_and_missing_history_cash():
    cov = covariance(history())
    assert np.all(np.linalg.eigvalsh(cov) > 0)
    assert allocate(["a", "b"], [], method="inverse_volatility")["cash_weight"] == 1
    assert allocate(["a", "b"], np.zeros((30, 2)), method="inverse_volatility")["cash_weight"] == 1
    with pytest.raises(ValueError):
        allocate(["a", "b"], history(), method="fixed", fixed={"a": 2, "b": 0})
    report = diversification(history(), [0.5, 0.5])
    assert sum(report["risk_contributions"]) == pytest.approx(1)
    assert report["annualized_volatility"] > 0


def test_volatility_target_never_levers_up():
    r = allocate(
        ["a", "b"],
        history(),
        method="volatility_target",
        cash_buffer=0.1,
        maximum_weight=1,
        target_volatility=0.05,
    )
    assert sum(r["weights"].values()) < 0.9
    r = allocate(
        ["a", "b"],
        history(),
        method="volatility_target",
        cash_buffer=0.1,
        maximum_weight=1,
        target_volatility=5,
    )
    assert sum(r["weights"].values()) == pytest.approx(0.9)


@pytest.mark.parametrize(
    "method", ["target_weight", "fixed_fractional", "volatility_adjusted", "atr", "risk_budget"]
)
def test_sizing_methods_respect_cash_lot_multiplier(method):
    q = size_position(
        10000,
        100,
        method=method,
        fraction=0.4,
        volatility=0.2,
        atr=2,
        multiplier=2,
        lot=2,
        buying_power=1000,
        maximum_weight=0.3,
        cost_per_unit=1,
    )
    assert q % 2 == 0
    assert q * 201 <= 1000
    assert q >= 0


def test_hand_calculated_atr_sizing():
    assert size_position(
        10000, 100, method="atr", atr=2, risk_fraction=0.01, maximum_weight=1
    ) == decimal(50)
    assert size_position(
        10000, 100, method="target_weight", fraction=0.2, maximum_weight=1
    ) == decimal(20)


def test_risk_position_sector_gross_correlation_caps():
    limits = RiskLimits(
        maximum_position=0.4,
        maximum_sector=0.5,
        maximum_gross=0.6,
        maximum_net=0.6,
        maximum_correlated=0.3,
    )
    target, reasons = constrain(
        {"A": decimal(80), "B": decimal(80)},
        {"A": decimal(10), "B": decimal(10)},
        decimal(1000),
        limits,
        {"A": "tech", "B": "tech"},
        [["A", "B"]],
    )
    assert (target["A"] + target["B"]) * 10 <= 300
    assert "correlated_exposure" in reasons
    assert "sector:tech" in reasons
    assert "gross_net_leverage" in reasons
    with pytest.raises(ValueError):
        RiskLimits(maximum_leverage=2)
