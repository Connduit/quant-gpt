"""Observable execution diagnostics without empirical live-performance claims."""

import statistics

from quantlab.backtesting.models import decimal
from quantlab.backtesting.report import dumps


def report(runtime):
    v = runtime.account.view()
    s = runtime.state
    rows = s["equity_history"]
    peak = float(s["configuration"]["capital"])
    dd = 0
    by_day = {}
    for row in rows:
        e = float(row["equity"])
        peak = max(peak, e)
        dd = max(dd, 1 - e / peak)
        by_day[row["at"][:10]] = e
    previous = float(s["configuration"]["capital"])
    returns = []
    for e in by_day.values():
        returns.append(e / previous - 1)
        previous = e
    sharpe = None
    if len(returns) >= 30 and statistics.stdev(returns) > 0:
        sharpe = statistics.mean(returns) / statistics.stdev(returns) * 252**0.5
    matured = [p["accuracy"] for p in s["predictions"] if p["accuracy"] is not None]
    closed = [
        float(f["realized_closed_pnl"])
        for f in runtime.account.fills
        if f.get("realized_closed_pnl") is not None and float(f["realized_closed_pnl"]) != 0
    ]
    return {
        "closed_fill_win_rate": sum(x > 0 for x in closed) / len(closed) if closed else None,
        "matured_prediction_count": len(matured),
        "execution_mode": "SIMULATED",
        "data_mode": runtime.mode,
        "experimental": any(x["deployment"] == "RESEARCH" for x in s["strategies"].values()),
        "live_stream_verified": False,
        "account": v,
        "drawdown": dd,
        "daily_observations": len(returns),
        "daily_returns": returns,
        "sharpe": sharpe,
        "sharpe_note": "Unavailable below 30 daily observations; not proof of profitability",
        "cumulative_pnl": v["equity"] - decimal(s["configuration"]["capital"]),
        "connected": s["connected"],
        "killed": s["killed"],
        "strategies": s["strategies"],
        "orders": [o.payload() for o in runtime.orders.values()],
        "fills": runtime.account.fills,
        "equity_history": rows,
        "predictions": s["predictions"],
        "alerts": s["alerts"],
        "model_accuracy": statistics.mean(matured) if matured else None,
        "model_accuracy_note": "Matured quote-event direction accuracy; serial dependence remains",
        "limitations": [
            "Displayed quote liquidity is not guaranteed executable.",
            "Replay is not real-time paper evidence.",
            "All risk/margin/fee settings are explicit assumptions.",
            "No strategy is automatically promoted; no live order capability.",
        ],
    }


def compare(reference, observed):
    """Compare supplied measurements; causal explanations require separate evidence."""
    fields = ("signals", "fills", "fees", "turnover", "gross", "equity", "prediction_mean")
    result = {}
    for k in fields:
        a, b = reference.get(k), observed.get(k)
        result[k] = {
            "reference": a,
            "observed": b,
            "difference": b - a
            if isinstance(a, (int, float)) and isinstance(b, (int, float))
            else None,
            "equal": a == b if a is not None and b is not None else None,
        }
    return {
        "comparison": result,
        "reference_mode": reference.get("mode"),
        "observed_mode": observed.get("mode"),
        "causes": "Not established by numerical differences alone",
        "investigate": [
            "timestamps",
            "latency",
            "spread/slippage",
            "data gaps",
            "granularity",
            "model/data versions",
            "software errors",
        ],
        "no_independent_profitability_evidence": True,
    }


def export(runtime, path):
    path.write_text(dumps(report(runtime)) + "\n")
