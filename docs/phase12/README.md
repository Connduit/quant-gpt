# Phase 12 initial research campaign

Continuation: [Phase 12A connectivity and provider evaluation](phase12a-results.md)
records the updated allowlist, fresh Stooq failures, missing local retained data,
and the documented Norgate limitations. The original audit below is historical.

**P12-EQ-001 is BLOCKED_DATA. No new model was fitted, no strategy trial was run,
and no candidate was promoted.** The current data passes engineering checks but
cannot meet the scientific data requirements in the [full request](instructions.md).
This is an initial readiness and data-quality result, not a negative model result.
Actual strategy discovery and profitability evaluation remain incomplete.

The [complete platform usage guide](../user-guide.md) explains the implemented
features. The frozen [campaign protocol](../../configs/phase12/equity-ml-campaign.yaml)
is a research specification, **not** an executable `quantlab research` YAML.
The [machine-readable preflight](preflight.json) records each exact snapshot,
checks, registry counts, holdout states and blockers. The operational script
[phase12_equity_campaign.py](../../examples/phase12_equity_campaign.py) reproduces
this read-only audit from the existing local artifacts:

```bash
uv run --frozen --all-extras python examples/phase12_equity_campaign.py
```

Exit **2** is the expected insufficient-data outcome; exit 1 indicates an assertion,
integrity, missing-input or software error. The script never dispatches experiments,
even if future data passes some checks. Replacing inputs requires reviewed snapshot
IDs, requirements and an execution adapter. A fresh clone does not contain ignored
vendor data or SQLite histories; it must be supplied those reviewed artifacts first.
The script overwrites only its generated `preflight.json`, not research history.

## Platform readiness audit

| Milestone | Implemented and checked | Current research limitation |
| --- | --- | --- |
| 1 Data | Provider interface, CSV validation, immutable Parquet/hash manifests, DuckDB | No complete PIT equity universe; Stooq blocked in attached instance |
| 2 Backtesting | Causal signals, next-eligible opening fills, costs, decimal ledger, actions | Accounting validation is not action-data certification |
| 3 Features and ML | Causal feature groups, return/direction/volatility labels, five CPU model families, purged folds | Native regression score ranking, not pairwise/listwise ranking |
| 4 Discovery | Bounded Optuna, subprocess limits, local MLflow, immutable identities, rejection/robustness | Old seven-stock experiment is developmental and reused |
| 5 Statistics | Block bootstrap, PSR/DSR with limitations, multiple-testing history, holdout ledger | Selection history incomplete outside retained registries; no independent confirmation |
| 6 Portfolios | Shared cash, netting/attribution, allocation methods, exposure/loss controls | Prior inputs were rejected strategies, not investable allocations |
| 7 Futures | Actual contracts, margins, rolls, intraday features, research/discovery | Verified ES archive has five days and two OOS sessions; no adequate micro history |
| 8 Paper | Durable OMS, quote checks, inference pins, recovery, risk, archival replay | No qualified strategy or verified continuous live feed |
| 9 Dashboard | Curated artifacts, charts, role checks, SSE refresh, named jobs | Shows research/replay; does not establish qualification |
| 10 Agent | Strict plans, memory, budgets, approved tools, quarantine | Execution adapter is futures-only; demonstrations scripted, no verified LLM |
| 11 Execution | Signed sandbox scopes, mock OMS tests, reconciliation, backup/restore | External PAPER unverified; real-money LIVE hard-disabled |

Current full Python suite: **326 passed, 7 skipped**, 513 warnings, 162.92 seconds.
Command: `uv run --frozen --all-extras pytest -q`. Skipped optional live tests are
not evidence of connectivity. The new audit independently revalidated all eight
pre-holdout price snapshots through the existing validator, storage reader and
DuckDB count. No package engine code was changed for Phase 12. Prior frontend,
container and deployment checks remain historical evidence; they were not rerun
as new Phase 12 empirical tests.

Critical execution-path finding: legacy equity research loads full configured
snapshots before dataset filtering, discovery preparation trims after opening
original snapshots, and statistical preparation verifies full source archives.
Worker-level sealing protects worker evaluation, but it is not a promise that
preparation never reads protected bytes. **Do not run those legacy preparation
paths for this campaign.** The audit checks request bounds before reading only
physically pre-2019 normalized snapshots/CSV. A reviewed prefix-only campaign
adapter remains a prerequisite for future fitting; no large-scale campaign was
started over this unresolved path.

