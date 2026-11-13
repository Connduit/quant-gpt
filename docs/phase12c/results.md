# Phase 12C implementation and actual exploratory demonstration

**Status: implemented; results NOT VALIDATED, no qualified/promoted candidate.**
No live order or final-holdout authorization/evaluation occurred.

## What was demonstrated

The checkout had no retained historical library/prediction artifacts. A pasted
report alone is not replayable. The demonstration therefore fetched a fresh,
strictly bounded **2016-2018** Alpaca SIP **daily raw** history for AAPL, MSFT,
NVDA and SPY: **754 sessions per symbol**, verified by source/Parquet hashes,
OHLCV/calendar validation and source equality. The exact bounds and hashes are
in `demo/data-provenance.json`; raw archives/models remain outside Git.

Chronological exploratory Ridge fitting used a five-session horizon, 252 training,
63 validation and 126 evaluation sessions per fold, embargo/purging and seed 42.
Saved prediction/dataset hashes, fold clocks, model hashes and first eligible opens
were verified without refitting during profitability evaluation. The actual OOS
simulation covers **2017-06-29 through 2018-12-31**, 379 sessions.
It does not describe performance over the entire training period.

## Explicit trading rules

ML: rank saved available Ridge excess-price-change scores; require score >=0;
select at most two stocks; rebalance every five exchange sessions; target equal
weights capped at 40% per stock and reserve 20% cash. Exit after 20 holding
sessions, on exclusion from a rebalance, after the 20% marked-equity drawdown or
5% daily-loss stop, or at the predeclared final opening. Signals execute strictly
later, at the next eligible opening. Whole-share market orders and shared cash
with sells funding buys; pre-fill cash/exposure checks are enforced. Targets may
drift between decisions; stops do not remove gap risk.

Controls: SPY buy/hold at the same initial cash reserve; periodically equal-weight
all three supplied stocks; rank positive lagged momentum; rank negative lagged MA
distance for mean reversion; cash at 0% interest. Momentum/mean-reversion use the
same top-N, timing, holding and risk policy. SPY/equal-weight use no individual-stock
cap or active drawdown stop; exposure differences are explicitly reported. All use
the same dates, initial $100,000, scenario costs and final opening liquidation.

## Net results at baseline costs

| Strategy | Net return | Max drawdown | Sharpe | Average gross exposure |
| --- | ---: | ---: | ---: | ---: |
| ml | 35.29% | -12.90% | 1.373 | 55.91% |
| spy_buy_hold | 2.29% | -16.71% | 0.187 | 81.06% |
| equal_weight | 17.85% | -21.43% | 0.676 | 66.31% |
| momentum | 3.32% | -10.43% | 0.222 | 55.26% |
| mean_reversion | 36.30% | -5.99% | 1.808 | 24.34% |
| cash | 0.00% | 0.00% | undefined | 0.00% |

**Interpretation:** ML made simulated net money under these incomplete assumptions,
but simple mean reversion returned 36.30%,
above ML's 35.29%. This is not evidence that ML is the best strategy.
Different exposure/active stops also prevent a simple equal-risk superiority claim.
ML ended with $135,289.11; annualized return 22.26%,
annualized volatility 15.52%, Sortino 1.996,
Calmar 1.725. It generated 140 fills and 79 sell fills;
win rate 78.48%, profit factor 2.038, average exit P&L
$446.70. These count sell fills, including partial exits, not
independent round trips. Two-way turnover was 32.988x mean equity.

## Costs and sensitivity

| Scenario | ML net return | Assumption multiplier |
| --- | ---: | ---: |
| low | 36.99% | 0.5x |
| baseline | 35.29% | 1x |
| high | 32.08% | 2x |

Baseline: $0.005/share commissions, 2 bps **full** spread (half at each fill),
5 bps slippage and 1 bp fixed assumed impact. Actual executed cost totals:
commissions $150.97; spread $419.07; slippage
$2,095.36; impact $419.07; total $3,084.48.
Both entry and exit/liquidation costs are included. Cost/risk-adjusted sizing
produced 22 reduced orders and
1 rejected orders at baseline costs.
Costs are embedded once in cash/fill prices, not subtracted again from performance.
The independent zero-cost ML replay returned 38.63%;
this is gross, not net, and may hold different quantities. Nearby rebalance and
holding settings were recorded as diagnostics, not selected into a new best result.

