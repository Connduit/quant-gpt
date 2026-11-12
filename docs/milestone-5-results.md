# Milestone 5 results

**All four real-data candidates were rejected. No candidate qualifies for paper trading.** The final holdout remained `SEALED`, with registration only and no authorization, evaluation or release events. Milestone 6 has not been implemented in this report.

## Data and execution

Fresh HTTPS downloads used the pinned LEAN provider: SPY plus AAPL, AIG, BAC, FB, GOOGL, IBM and WM, 1,195 daily XNYS sessions each (April 3, 2014–December 31, 2018). The [snapshot manifest](market-data-verification-datasets.json) records exact IDs and source hashes. The final 2019 period was not materialized into research inputs or evaluated. Bulk source archives can contain additional dates.

Prices are raw according to the pinned reader/scaling contract and cross-checks. Corporate actions use an explicitly incomplete factor proxy; missing pay dates remain null and distributions are non-spendable receivables. Static survivors are not certified historical membership. This limits interpretation even if statistical diagnostics improve. See [network/data verification](market-data-verification.md).

The four saved M4 candidates were rerun on rolling 504-session training, 126-session inner validation and evaluation windows, refreshed every 126 sessions, with two-session gaps and five-session embargo. Each produced four OOS evaluation folds and 465 nonoverlapping portfolio-return observations. Train-only fitting, global label-availability purging and the common longest-horizon calendar remain enforced. The source execution settings are retained per candidate, including commissions, spread and slippage.

## Actual outcomes

| Candidate | Model / target / horizon | Mean fold net return | Mean fold SPY excess | BY q | Status |
| --- | --- | ---: | ---: | ---: | --- |
| `6246e0bf1e87d7d4` | xgboost / stock_return / 1 | 4.028% | -0.176% | 1.000 | REJECTED |
| `38e6ed5aaaa07318` | random_forest / stock_return / 1 | -0.177% | -4.380% | 1.000 | REJECTED |
| `b31393bc502f3d03` | random_forest / excess_return / 1 | 1.879% | -2.325% | 1.000 | REJECTED |
| `b65a005cf94c0275` | random_forest / excess_return / 5 | 3.965% | -0.238% | 1.000 | REJECTED |

Returns are arithmetic means of individual fold returns, not a multi-year account return or CAGR. Every candidate lagged SPY on this fold aggregate and the strongest simpler baseline. One also had nonpositive mean net return. Profitability did not survive the economic gates; statistical adjustments do not reverse rejection.

The report counted **60 unique recorded hypotheses, 61 attempts and 14 optimizer trials** across seven retained registries, including preliminary discovery/validation runs and failed/rejected variants. Current final validation contributes four candidate attempts plus eight distinct robustness attempts. Correlation participation ratio was 1.359 for the four observed daily series; correction count stayed 60. Unknown external/manual searches remain uncounted.

Each candidate used 500 bootstrap replications at 5/10/20-session blocks. Every 10-session active-mean interval crossed zero; BY q and conservative full-count familywise sensitivity were 1.0. Approximate deflated Sharpe probabilities ranged from 0.008 to 0.172. These reused-development diagnostics do not establish independent statistical evidence. Seeded alternative normalized paths and drawdown quantiles are retained in the full local report.

All **eight distinct robustness scenarios** were rejected: separate commission, slippage, execution-delay, rolling/expanding, period, parameter, sizing and regime variations. Historical-universe robustness was not run because membership coverage is missing. Original M4 artifacts were preserved. The preliminary run exposed integer rounding that made a neighbor unchanged; this was corrected and the final run verified eight distinct attempt IDs. Preliminary searches remain in multiplicity counts.

## Artifacts, tests and reproduction

The [machine-readable results](milestone-5-results.json) include exact strategy/attempt IDs, configuration, scores, intervals, search scope, robustness outcomes and holdout audit status. The full local report is `data/statistical/milestone-5-final/validation.json`, with per-fold model/prediction/backtest artifacts under `experiments/attempts/`. Data and models are not redistributed in Git.

```bash
uv sync --frozen --all-extras
uv run --frozen --all-extras python examples/statistical_validation_demo.py --output data/statistical/NEW_RUN
uv run --frozen --all-extras quantlab validate rejected --reports data/statistical/milestone-5-final
uv run --frozen --all-extras quantlab validate eligible --reports data/statistical/milestone-5-final
```

**197 tests passed**, preserving all 170 prior tests; three opt-in live tests skipped by default. Explicit live tests passed **3/3**. Lint, formatting, wheel/source distribution builds and independent wheel source-hash checks passed. The installed wheel reproduced a real candidate’s bootstrap intervals, seeded paths and deflated Sharpe exactly; its eligible-candidate CLI returned an empty list. See the [methodology](statistical-validation.md) and [audit](statistical-validation-audit.md). Repeated runs retain earlier registries, so multiplicity counts can grow; reproduce a recorded calculation with its saved history count and seeds. Source hashes identify the dirty build precisely; the reported Git commit is its base commit.

Remaining limits include adaptive research reuse, approximate PSR/DSR null assumptions, finite bootstrap resolution/local stationarity, uncertified action and universe coverage, and daily execution/capacity assumptions. No final holdout result was used. Future portfolio work requires explicit allocation/exposure/risk limits, realistic capacity assumptions and continued separation from independent final evaluation; it does not override these rejected statuses.
