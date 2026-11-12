# Statistical validation and overfitting protection

Milestone 5 extends the existing research pipeline; it does not restart discovery
or authorize trading. See the [unaltered request](milestone-5-instructions.md),
[pipeline audit](statistical-validation-audit.md), [real-data verification](market-data-verification.md)
and [recorded outcomes](milestone-5-results.md).

## Chronology, information intervals and reuse

Each asset/session sample records `prediction_at`, `execution_at`, `label_end_at`
and `label_known_at`, all timezone-aware. Prediction precedes eligible execution;
label end follows entry and cannot precede known-at publication. Duplicate
asset/session observations, nulls and invalid boundaries fail validation.

`ml.validation.walk_forward` supports rolling or expanding training, inner
validation and subsequent evaluation windows. `retraining_sessions` controls
model refresh frequency independently from the maximum test-window length.
When refresh is more frequent, predictions stop at the next refresh to avoid
double-counting. When refresh is less frequent than test length, explicit gaps
remain between evaluated windows; no fabricated returns fill those gaps.
`gap_sessions` and `embargo_sessions` remove trailing training/inner-validation
session dates before the next boundary. They are trading-session counts, never
calendar-day approximations. The existing train/validation/test lengths count
candidate session dates before removal and label maturation purging.

Across **all assets**, training labels must be known strictly before the first
inner-validation prediction; inner-validation labels must be known before the
first evaluation prediction. This stronger chronological rule also excludes
any forward information interval overlapping the next partition. The standalone
`purge_overlaps` helper applies the same global cross-asset cutoff. Models and
scalers fit only retained training samples. Each prediction records fit time
and latest training-label availability. Horizon comparisons retain the existing
common longest-horizon calendar and purge adjacent evaluation-window tails.

Training fits, hyperparameter search/inner validation, strategy-selection
validation, and final holdout retain distinct roles. Milestone 5 can rerun
advanced folds on permitted development data, but **does not manufacture a new
independent strategy-selection period from data already inspected by discovery**.
Reports label these runs `reused_development_diagnostics`. A chronological fold
is OOS for its model; it is not independently unseen by the researcher who
repeatedly changes strategy rules on the same historical period.

## Holdout manifests and one-use evaluation

Routine validation accepts only verified normalized inputs ending strictly
before the configured holdout. It creates new immutable development seals, so
workers receive no reserved normalized rows, features or labels. The manifest
must match the original research snapshot IDs and cutoff. This adapter reads
research YAML metadata, never the original full-history snapshot data. Pinned
bulk source ZIPs can contain additional dates; requested normalization filters
those out before research construction.

`HoldoutVault` stores immutable source/range manifests and an append-only event
history in local SQLite. Overlapping manifests with shared source identities
cannot be relabeled as fresh. Registration is idempotent. A trusted future caller
must explicitly supply actor, reason and `AUTHORIZE_ONE_FINAL_EVALUATION` to
obtain a random one-use token. `evaluate` consumes that token **before invoking
an evaluator**, including failures/crashes, records results and keeps them
sealed. A separate explicit `AUTHORIZE_RELEASE_FINAL_RESULTS` is required to
return results. Consumed holdouts cannot be reused as fresh independent evidence.

This milestone's CLI deliberately exposes no final-evaluation or release command.
No real holdout evaluation is run. The vault is a trusted application boundary,
not protection against someone editing SQLite or reading original files outside
the API. Future evaluators must use the same canonical ledger/source identities;
copying/resetting a ledger or renaming re-ingested sources is not fresh evidence.

## Uncertainty and historical path simulations

`statistical.statistics` implements seeded moving-block and stationary bootstrap.
Moving blocks retain consecutive observations; stationary blocks restart with
probability `1 / block_length`. Both sample **within each original fold**, retain
fold order and preserve cross-candidate pairing when appropriate. The default
5/10/20-session block sensitivity is reported instead of selecting whichever
block produces a favorable answer. At least 100 and at most 10,000 replications
are supported; the recorded demo uses 500.

Percentile intervals cover mean daily return, chained normalized-fold return,
annualized Sharpe and maximum drawdown. The original fold accounts reset their
cash independently; chaining their daily return factors is a normalized diagnostic
path, not a continuously traded multi-year account. Benchmark-relative series
are arithmetic daily strategy return minus SPY return; compounding that series
is a diagnostic active-return path, not an actual self-financing long/short book.
Reports include five drawdown quantiles and three seeded example paths.
Drawdown path quantiles and alternative paths describe conditional historical
uncertainty, **not forecasts**. Local stationarity, finite moments, chosen block
length and sample representativeness remain assumptions. Tail/nonstationary risks
can be understated. Per-fold equity, turnover, exposure, fill counts, exit-profit
concentration, costs and predictive metrics remain available in the full report.

Effective sample size uses a capped positive autocorrelation sequence. It is a
heuristic measure of serial information, not a proof of independent observations;
trade counts and cross-asset prediction counts are not substituted for independent
daily portfolio observations.

## Sharpe diagnostics and search corrections

Probabilistic Sharpe Ratio uses nonannualized Sharpe, observed skew/kurtosis and
a normal approximation. The null reference is zero daily return (zero risk-free
rate); a reported effective-n substitution is a heuristic dependence adjustment.
Zero variance or insufficient effective observations produces an unavailable
result rather than infinity or automatic significance.