## Data quality, coverage and access

The eight safe snapshots contain AAPL, AIG, BAC, FB, GOOGL, IBM, WM and SPY,
**1,195 XNYS sessions each, 2014-04-03–2018-12-31**. Exact IDs and per-symbol
results are in [preflight.json](preflight.json). Source is the QuantConnect LEAN
archive pinned to commit `655ac6d475ad8539ff54583a26327e63b59c5703`.
OHLC prices are raw/unadjusted, normalized from the documented scale. Hashes,
CSV/Parquet equality, finite positive OHLC relationships, integer nonnegative
volume, unique dates and XNYS session completeness passed. DuckDB read-back counts
matched. These checks establish internal consistency, not a full independent
market-data audit or compatibility with every future model configuration.

There are only seven stock names in four sectors, selected retrospectively.
No historical membership, delisting return or full historical symbol-map evidence
is present. Metadata explicitly says `point_in_time: false`. The availability
bound is a conservative following-day rule, not verified historical publication
latency. Factor-file action ledgers explicitly say `complete: false`; dividend
amounts are rounded-factor reconstructions and payment dates are unknown. Zero
recorded events never establishes that no events occurred. Receivables are not
silently paid. An earlier independent AAPL comparison covered 506 price sessions,
99.802% within one cent; it does not certify all symbols or action completeness.

A fresh request through the actual Stooq Python/httpx adapter still failed:
**ProviderNetworkError → ProxyError: `403 Forbidden`**. See [exact evidence](connectivity.json).
Current environment observations are current, enforced revision 1, with no custom
allowed hosts or secret bindings. This attached instance does not reflect the
claimed Stooq permission update. Environment administrator action: apply/publish
`stooq.com` permission to the selected instance (or start a task using the updated
configuration), then retest a fresh Python connection. TLS verification remained
on; no proxy bypass was attempted. Even successful Stooq CSV downloads would
retain `vendor_adjustment_unspecified`, with no complete event or PIT ledger.

Required replacement: licensed, auditable unadjusted daily bars, historical symbol
mapping and PIT membership including delistings and payouts, certified splits and
dividends with payment dates, coverage/source versions and independent checks.
Evaluate an institutional equities dataset with explicit event/universe products
and contractual entitlements; an OHLC-only API is insufficient. The current
provider protocol can be extended with an adapter without network logic in the
research engine. No new licensed provider, subscription or credentials were
assumed. Respect archive/provider redistribution rights; raw files remain ignored.

The frozen campaign chooses at least **100 stocks, eight sectors and 2,000 sessions**
as initial protocol coverage goals, not universal scientific thresholds or a
promise of power. It additionally requires an independently reviewed confirmation
period that excludes the reserved holdout and old reused validation. Reducing
these goals or replacing the data requires a documented protocol revision, never
an automatic retry with weakened validation.

## Existing strategy inventory and results

| Inventory | Previous actual outcome | Appropriate status/use |
| --- | --- | --- |
| Momentum, mean reversion, buy-and-hold, SPY/equal-weight/random controls | Synthetic and developmental comparison engines work | RESEARCH controls; no profitability evidence from fixtures |
| M4 seven-stock discovery | Four optimizer trials plus six diagnostics; none qualified | REJECTED under original filters; retrospective development only |
| M5 statistical diagnostics | Four candidates plus eight robustness variants; none qualified | REJECTED; reused windows and proxy actions |
| M6 multi-strategy portfolio | Nine runs; equal-weight −3.339%, inverse-vol −5.154%, SPY +12.093% on that report interval | Research mechanics, no qualified strategy allocation |
| M7 futures | Four ML candidates plus five controls; all rejected, two OOS days | REJECTED / insufficient independent evidence |
| M8 archival replay | 99 fills, $348.48 fees, ending NAV $98,882.77, loss kill persisted | Experimental RESEARCH replay; not live paper performance |
| M10 agent | Two scripted two-iteration sessions; 12 attempts each, all rejected | Scripted engineering evidence, not LLM-generated alpha |
| M11 sandbox | Mock broker, synthetic quotes, three fills, $0.10 fees, ending NAV $99,999.60 | Execution engineering only |