## Drawdowns, periods and uncertainty

Daily marked net equity and drawdown are in `baseline-ml-equity.csv` and the JSON
curves, with identical-period SPY/equal-weight paths. Monthly/yearly results and
ex-post SPY-direction conditional means are included for every strategy/scenario.
Regime definitions never feed trading signals. The final opening is liquidated
with costs; remaining dividend receivables, if any, remain economic assets.

A conditional 95% stationary-block bootstrap of daily active returns (10-session
blocks, 200 replicates) and deflated-Sharpe diagnostic were generated. These are
not independent validation, a complete multiple-testing correction, or forecasts.
The persistent registry retains all attempts, failed/repeated evaluations and
sensitivity variants. Its count is not a claim of a known unique external hypothesis
family. FDR qualification is unavailable with unknown complete history. No candidate
is certified, promoted to paper, or deployed. The canonical 2019 equity and
2013-10-14 futures protected holdouts were not opened, authorized or consumed.

## Data limitations and next campaign

- Corporate-action and historical-universe evidence is absent. No missing split,
  dividend, pay date, delisting payout or membership was invented. Omitted dividends
  can understate wealth and change comparisons; raw discontinuities can distort
  signals/accounting. Results are explicitly **exploratory**, not validated total-return evidence.
- The three retrospectively supplied surviving stocks are not a PIT/unbiased universe.
- Price availability uses the conservative following-day bound, not independent
  publication/revision certification. Provider revisions are not independently reconciled.
- Raw executable prices are separated from action ledgers. Adjusted snapshots are
  rejected for cash replay. Known events retain existing split/reverse-split/dividend
  accounting; unknown coverage is incomplete, never certified empty.
- Lifecycle-marked symbol changes/delistings without a validated execution adapter
  fail closed. Order book, queues, taxes, financing, interest, calibrated capacity
  and cash-in-lieu are not modeled. Fixed impact is a scenario, not proof of capacity.

Next: obtain independently reviewed raw prices/events/PIT lifecycle data, freeze a
campaign and confirmation plan, compare ML against the already stronger simple
mean-reversion control, calibrate transaction costs/participation and run a bounded
registered search. Preserve full historical attempts and separate development from
independent confirmation/final holdout. No salary, future-return or live-readiness
claim follows from this demonstration. The original Phase 12 campaign stays blocked.

## Deliverables

- `demo/simulation-report.json`: full net/gross metrics, all scenarios, model/source
  provenance, period/regime performance, bootstrap diagnostics and parameter sensitivity.
- `demo/benchmark-comparison.csv`: all 18 strategy/scenario comparisons and costs.
- `demo/baseline-*-trades.csv`, `orders.csv`, `signals.csv`, `positions.csv`,
  `corporate_actions.csv`, `equity.csv`: actual simulated logs at baseline costs.
- `demo/verified-predictions.csv`: saved OOS scores and clock/model version evidence.
- `demo/simulation-artifacts.zip`: all scenarios' complete report and CSV artifacts.
- `demo/data-provenance.json`, `demo/artifacts-sha256.json`: reproduction inputs and
  deliverable checksums. Vendor archives and model binaries are intentionally unshared.
- `verification.json`: final automated validation; `audit.md`: baseline and reuse audit.

## Automated validation

Baseline before changes: **363 passed, 11 skipped**. Final full Python suite: **378 passed, 11 skipped**, 701 dependency warnings, 186.46 seconds. **22 frontend tests** and **7 browser workflow checks** passed; production build, Ruff, Prettier and diff whitespace checks passed. The browser checks cover strategy submission, net-results/scenario switching, desktop/mobile rendering, existing workflows and original report downloads. A real API-to-background-worker test also produced the complete ZIP without model binaries. Skipped live tests are not evidence of external execution. No live trading or protected-holdout evaluation occurred.