Deflated Sharpe Ratio uses the expected maximum Gaussian null Sharpe approximation,
Euler's constant and null dispersion `1/sqrt(n_eff-1)`. It counts **all recorded
unique hypotheses**, not only successful optimizer trials. This is an explicitly
approximate null-dispersion assumption, not measured independent-strategy Sharpe
dispersion. Search correlation's eigenvalue participation ratio is also reported,
but never reduces the conservative count used for correction.

The history reader collects all explicitly supplied registry roots, including
rejected, failed, pruned and robustness variants. Retries/reproduction attempts
are tracked separately. The example includes all retained `data/discovery`
registries, all retained statistical-validation registries, and the current registry. Unknown manual/external searches
cannot be counted; reports disclose this scope.

For observed candidate daily SPY-relative returns on common OOS dates, a centered
stationary-block **max-t** bootstrap uses the same sampled indices across columns.
Scaling uses observed standard errors and remains fixed across draws; this is
not a fully studentized nested bootstrap. Centering is global, preserving fold
regime offsets. It reports one-sided marginal and observed-family max-test
p-values under a joint nonpositive-mean null. Full-history-count Bonferroni
sensitivity additionally guards against treating unobserved variants as absent.
This is conservative sensitivity analysis; opaque adaptive search/reuse prevents
an unconditional claim that all selection bias has been removed.

Benjamini–Yekutieli FDR adjustment is the default for dependent valid p-values;
Benjamini–Hochberg appears only as a sensitivity under independence/positive
dependence assumptions. Failed/unobserved hypotheses remain in family size as
untested p=1 slots. The worst p-value across block lengths is used. Finite
bootstrap resolution limits inference after a large search; no zero p-values
are emitted. FDR control still requires valid input p-values; historical reuse
and adaptive selection can violate that premise. No single statistic establishes
future profitability.

## Robustness and research statuses

Separate registry attempts rerun the top candidate under doubled per-share
commissions, doubled slippage, a one-session execution delay, alternate rolling/
expanding training, alternate validation period, a nearby model parameter,
alternate sizing and a regime filter toggle. Existing fixed-prediction cost stress
also remains in every fold. Delay changes when an already available signal is
submitted; the backtester's strictly later-open execution rule stays intact.
Scenarios have immutable separate artifacts and parent lineage. Missing scenarios
or resource-budget failures do not count as passes.

Volatility-regime reporting classifies observed SPY volatility using a fixed
20% annualized threshold. This is a descriptive classification using each
observation’s close-based features, which may be published after that day’s
return; it is not a regime signal known before earning that same return.
No future realized regime is used to choose or promote a strategy. Alternative stock
universes are explicitly unavailable without reliable historical membership
coverage. Robustness reuses development data and does not supply independent
confirmation. No original discovery artifact is overwritten.

Status rules are applied in this order:

1. `REJECTED`: economic/discovery gates fail, net validation return is nonpositive,
   or the strategy fails to exceed the strongest simple baseline.
2. `INSUFFICIENT_EVIDENCE`: sample/fold/effective-information minimums fail; or
   BY q/full-count familywise sensitivity exceeds alpha; or DSR is unavailable/
   below `1-alpha`; or block-sensitive active-return intervals cross zero; or
   required robustness fails/is missing.
3. `REQUIRES_FURTHER_TESTING`: earlier gates pass, but action completeness,
   historical-universe certification or independent strategy-selection evidence
   remains missing.
4. `VALIDATED_FOR_PAPER_TRADING`: all earlier gates pass **and** a trusted research
   caller supplies audited independent-selection and universe evidence, with
   complete action coverage. This rule is unit-tested with synthetic evidence;
   the present real-data adapter has no certification source and cannot emit
   this status. YAML booleans cannot self-certify data. This status would still
   imply neither proven future profit nor authorization for live orders.

The framework explicitly allows an empty paper-trading shortlist.

## Commands and reproducibility

```bash
uv sync --frozen --all-extras
uv run --frozen --all-extras python examples/statistical_validation_demo.py --output data/statistical/NEW_RUN
uv run --frozen --all-extras quantlab validate walk-forward --validation-config configs/validation.example.yaml --output data/statistical/ANOTHER_RUN
uv run --frozen --all-extras quantlab validate confidence-intervals --reports data/statistical/NEW_RUN
uv run --frozen --all-extras quantlab validate multiple-testing --reports data/statistical/NEW_RUN
uv run --frozen --all-extras quantlab validate compare --reports data/statistical/NEW_RUN data/statistical/ANOTHER_RUN
uv run --frozen --all-extras quantlab validate rejected --reports data/statistical/NEW_RUN
uv run --frozen --all-extras quantlab validate eligible --reports data/statistical/NEW_RUN
```

`run`, `walk-forward` and `robustness` run the full bounded pipeline; the remaining
commands inspect saved immutable JSON without launching research. Use `report`
for full reports or `list` for all statuses. Existing output directories fail
rather than overwrite evidence. Paths resolve relative to YAML files. The
populated [example](../configs/validation.example.yaml) references retained M4
candidates and freshly verified pre-holdout inputs; a fresh checkout needs those
local artifacts or a new discovery run and matching source manifest. Backtest artifacts are checksum-verified before statistical reads. Source data,
models and SQLite files are ignored by Git. Input source hashes/configuration,
code hash, IDs, parameters, seeds, bootstrap settings, trial history, fold timing,
known limitations and statuses are included in `validation.json`.

No service or GPU is required. Existing resource-limited discovery workers handle
training/replay; configuration caps candidate count, diagnostics, wall time,
threads and memory. Block analysis is bounded by replication/block-length limits.
Optional live tests use `QUANTLAB_LIVE_PROVIDERS=1`; ordinary tests remain offline.
Milestone 6 is not started.
