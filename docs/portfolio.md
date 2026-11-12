# Multi-strategy portfolios and risk management

Milestone 6 builds on the existing event-driven cash-equity engine. It does not
promote the rejected Milestone 5 candidates or enable live execution. See the
[unaltered request](milestone-6-instructions.md), [Stooq recheck](stooq-reverification.md)
and [recorded results](milestone-6-results.md).

## Architecture and accounting

`portfolio.book.MultiStrategyBook` implements the existing `Strategy` interface.
Optional replay lifecycle hooks initialize attribution, check opening risk,
record actual fills, mirror corporate actions and reconcile daily accounts.
Strategies without hooks retain the original behavior. Each registered strategy
receives an allocation-budget view plus only currently available bar history.
ML and conventional strategies both use the existing long-share target interface.

There is **one authoritative funded account**. Strategy ledgers are virtual
ownership/cash claims, not additional cash pools. Their initial endowments sum
to the account's initial cash. Dynamic weights change permitted position budgets;
they do not invent cash deposits or rewrite historic P&L. Internal cash claims
may be negative when another strategy finances a position, but shared cash must
remain nonnegative. Only the authoritative account determines buying power.

Opposing target changes can cross ownership of an existing position at the known
mark, with no external fill or duplicated fee. Residual orders net by symbol.
After actual external fills, quantity and commission/spread/slippage amounts are
attributed proportionally to outstanding strategy demand; the final portion
absorbs Decimal rounding. Rejections never create virtual fills. Splits and
dividend entitlements/payments propagate to each owner. Cash, receivables, asset
quantities and equity reconcile at every internal cross and daily mark.
Strategy total P&L sums to total account P&L. Internal crosses can reclassify
realized versus unrealized P&L at strategy level, so those two subcomponents
separately need not equal the combined account's average-cost classifications.

Execution remains long-only USD daily cash equities, using the strictly later
eligible opening print. Strategy ownership claims can be fractional after
proportional attribution; external risk-approved orders use whole shares.
Futures margin/short accounting requires its own adapter (Milestone 7), not
reuse of the cash-equity assumptions.

## Allocation and causal estimates

Supported methods are equal, fixed, inverse volatility, risk parity and
volatility targeting. Fixed weights must be nonnegative and sum to at most one.
Covariance uses aligned trailing observations, diagonal shrinkage and a small
positive regularizer. Risk parity solves a convex coordinate-descent risk-budget
problem; constraints/caps can change the final contributions and leave residual
capital in cash. Volatility targeting scales down, never borrows to reach a
nominal target. Expected-return optimization is deliberately deferred.

Insufficient, nonfinite or zero-variance history produces an explicit cash-only
fallback for covariance methods. The real demo supplies separately evaluated
individual-strategy return histories with explicit `available_at` timestamps.
At allocation time, only observations available by the replay clock are used;
future observations cannot affect current weights. Without reference histories,
actual virtual-ledger return history is used. Allocation logs preserve weights,
cash reserve, covariance and fallback reasons.

This is walk-forward allocation of previously discovered strategies on permitted
validation data, not independently unseen portfolio confirmation. Reference
returns are standalone strategy opportunities; allocated virtual-ledger returns
are separately reported. Historic correlation, risk parity and covariance
regularization do not guarantee diversification.

## Sizing, risk and suspension

Sizing helpers support target weight, fixed fractional, volatility-adjusted,
ATR and risk-budget sizing with explicit price, multiplier, lot size, buying
power and cost inputs. Book-level optional sizing uses only available history;
insufficient risk history blocks increases. Allocation-budget and account-wide
caps still apply afterward.

Before accepting targets, rules bound per-position, sector, correlated group,
strategy allocation, gross/net exposure and leverage. Unknown sectors share a
conservative common bucket. Correlated groups use observed past symbol returns.
Equity leverage above one and negative equity targets are rejected. Cosmetic
increases below minimum notional/weight thresholds are suppressed; projected
transaction costs can also suppress uneconomic increases. Risk reductions are
permitted under the configured turnover and risk policy.

Before fills, rules reevaluate aggregate exposure at **actual opening prices**,
check opening loss/drawdown, enforce actual shared buying power including fees,
and cap opening turnover. Optional participation limits use only previously
published volume, never the completed volume of the execution day. A documented
research execution-unavailable/rejection switch exercises failure paths.
Structured decisions state APPROVED, REDUCED or REJECTED with requested/approved
quantity and reasons. Gaps can breach existing marked exposure before any new
order; reducing risk is allowed, but no model can guarantee avoiding gap losses.

Daily loss breaches block increases at the next scheduled decision. Lifetime
and trailing 63-session strategy drawdowns are recorded; a strategy breach
suspends increases while permitting reductions. Portfolio drawdown triggers a
**one-time fractional position cap**, applied on subsequent rebalances; the cap
persists until manual reset rather than repeatedly halving positions to zero.
There is no arbitrary immediate full liquidation. Manual strategy reactivation
and portfolio reset require explicit approval and a reason, both logged.

Daily/weekly/monthly and threshold rebalancing support minimum notionals, weight
thresholds, turnover limits, cash buffers and cost filters. Stable strategy/name
ordering makes allocation and fill attribution reproducible. Paper mode requires
both a validated research status and an explicit per-strategy approval boolean;
research mode retains rejected/insufficient/research-only labels. Live mode is
unavailable. Suspension and reactivation do not promote research eligibility.

## Reports, stress and commands

Reports include individual and combined returns, Sharpe/Sortino, volatility,
drawdown, turnover, costs, benchmark comparisons, strategy P&L, allocation logs,
risk decisions, internal transfers, rolling correlations, covariance, marginal
risk contributions, concentration, exposure overlap and stressed-loss correlation.
Period correlation comparisons expose instability; missing history is explicit.

Executed stress runs include doubled costs, prior-volume participation caps,
rejected orders and unavailable execution. Additional analytical scenarios label
doubled volatility, perfect loss correlation, overnight gaps and strategy
underperformance as **hypothetical diagnostics, not forecasts**. Missing daily
sessions are rejected by ingestion/synchronized-feed validation; missing data is
not forward-filled into tradable observations. No broker connection is used.

```bash
uv sync --frozen --all-extras
uv run --frozen --all-extras python examples/portfolio_demo.py --output data/portfolios/NEW_RUN --stress
uv run --frozen --all-extras quantlab portfolio backtest --portfolio-config configs/portfolio.example.yaml --output data/portfolios/ANOTHER_RUN
uv run --frozen --all-extras quantlab portfolio risk --report data/portfolios/NEW_RUN
uv run --frozen --all-extras quantlab portfolio strategies --report data/portfolios/NEW_RUN
uv run --frozen --all-extras quantlab portfolio report --report data/portfolios/NEW_RUN
```

Use `portfolio create --output-config PATH --source-validation REPORT
--verified-inputs DIRECTORY --start YYYY-MM-DD --end YYYY-MM-DD` to create an
empty research configuration. `portfolio register --portfolio-config PATH
--strategy-id ID --name NAME` registers an evaluated candidate with paper approval
false. `portfolio allocate --portfolio-config PATH --method METHOD` assigns a
baseline method. Invalid registration preserves the previous file. Configuration
writes are atomic. YAML paths resolve relative to the configuration file.

The populated [example](../configs/portfolio.example.yaml) references retained M5
prediction artifacts and verified 2014–2018 inputs. Routine jobs check the current
holdout ledger and reject any input period reaching the final cutoff. Output
directories are immutable; choose a new one rather than overwrite evidence.
Raw vendor data, model files and local reports stay under ignored `data/`.
