# Development progress and current roadmap

The original [blueprint](blueprint.md) remains the master product specification.
The full [post-Milestone 1 development instructions](development-instructions.md)
update the roadmap to **11 development milestones**. These supersede the original
10-milestone numbering from Milestone 5 onward. Market phases (equities, futures,
additional markets) and the blueprint's 12 core capabilities are separate concepts.

| Milestone | Status |
| --- | --- |
| 1 — Foundation and historical data infrastructure | Implemented and audited; original 47 tests preserved. Real Stooq connectivity remains unverified in this cloud environment; raw CSV import now available. |
| 2 — Event-driven backtesting | Implemented for daily one-instrument long-only USD cash equities, with action accounting, causal replay, baseline strategies, benchmark and exports. See verification below. |
| 3 — Feature engineering and ML | Not started; awaiting user instruction. |
| 4 — Automated strategy discovery | Not started. |
| 5 — Statistical validation | Not started as a full subsystem. Essential causal/timing safeguards are already enforced in Milestone 2. |
| 6 — Portfolio construction and risk management | Not started. Milestone 2 enforces only its cash/long-only account constraints. |
| 7 — Futures research | Not started. |
| 8 — Paper trading | Not started. |
| 9 — Dashboard | Not started. |
| 10 — AI research agent | Not started. |
| 11 — Controlled live execution | Not started; live trading remains unavailable and requires future explicit authorization. |

## Milestone 2 deliverables

- [Architecture audit](architecture-audit.md) maps all 12 capabilities to current
  boundaries and deferred work; existing working modules are preserved.
- Immutable target signals, explicit market orders/statuses, opening-print fills
  and read-only strategy contexts.
- Chronological open/close/availability/action replay; no same-close/same-open fills
  from newly observed daily data and no unavailable close leakage via account views.
- Configurable per-share/fixed/minimum commissions, adverse spread and slippage.
- Decimal cash/cost-basis/position accounting, partial position exits, realized and
  unrealized P&L, split handling, dividend entitlements, receivables and payments.
- Explicit raw CSV import and adjustment/action-coverage guards.
- Momentum, mean reversion and buy-and-hold; identical-period cost-aware benchmarks.
- Atomic, versioned-by-content reports, exact trade/position/equity histories,
  performance metrics, provenance and artifact checksums.
- [Runnable demonstration and assumptions](backtesting.md).

Verification: **93 tests passed** (the original 47 plus 46 new tests), Ruff lint
and formatting passed, and both source distribution and wheel built successfully.
The end-to-end demonstration produced two momentum fills, one mean-reversion
fill and one buy-and-hold fill, with exported reports for each. The installed
wheel was also exercised outside the checkout against the verified fixture snapshot.
Third-party exchange-calendars/Pandas deprecation warnings remain; they do not
represent failed tests or suppressed assertions.

Tests use explicitly synthetic fixtures; no profitability claim or verified real-data
backtest is made. Limits include single-instrument daily full market fills,
caller-asserted raw/action semantics and no certified point-in-time universe.

Next milestone, only after user review: causal feature engineering, forward
labels, chronological/purged training datasets, baseline regressions, tree models
and ML ranking. No ML training has been added in Milestone 2.
