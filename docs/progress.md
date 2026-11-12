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
| 3 — Feature engineering and ML | Implemented: 46 default causal features, execution-aligned targets, purged walk-forward folds, five CPU model families, OOS ranking portfolios, comparisons and exports. See verification below. |
| 4 — Automated strategy discovery | Implemented: bounded Optuna search, local MLflow, immutable registry, resource isolation, eligibility and robustness. See results below. |
| 5 — Statistical validation | Implemented: interval checks, advanced folds, holdout-use ledger, bootstrap uncertainty, Sharpe/search corrections, robustness and conservative status reports. |
| 6 — Portfolio construction and risk management | Implemented for cash equities: shared account, strategy attribution/netting, baseline allocations, risk/sizing, suspensions, rebalancing and stress reports. |
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

## Milestone 3 verification and scope

The [full request](milestone-3-instructions.md) is saved unchanged. The
[ML research guide](ml-research.md) documents features, labels, publication-time
purging, model APIs, YAML, ranking controls, artifacts and limitations. The
single-stock interfaces and all 93 previous tests are preserved. `MarketData`
adds synchronized daily feeds sharing the existing cash and corporate-action ledger.

**135 tests passed** (93 existing plus 42 new). Lint/formatting and the source/wheel
build passed. All five CPU model families trained in the end-to-end demonstration;
regression/classification variants, serialization, loading and seed reproducibility
were also tested. There are no GPU requirements or enabled live orders.

An independently installed wheel reproduced the checkout's predictive/trading
metrics and OOS prediction artifact exactly.

The default synthetic experiment ran four folds and produced 402 OOS stock/session
predictions per model, with 50 final sessions reserved and not evaluated. It
reported that ML did not outperform the strongest simpler baseline after costs.
These are synthetic functional results, not a verified trading advantage. No
appropriate real raw-price/action dataset was available for a real-data integration
demonstration. Supplied static universes can have survivorship bias; source data
is not independently certified point-in-time.

## Milestone 4 verification and scope

The [full instructions](milestone-4-instructions.md) and [data requirements](milestone-4-data-instructions.md) are preserved. The [discovery guide](discovery.md) explains the implementation; [recorded results](milestone-4-results.md) and [dataset manifest](milestone-4-datasets.json) document the real run.

**170 tests passed**, preserving all prior tests. Lint, formatting and package builds passed. Four optimizer trials and six diagnostic variants ran on seven historical stocks plus SPY (2014–2019); zero candidates qualified. The final 252 sessions in 2019 remained inaccessible to trials. Explicit factor-file proxies have incomplete corporate-action coverage and unknown payment dates; this is not a fully corporate-action-aware demonstration. Milestone 5 now adds statistical diagnostics; see verification below.

## Milestone 5 verification and scope

The [full request](milestone-5-instructions.md), [audit](statistical-validation-audit.md), [methodology](statistical-validation.md) and [actual results](milestone-5-results.md) are recorded. **197 tests passed**, three live tests skipped by default; the explicit live run passed all three. Lint, formatting and package builds passed. Four real-data candidates and eight distinct robustness scenarios were rejected. No candidate qualifies for paper trading. All 252 reserved 2019 sessions remained unevaluated; the holdout ledger is SEALED. Action/universe certification and independent confirmation remain missing. Milestone 6 is not implemented in this verification.

## Milestone 6 verification and scope

The [full instructions](milestone-6-instructions.md), [design](portfolio.md), [results](milestone-6-results.md) and [Stooq runtime recheck](stooq-reverification.md) are preserved. **218 tests passed**, three live checks skipped by default. Nine real-data portfolio/stress runs reconciled attribution. Equal weighting returned -3.339%, inverse volatility -5.154%, versus SPY +12.093% in the selected 2017–2018 period. Both evaluated candidates remain rejected/research-only, with no final holdout access or paper promotion. Later milestone requests are saved and queued in order.

## Milestone 7 verification and scope

[Actual results](milestone-7-results.md): 250 offline tests passed, four optional
real-download checks passed. Real ESZ13 minute data were downloaded and stored;
four ML trials and five controls completed. All rejected; two OOS sessions are
insufficient for statistical eligibility. Holdouts remain untouched. No live feed,
paid Databento access, certified historical margins, or paper eligibility verified.

## Milestone 8 verification and scope

[Actual replay results](milestone-8-results.md), [operation](paper-trading.md):
278 tests passed, five optional network tests skipped. The real ES archival replay
recorded 99 simulated fills, $348.48 fees and $98,882.77 ending equity. Its daily
loss halt remained active across a reconciled restart; duplicate events created
no extra fills. The installed wheel reconstructed all account metrics exactly.
No authenticated streaming was verified, no strategies qualify for validated
paper deployment, and no real-money submission capability exists.

## Milestone 9 verification and scope

[Dashboard operation](dashboard.md) and [actual verification](milestone-9-results.md):
287 Python tests, five frontend tests and five Chromium browser tests passed.
The API reads curated actual artifacts and journal-verified paper state. No live
controls, automatic promotions, raw holdout browsing or arbitrary execution exists.
External streaming/brokers and real-time paper eligibility remain unverified.

## Milestone 10 verification and scope

[Architecture](research-agent.md) and [results](milestone-10-results.md): 303 Python
tests, five frontend tests and six Chromium browser tests passed. Two bounded
real-data investigations made 12 recorded attempts; all rejected, with canonical
holdout state SEALED. The installed 0.10 wheel matched executed policy/source
identity. Planning was scripted engineering; no external LLM or generated-code
sandbox was verified. No eligible paper/live strategy or trading authority granted.

## Milestone 11 verification and scope

[Execution design](controlled-execution.md), [actual verification](milestone-11-results.md),
[production operation](production.md), [incident response](incident-response.md),
and [independent readiness report](go-live-readiness.md) are saved. **326 Python
tests passed**, seven optional checks skipped; the explicit archive run passed four
real-download checks. Five frontend and seven real Chromium browser tests passed.
The installed wheel matched source/accounting. The digest-pinned nonroot/read-only
container built and passed mock recovery, frontend and authenticated API checks.

The explicit mock broker demo verified uncertain acceptance without retry,
partials/duplicates, restart reconciliation, outage, kill/cancellation and backups.
External Alpaca PAPER/Stooq/data requests remain proxy-403 blocked in the older
runtime; credentials are missing. No external broker routing or real-time paper
record is claimed, no strategy qualifies, and no final holdout was consumed.
**LIVE remains disabled.** No Milestone 12 starts automatically.
