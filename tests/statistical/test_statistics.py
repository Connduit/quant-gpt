import math
from statistics import NormalDist

import numpy as np
import pytest

from quantlab.statistical.statistics import (
    bootstrap_indices,
    deflated_sharpe,
    effective_sample_size,
    fdr_adjust,
    max_test_bootstrap,
    path_metrics,
    search_complexity,
    sharpe_probability,
    uncertainty,
)


def test_psr_known_symmetric_example():
    x = np.array([-0.01, 0, 0.01, 0])
    assert sharpe_probability(x)["probability"] == pytest.approx(0.5)
    y = x + 0.002
    sr = y.mean() / y.std(ddof=1)
    z = (y - y.mean()) / y.std()
    expected = NormalDist().cdf(
        sr * math.sqrt(3) / math.sqrt(1 - np.mean(z**3) * sr + (np.mean(z**4) - 1) / 4 * sr**2)
    )
    assert sharpe_probability(y)["probability"] == pytest.approx(expected)
    assert sharpe_probability([0.01] * 20)["probability"] is None


def test_deflation_penalizes_search():
    x = np.random.default_rng(9).normal(0.001, 0.01, 500)
    one = deflated_sharpe(x, 1)
    many = deflated_sharpe(x, 100)
    assert many["reference_daily_sharpe"] > one["reference_daily_sharpe"]
    assert many["probability"] < one["probability"]
    with pytest.raises(ValueError):
        deflated_sharpe(x, 0)


def test_known_fdr_examples_and_dependence():
    assert fdr_adjust([0.01, 0.04, 0.03], dependence=False) == pytest.approx([0.03, 0.04, 0.04])
    assert fdr_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.055, 0.0733333333, 0.0733333333])
    assert fdr_adjust([0.01], family_size=10, dependence=False) == pytest.approx([0.1])
    with pytest.raises(ValueError):
        fdr_adjust([float("nan")])
    with pytest.raises(ValueError):
        fdr_adjust([0.1, 0.2], family_size=1)


def test_autocorrelation_reduces_effective_information():
    rng = np.random.default_rng(4)
    white = rng.normal(0, 0.001, 1000)
    dependent = np.zeros(1000)
    for i in range(1, 1000):
        dependent[i] = 0.95 * dependent[i - 1] + white[i]
    assert effective_sample_size(dependent) < effective_sample_size(white) / 3
    assert effective_sample_size([0] * 20) == 1


@pytest.mark.parametrize("method", ["stationary", "moving_block"])
def test_dependent_bootstrap_reproducibility_and_intervals(method):
    x = np.random.default_rng(1).normal(0.0004, 0.01, 300)
    a = uncertainty([x[:150], x[150:]], replications=100, block_length=10, seed=3, method=method)
    assert a == uncertainty(
        [x[:150], x[150:]], replications=100, block_length=10, seed=3, method=method
    )
    lo, hi = a["percentile_intervals"]["mean_daily_return"]
    assert lo < x.mean() < hi
    assert a["percentile_intervals"]["maximum_drawdown"][1] <= 0


def test_block_indices_and_known_path():
    indices = bootstrap_indices(30, 5, np.random.default_rng(2), "moving_block")
    for i in range(0, 30, 5):
        assert np.diff(indices[i : i + 5]).tolist() == [1] * 4
    assert path_metrics([0.1, -0.1, 0])["total_return"] == pytest.approx(-0.01)
    assert path_metrics([0.1, -0.1, 0])["maximum_drawdown"] == pytest.approx(-0.1)
    with pytest.raises(ValueError):
        bootstrap_indices(10, 11, np.random.default_rng())
    with pytest.raises(ValueError):
        uncertainty([[0.1] * 20], replications=5)
    with pytest.raises(ValueError):
        path_metrics([0, float("nan"), 0])


def test_max_t_family_dependence_and_null():
    rng = np.random.default_rng(7)
    x = rng.normal(0, 0.01, (160, 3))
    x[:, 1] = x[:, 0]
    result = max_test_bootstrap([x[:80], x[80:]], replications=100, block_length=5, seed=2)
    assert result == max_test_bootstrap([x[:80], x[80:]], replications=100, block_length=5, seed=2)
    assert np.all(np.asarray(result["familywise_pvalues"]) >= result["pvalues"])
    assert result["pvalues"][0] == result["pvalues"][1]
    assert search_complexity(x[:, :2], 10)["effective_rank_diagnostic"] == pytest.approx(1)
    assert max_test_bootstrap([np.zeros((50, 2))], replications=100)["pvalues"] == [1, 1]