Sources: [M4](../milestone-4-results.md), [M5](../milestone-5-results.md),
[M6](../milestone-6-results.md), [M7](../milestone-7-results.md),
[M8](../milestone-8-results.md), [M10](../milestone-10-results.md),
[M11](../milestone-11-results.md). Different periods/data/accounts are not combined
into a return track record. Historical runs were not rerun as independent evidence.
The current preflight records every retained registry's attempts/status counts;
counts across registries are not automatically unique independent hypotheses.

## Initial campaign and statistical-validation report

Eight predeclared hypotheses combine four fixed models (Ridge, Random Forest,
LightGBM, XGBoost) with two economic feature bundles. Full rationales and ordered
alternatives are in [research-backlog.yaml](research-backlog.yaml). The protocol
specifies parameters, 756/126/126-session training/validation/test, five-session
horizon, gap/purge/embargo, cadence, costs, position/liquidity limits, seed and
hard proposed budgets. There is no post-result hyperparameter optimization.

The native label is next-eligible-open five-session total excess return over SPY
before trading costs. Risk adjustment means portfolio volatility/drawdown and
known-volatility sizing; the platform does not secretly provide a volatility-
normalized label or learning-to-rank objective. Baselines use identical periods,
capital, event treatment, execution timing and costs. No mixed-price-basis comparison
is valid. Results must include active net return, turnover, drawdown, exposures,
trade concentration, capacity, regime/window stability and parameter sensitivity.

**Actual Phase 12 result: zero fits, zero strategy evaluations, zero candidates.**
Bootstrap intervals, p/q values, DSR, Sharpe, drawdown, profitability and capacity
are unavailable, not zero or fabricated. No synthetic output substitutes for an
empirical result. All eight hypotheses remain blocked proposals rather than tested
REJECTED strategies. The [candidate registry](candidate-registry.json) has no new
candidate entries. No surviving or approved candidate exists.

Future eligible trials must record every failed, pruned, duplicate, diagnostic and
robustness attempt, retaining full historical searches. Proposed acceptance uses
positive net active mean versus each baseline, positive lower 95% block-bootstrap
bounds (blocks 5/10/20, 2,000 replicates), BY q ≤ .05 across the full declared family,
DSR ≥ .95 only when estimable, ≥60% positive windows, regime/parameter stability,
nonconcentrated profits and doubled-cost survival. Small-sample/nonstationarity and
unknown external search history limit these statistics. Multiplicity for all
baseline contrasts and robustness variants must be fixed before execution.
Independent confirmation and explicit human paper approval remain separate gates.
No threshold can override missing PIT/action evidence.

## Next experiments and capital feasibility

1. Acquire and independently validate the complete data bundle above; report
   price/event/membership coverage failures per symbol and period.
2. Review a safe prefix-only equity adapter, exact confirmation dates, dated cost
   and participation/capacity assumptions, then freeze a native execution config.
3. Only after those gates pass, run the initial eight hypotheses and the same
   simple baselines within the fixed budget. Stop on data, integrity, holdout or
   resource violations and report all attempts, including no survivors.
4. Review evidence before any later campaign, richer models, paper approval or
   deployment. No automated expansion or Milestone 13 was started.

There is no statistically qualified return distribution from which to estimate
salary-replacing capital, safe withdrawal income or risk of ruin. These quantities
are **not identifiable from the current results**. Illustrative arithmetic only:
a $100,000 annual pre-tax withdrawal plus $10,000 operating costs would require
110%, 44%, 22%, 11% or 5.5% annual cash return on $100k, $250k, $500k, $1m or $2m
respectively, before taxes, drawdowns, inflation and reserve requirements. These
are required hurdles, not forecasts or achievable returns. Taxes and personal
income needs are unspecified. No strategy currently supports an income claim,
capital recommendation or leaving employment.

The equity 2019 and futures 2013-10-14 protected periods were not read/evaluated
by this audit; canonical ledger states were read as metadata only and remained
SEALED. No authorization token, protected result, source ZIP, broker order or
promotion was created. Research stops at this blocked initial campaign.
