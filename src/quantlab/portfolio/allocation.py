"""Past-only regularized covariance and transparent baseline capital allocations."""

import numpy as np


def covariance(history, *, minimum=20, lookback=126, shrinkage=0.2):
    x = np.asarray(history, dtype=float)
    if x.ndim != 2 or not np.isfinite(x).all() or x.shape[0] < minimum or x.shape[1] < 1:
        raise ValueError("Insufficient aligned finite strategy history")
    if not 0 <= shrinkage <= 1:
        raise ValueError("Shrinkage must be in [0,1]")
    x = x[-lookback:]
    if np.any(np.std(x, axis=0, ddof=1) <= 1e-12):
        raise ValueError("Zero-variance history does not identify strategy volatility")
    raw = np.atleast_2d(np.cov(x, rowvar=False, ddof=1))
    return (
        (1 - shrinkage) * raw
        + shrinkage * np.diag(np.maximum(np.diag(raw), 1e-12))
        + np.eye(x.shape[1]) * 1e-12
    )


def allocate(
    names,
    history,
    *,
    method="equal",
    fixed=None,
    cash_buffer=0.1,
    maximum_weight=0.6,
    target_volatility=0.12,
    risk_budgets=None,
    minimum=20,
):
    n = len(names)
    if n < 1 or not 0 <= cash_buffer < 1 or not 0 < maximum_weight <= 1 or target_volatility <= 0:
        raise ValueError("Invalid allocation bounds")
    cov = None
    note = None
    if method == "fixed":
        if (
            fixed is None
            or set(fixed) != set(names)
            or any(not np.isfinite(v) or v < 0 for v in fixed.values())
            or sum(fixed.values()) > 1
        ):
            raise ValueError("Fixed weights must cover strategies, be nonnegative and sum <= 1")
        weights = np.array([fixed[s] for s in names], dtype=float)
    elif method == "equal":
        weights = np.ones(n) / n
    elif method in ("inverse_volatility", "risk_parity", "volatility_target"):
        try:
            cov = covariance(history, minimum=minimum)
        except ValueError:
            # Explicit conservative cash fallback; no noisy backfilled performance.
            return {
                "weights": dict.fromkeys(names, 0.0),
                "cash_weight": 1.0,
                "note": "insufficient_history_cash",
                "covariance": None,
            }
        vol = np.sqrt(np.diag(cov))
        weights = 1 / vol
        weights /= weights.sum()
        if method == "risk_parity":
            budget = (
                np.ones(n) / n
                if risk_budgets is None
                else np.asarray([risk_budgets[s] for s in names], dtype=float)
            )
            if not np.isfinite(budget).all() or np.any(budget <= 0):
                raise ValueError("Risk budgets must be positive")
            budget /= budget.sum()
            # Coordinate descent solves .5*x*C*x - sum(b_i log x_i).
            x = np.ones(n)
            for _ in range(1000):
                previous = x.copy()
                for i in range(n):
                    cross = cov[i] @ x - cov[i, i] * x[i]
                    x[i] = (-cross + np.sqrt(cross**2 + 4 * cov[i, i] * budget[i])) / (
                        2 * cov[i, i]
                    )
                if np.max(abs(x - previous)) < 1e-10:
                    break
            weights = x / x.sum()
    else:
        raise ValueError("Unsupported allocation method")
    weights = weights * min(1, (1 - cash_buffer) / max(weights.sum(), 1e-15))
    weights = np.minimum(weights, maximum_weight)
    if method == "volatility_target" and cov is not None:
        current = np.sqrt(weights @ cov @ weights * 252)
        weights *= min(1, target_volatility / max(current, 1e-12))
    # Never lever up to achieve a target; capped residual stays in cash.
    return {
        "weights": dict(zip(names, map(float, weights), strict=True)),
        "cash_weight": float(1 - weights.sum()),
        "note": note,
        "covariance": cov.tolist() if cov is not None else None,
    }


def diversification(history, weights):
    try:
        cov = covariance(history, minimum=3)
    except ValueError:
        return {"status": "insufficient_history"}
    w = np.asarray(weights, dtype=float)
    variance = float(w @ cov @ w)
    vol = np.sqrt(np.diag(cov))
    corr = cov / np.outer(vol, vol)
    contribution = w * (cov @ w) / variance if variance > 0 else np.zeros(len(w))
    x = np.asarray(history)
    losses = x[np.any(x < -0.01, axis=1)]
    stress = (
        np.corrcoef(losses, rowvar=False).tolist()
        if len(losses) > 2 and np.all(np.std(losses, axis=0) > 0)
        else None
    )
    midpoint = len(x) // 2
    periods = []
    for block in (x[:midpoint], x[midpoint:]):
        periods.append(
            np.atleast_2d(np.corrcoef(block, rowvar=False)).tolist()
            if len(block) > 2 and np.all(np.std(block, axis=0) > 0)
            else None
        )
    return {
        "covariance": cov.tolist(),
        "correlation": corr.tolist(),
        "annualized_volatility": float(np.sqrt(variance * 252)),
        "risk_contributions": contribution.tolist(),
        "risk_concentration": float(np.sum(contribution**2)),
        "diversification_ratio": float(w @ vol / np.sqrt(variance)) if variance > 0 else None,
        "stressed_loss_correlation": stress,
        "period_correlations": periods,
    }
