# Milestone 6 results

The multi-strategy portfolio ran on **503 real historical sessions, January 3, 2017–December 31, 2018**, using verified LEAN pre-holdout snapshots and two independently evaluated M5 prediction books. Both candidates remain **REJECTED / research-only**; no strategy qualifies for paper allocation. The current holdout ledger remained sealed and no 2019 data was accessed.

The [Stooq recheck](stooq-reverification.md) still found proxy 403 errors in the older running environment (observed revision 1). Stooq-specific verification remains blocked pending an applied runtime allowlist. The verified alternative and incomplete factor-action/universe limitations are unchanged.

| Portfolio / stress | Total return | Max drawdown | Fills |
| --- | ---: | ---: | ---: |
| equal | -3.339% | -13.510% | 72 |
| equal_disconnected | 0.000% | 0.000% | 0 |
| equal_double_costs | -3.592% | -13.746% | 74 |
| equal_liquidity | -3.333% | -13.399% | 113 |
| equal_rejected_order | -3.530% | -13.521% | 72 |
| inverse_volatility | -5.154% | -13.234% | 66 |
| inverse_volatility_double_costs | -5.453% | -13.448% | 66 |
| risk_parity | -5.154% | -13.234% | 66 |
| volatility_target | -5.154% | -13.234% | 66 |

SPY benchmark total return: **12.093%**. Individual strategy returns: excess_random_forest: -4.372%, return_xgboost: -0.604%.

These are continuously replayed portfolio accounts using saved OOS predictions, unlike M5’s separately reset fold accounts. Gaps without predictions retain existing positions under the declared rules. No result establishes a trading edge; all combined baseline methods underperformed SPY. Risk parity and volatility targeting coincided with inverse-volatility outcomes under these constraints and estimates.

Every replay reconciled strategy cash claims, receivables, quantities and total P&L with the authoritative shared account. Known-price internal crosses and actual fills have separate logs. Proportional ownership uses bounded 18-decimal share precision with exact remainder assignment; the real run uncovered and regression-tested the recurring-fraction full-exit issue. No rejected/unavailable execution produces virtual positions.

Executed stresses cover doubled costs, volume participation, order rejection and disconnected execution. Disconnected execution returned zero with no fills or phantom P&L. Hypothetical volatility, perfect loss correlation, overnight gap and degradation scenarios are labeled diagnostics, not forecasts. Missing synchronized history is rejected rather than forward-filled; no real broker is connected.

The [machine-readable report](milestone-6-results.json) records exact IDs, settings, metrics, attribution totals, risk counts, correlations and scenarios. Full local artifacts are under `data/portfolios/milestone-6-release/`: per-method equity/trades, allocations, risk decisions, internal transfers and daily strategy attribution. Raw data and model artifacts remain ignored by Git.

**218 tests passed** (all 197 previous tests plus 21 portfolio checks), three opt-in live tests skipped by default. Lint, formatting and source/wheel builds passed. An independently installed 0.6.0 wheel reproduced equal and inverse-volatility portfolio metrics and strategy attribution exactly, with a matching package source hash. Numerical tests cover cash/fees, recurring allocations, full exits, splits/dividends, position sizing, known covariance weights, exposure limits, chronology, suspensions, manual resets and CLI registration.

```bash
uv sync --frozen --all-extras
uv run --frozen --all-extras python examples/portfolio_demo.py --output data/portfolios/NEW_RUN --stress
uv run --frozen --all-extras quantlab portfolio risk --report data/portfolios/milestone-6-release
```

See [portfolio methodology](portfolio.md) and [the full request](milestone-6-instructions.md). Remaining limits are daily full-print cash-equity simulation, static survivor universe, incomplete corporate-action coverage/payment dates, historical covariance uncertainty and reused validation data. Paper approval and live execution remain disabled. Futures accounting must keep multipliers, margin, shorts, sessions, settlement and actual contract rolls separate from cash equities.
