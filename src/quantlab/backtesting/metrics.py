"""Session-based performance metrics; undefined ratios are null, never infinity."""

import math
import statistics


def performance(rows: list[dict], trades: list[dict], initial_cash, sessions_per_year: int) -> dict:
    initial = float(initial_cash)
    equity = [float(row["equity"]) for row in rows]
    returns = []
    previous = peak = initial
    maximum_drawdown = 0.0
    for row, value in zip(rows, equity, strict=True):
        if previous == 0 and value != 0:
            raise ValueError("External cash flows after zero equity require time-weighted returns")
        change = value / previous - 1 if previous else 0.0
        returns.append(change)
        peak = max(peak, value)
        drawdown = value / peak - 1
        maximum_drawdown = min(maximum_drawdown, drawdown)
        row["daily_return"] = change
        row["drawdown"] = drawdown
        previous = value
    deviation = statistics.stdev(returns) if len(returns) > 1 else 0.0
    mean = statistics.mean(returns)
    downside = math.sqrt(statistics.mean(min(r, 0) ** 2 for r in returns))
    try:
        annualized = (
            math.expm1(math.log(equity[-1] / initial) * sessions_per_year / len(rows))
            if equity[-1]
            else -1.0
        )
    except (OverflowError, ValueError):
        annualized = None
    exits = [float(t["realized_pnl"]) for t in trades if t["side"] == "sell"]
    profits = sum(max(pnl, 0) for pnl in exits)
    losses = abs(sum(min(pnl, 0) for pnl in exits))
    notional = sum(float(t["price"] * t["quantity"]) for t in trades)
    return {
        "sessions": len(rows),
        "total_return": equity[-1] / initial - 1,
        "annualized_return": annualized,
        "sharpe_ratio": mean / deviation * math.sqrt(sessions_per_year) if deviation else None,
        "sortino_ratio": mean / downside * math.sqrt(sessions_per_year) if downside else None,
        "annualized_volatility": deviation * math.sqrt(sessions_per_year),
        "calmar_ratio": annualized / abs(maximum_drawdown)
        if annualized is not None and maximum_drawdown
        else None,
        "maximum_drawdown": maximum_drawdown,
        "gross_turnover": notional / statistics.mean(equity),
        "average_gross_exposure": statistics.mean(float(row["gross_exposure"]) for row in rows),
        "time_in_market": sum(row["quantity"] > 0 for row in rows) / len(rows),
        "fill_count": len(trades),
        "exit_fill_count": len(exits),
        "win_rate": sum(pnl > 0 for pnl in exits) / len(exits) if exits else None,
        "profit_factor": profits / losses if losses else None,
        "average_exit_pnl": statistics.mean(exits) if exits else None,
        "final_equity": rows[-1]["equity"],
        "realized_pnl": rows[-1]["realized_pnl"],
        "unrealized_pnl": rows[-1]["unrealized_pnl"],
        "dividend_income": rows[-1]["dividend_income"],
        "commissions": rows[-1]["commissions"],
        "spread_cost": rows[-1]["spread_cost"],
        "slippage_cost": rows[-1]["slippage_cost"],
        "market_impact_cost": rows[-1].get("market_impact_cost", 0),
        "turnover_definition": "sum_absolute_executed_notional_over_mean_equity; two_way",
    }
