"""Dependence-aware diagnostics, not guarantees of future profitability."""

import math
from statistics import NormalDist

import numpy as np

NORMAL = NormalDist()


def series(values, minimum=3):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < minimum or not np.isfinite(x).all():
        raise ValueError(f"Expected at least {minimum} finite one-dimensional observations")
    if np.any(x <= -1):
        raise ValueError("Simple returns must be greater than -1")
    return x


def effective_sample_size(values, max_lag=None):
    """Positive-sequence autocorrelation approximation, conservatively capped at n."""
    x = series(values)
    centered = x - x.mean()
    variance = float(centered @ centered)
    if variance == 0:
        return 1.0
    lag = min(len(x) // 4, max_lag or max(1, round(len(x) ** (1 / 3))))
    inflation = 1.0
    for k in range(1, lag + 1):
        rho = float(centered[k:] @ centered[:-k] / variance)
        if rho <= 0:
            break
        inflation += 2 * (1 - k / len(x)) * rho
    return max(1.0, min(float(len(x)), len(x) / inflation))


def sharpe_probability(values, reference=0.0, effective_n=None):
    """PSR: nonannualized Sharpe; normal approximation with observed skew/kurtosis."""
    x = series(values)
    sigma = float(x.std(ddof=1))
    if sigma <= 1e-15:
        return {"probability": None, "reason": "zero_return_variance"}
    sr = float(x.mean() / sigma)
    z = (x - x.mean()) / float(x.std(ddof=0))
    skew, kurt = float(np.mean(z**3)), float(np.mean(z**4))
    n = float(effective_n if effective_n is not None else len(x))
    if not 1 < n <= len(x) or not math.isfinite(reference):
        return {"probability": None, "reason": "insufficient_effective_observations"}
    denominator = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if denominator <= 0:
        return {"probability": None, "reason": "invalid_moment_approximation"}
    statistic = (sr - reference) * math.sqrt(n - 1) / math.sqrt(denominator)
    return {
        "probability": NORMAL.cdf(statistic),
        "daily_sharpe": sr,
        "annualized_sharpe": sr * math.sqrt(252),
        "reference_daily_sharpe": reference,
        "skewness": skew,
        "kurtosis": kurt,
        "effective_n": n,
        "assumption": "moment/normal approximation; effective-n substitution is heuristic",
    }


def deflated_sharpe(values, tested_variants):
    """Null SR variance approximation, conservatively using all recorded hypotheses."""
    if type(tested_variants) is not int or tested_variants < 1:
        raise ValueError("tested_variants must be positive")
    x = series(values)
    n = effective_sample_size(x)
    if n <= 1:
        return {"probability": None, "reason": "insufficient_effective_observations"}
    if tested_variants == 1:
        reference = 0.0
    else:
        gamma = 0.5772156649015329
        expected_max = (1 - gamma) * NORMAL.inv_cdf(1 - 1 / tested_variants)
        expected_max += gamma * NORMAL.inv_cdf(1 - 1 / (tested_variants * math.e))
        # Assumes null SR dispersion ~1/sqrt(n_eff-1); not measured strategy dispersion.
        reference = expected_max / math.sqrt(n - 1)
    return {
        **sharpe_probability(x, reference, n),
        "tested_variants": tested_variants,
        "null_dispersion_assumption": "independent Gaussian null SRs; conservative count",
    }


def fdr_adjust(pvalues, *, dependence=True, family_size=None):
    """Benjamini-Yekutieli by default; BH only under independence/positive dependence."""
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("p-values must be finite probabilities")
    m = len(p) if family_size is None else family_size
    if type(m) is not int or m < len(p):
        raise ValueError("Family size must include every supplied test")
    if not len(p):
        return []
    factor = sum(1 / k for k in range(1, m + 1)) if dependence else 1.0
    order = np.argsort(p, kind="stable")
    adjusted = np.minimum.accumulate((p[order] * m * factor / np.arange(1, len(p) + 1))[::-1])[::-1]
    result = np.empty(len(p))
    result[order] = np.minimum(adjusted, 1)
    return result.tolist()


def bootstrap_indices(n, block_length, rng, method="stationary"):
    if type(n) is not int or type(block_length) is not int or not 1 <= block_length <= n:
        raise ValueError("Block length must be a session count between 1 and sample size")
    if method not in ("moving_block", "stationary"):
        raise ValueError("Use moving_block or stationary bootstrap")
    if method == "moving_block":
        starts = rng.integers(0, n - block_length + 1, size=math.ceil(n / block_length))
        return np.concatenate([np.arange(s, s + block_length) for s in starts])[:n]
    indices = np.empty(n, dtype=int)
    indices[0] = rng.integers(n)
    for i in range(1, n):
        indices[i] = (
            rng.integers(n) if rng.random() < 1 / block_length else (indices[i - 1] + 1) % n
        )
    return indices


def path_metrics(values):
    x = series(values)
    equity = np.r_[1.0, np.cumprod(1 + x)]
    sigma = float(x.std(ddof=1))
    return {
        "mean_daily_return": float(x.mean()),
        "total_return": float(equity[-1] - 1),
        "sharpe": float(x.mean() / sigma * math.sqrt(252)) if sigma > 1e-15 else None,
        "maximum_drawdown": float(np.min(equity / np.maximum.accumulate(equity) - 1)),
    }


def uncertainty(
    folds, *, replications=500, block_length=10, seed=42, method="stationary", level=0.95
):
    if type(replications) is not int or not 100 <= replications <= 10000 or not 0 < level < 1:
        raise ValueError("Use 100–10000 replications and a confidence level in (0,1)")
    arrays = [series(f) for f in folds]
    if not arrays or any(len(x) < block_length for x in arrays):
        raise ValueError("Every fold needs at least one full block")
    rng = np.random.default_rng(seed)
    original = path_metrics(np.concatenate(arrays))
    draws, example_paths = [], []
    for replication in range(replications):
        sample = np.concatenate(
            [x[bootstrap_indices(len(x), block_length, rng, method)] for x in arrays]
        )
        draws.append(path_metrics(sample))
        if replication < 3:
            example_paths.append(np.r_[1.0, np.cumprod(1 + sample)].tolist())
    alpha = (1 - level) / 2
    intervals = {}
    for key in original:
        values = [d[key] for d in draws if d[key] is not None]
        intervals[key] = np.quantile(values, [alpha, 1 - alpha]).tolist() if values else None
    return {
        "observed": original,
        "example_normalized_paths": example_paths,
        "drawdown_path_quantiles": np.quantile(
            [d["maximum_drawdown"] for d in draws], [0.01, 0.05, 0.5, 0.95, 0.99]
        ).tolist(),
        "drawdown_quantile_levels": [0.01, 0.05, 0.5, 0.95, 0.99],
        "percentile_intervals": intervals,
        "replications": replications,
        "block_length_sessions": block_length,
        "method": method,
        "seed": seed,
        "confidence_level": level,
        "resampling": "within fold; fold order fixed; daily paths chain normalized fold returns",
        "interpretation": "conditional historical uncertainty/path simulations, not forecasts",
    }


def search_complexity(matrix, recorded_variants):
    x = np.asarray(matrix, dtype=float)
    if x.ndim != 2 or len(x) < 3 or x.shape[1] < 1 or not np.isfinite(x).all():
        raise ValueError("Expected aligned finite session-by-strategy matrix")
    active = x[:, x.std(axis=0) > 1e-15]
    effective = None
    if active.shape[1]:
        correlation = np.atleast_2d(np.corrcoef(active, rowvar=False))
        eigenvalues = np.maximum(np.linalg.eigvalsh(correlation), 0)
        effective = float(eigenvalues.sum() ** 2 / (eigenvalues @ eigenvalues))
    return {
        "recorded_variants": recorded_variants,
        "observed_return_series": x.shape[1],
        "effective_rank_diagnostic": effective,
        "note": (
            "correlation participation ratio is diagnostic; "
            "failed/unobserved variants remain in correction count"
        ),
    }


def max_test_bootstrap(fold_matrices, *, replications=500, block_length=10, seed=42):
    """One-sided centered common-index block max-t bootstrap across observed family."""
    matrices = [np.asarray(f, dtype=float) for f in fold_matrices]
    if not matrices or any(f.ndim != 2 or len(f) < block_length for f in matrices):
        raise ValueError("Need aligned fold matrices and complete blocks")
    if any(f.shape[1] != matrices[0].shape[1] or not np.isfinite(f).all() for f in matrices):
        raise ValueError("Inconsistent strategy columns or nonfinite returns")
    if not 100 <= replications <= 10000:
        raise ValueError("Use 100–10000 replications")
    x = np.concatenate(matrices)
    scale = x.std(axis=0, ddof=1)
    means = x.mean(axis=0)
    active = scale > 1e-15
    se = np.where(active, scale / math.sqrt(len(x)), 1)
    observed = means / se
    # Global null centering preserves relative regime offsets, unlike per-fold centering.
    centered = [f - means for f in matrices]
    rng = np.random.default_rng(seed)
    maxima, marginal = [], []
    for _ in range(replications):
        draw = np.concatenate([f[bootstrap_indices(len(f), block_length, rng)] for f in centered])
        statistics = draw.mean(axis=0) / se
        statistics[~active] = 0
        marginal.append(statistics)
        maxima.append(float(np.max(statistics)))
    raw = (1 + np.sum(np.asarray(marginal) >= observed, axis=0)) / (replications + 1)
    adjusted = (1 + np.sum(np.asarray(maxima)[:, None] >= observed, axis=0)) / (replications + 1)
    raw[~active] = adjusted[~active] = 1
    return {
        "pvalues": raw.tolist(),
        "familywise_pvalues": adjusted.tolist(),
        "replications": replications,
        "block_length_sessions": block_length,
        "seed": seed,
        "null": "all mean daily benchmark-relative returns <= 0",
        "method": (
            "centered stationary-block max-t, common indices across strategies; "
            "fixed observed scaling"
        ),
    }
