# Historical data and equity research in the dashboard

Once the server is running and a researcher is connected, these workflows require
no command-line input. Existing curated result panels remain below the new forms.

## Download and create snapshots

Open **Data library**. Both download forms default to **SPY, AAPL, MSFT, AMZN,
GOOGL, META, NVDA and TSLA** (SPY plus the Mag 7).

Use **Quick download: training + protected test snapshots** to create both datasets
in one job with Alpaca. The default preset uses 2020–2024 for training and 2025
through yesterday (UTC) for protected testing. The legacy preset uses 2016–2018
for training and 2019 for testing; **Custom split** lets you choose the boundary.
The preview shows both ranges before submission. The worker sends separate bounded
requests and stores protected snapshots under `library/protected`, with immutable
`dataset_role` metadata. The report labels every outcome Training or Protected test.

Test dates are reserved before downloading, including when a job partially fails.
Repeat requests reuse caches for the same role. Reservations cannot be moved into
training, and overlapping older archives or saved runs are blocked from routine
research/evaluation. Protected rows remain visible but cannot be selected, including
in exploratory mode. This shortcut downloads data; it does not run final test
evaluation, make previously inspected data unseen, or supply missing corporate-action
and historical-membership evidence. Custom training ranges must also respect the
existing canonical 2019 holdout when evaluating strategies.

For a single range or Databento, enter US symbols,
choose dates and click **Download & create snapshots**. The form defaults to
one year ending yesterday (UTC), with the end-date picker allowing completed dates
after 2018. Switching to Databento selects a 31-calendar-day window ending on the
chosen end date. At most 12 symbols and
ten years for Alpaca (31 calendar days for Databento) are accepted per request.
Select Alpaca/SIP or IEX, or Databento/dataset and estimated cost cap. See
[provider setup](market-data-setup.md) for secrets, allowlist and entitlement details.
Downloads support completed historical dates, including dates after 2018.
For unreserved research archives, choose the research date range in those forms;
the worker automatically extracts just that range. Archives overlapping explicitly
reserved protected dates must use the separately downloaded training snapshot.

Add or replace provider credentials through **API keys** in the sidebar, using an
operator token. The Data library's **Manage API keys** link opens the same page.
Saved keys are encrypted on the server and apply immediately to new jobs.

Follow **Equity workflow jobs**. Open **View report** for per-symbol outcomes and
download its JSON report. Partial downloads retain successful snapshots and report
failed symbols. **Historical snapshot library** shows dates, counts, provider,
price basis, identity and research blockers.

An exact prior request reuses a checksum-verified cache. **Fetch a fresh version**
downloads another immutable version without overwriting earlier data. Validation
checks source date bounds, full XNYS sessions, OHLCV consistency, hashes and
storage/DuckDB read-back. HTML verification pages and HTTP errors fail the job.

## Exploratory ML for downloaded prices

In **Machine learning** / **Research**, choose **Research mode → Exploratory ML —
prediction only**. Click **Use training snapshots** to select eligible snapshots
(one per symbol, including SPY) and fill their shared research date range. Training
snapshots are preferred and protected test snapshots are excluded. You can also
select snapshots manually. If Start is disabled, the requirements directly above
it identify the missing selection, benchmark, date coverage or model. Select one
downloaded snapshot per stock plus SPY, choose your
research dates, models and chronological windows, then click **Start exploratory
ML**. Switching modes clears snapshot selection so the eligibility rules are
explicit. For a full 2020–2026 range with the default 504 training and 126
validation sessions, use 252 evaluation sessions per fold to stay within the
eight-fold budget. Exploratory snapshots show **EXPLORATORY**, with their strict-research
limitations still visible. The default remains **Strict research**.

Exploratory ML accepts declared unadjusted or adjusted daily prices without
corporate-action ledgers or historical-universe membership. All selected inputs
must share the same declared price basis. Synthetic and unspecified-basis inputs
remain blocked. Source checksums, OHLCV/calendar validation, requested date bounds,
availability timestamps, train-only preprocessing, purging and resource limits
still apply. No action records, historical membership, or eligibility claims are
invented. The original snapshots are unchanged.

This path produces saved models, features, validation/out-of-sample prediction
metrics and predictions, but **no portfolio simulation, return-after-costs report,
strategy qualification or promotion**. Targets are next-eligible-open to horizon-
open quoted price changes relative to SPY, not verified total returns. Logistic
regression predicts the probability of a positive excess price change.

Raw splits and dividends can distort features and targets; this mode does not
infer corrections. Adjusted inputs retain the vendor's retrospective adjustment
basis and are not certified point-in-time inputs. Reports show the input basis,
large close-price-change diagnostic counts (absolute changes of at least 40%),
source lineage, hashes and these limitations. Counts are not verified actions.
A fixed supplied stock list also introduces possible survivorship/selection bias.

Exploratory mode is available only for ML training. **Discovery** and strict
research retain the raw-price/action/PIT evidence requirements. Old API requests
default to strict mode; exploratory API requests must specify `research_mode:
exploratory`, the training workflow and both research dates.

## Evaluate saved predictions as a trading strategy (Phase 12C)

Open a completed ML job's **View report**, then **Evaluate strategy profitability**.
Set the model/date range, starting capital, top holdings, score or probability
threshold, volatility ranking, holding/rebalance schedule, target weights, share
assumptions and risk/cost settings. Choose strict or exploratory evidence mode
explicitly and click **Evaluate strategy** with researcher access.

The queued `profitability` job verifies saved source/model/prediction hashes and
clocks, then runs the existing cash backtester. Open its report for net equity,
drawdown, annualized return, Sharpe/Sortino, benchmarks, turnover, costs, period and
regime results, nearby-parameter sensitivity and validation status. Cost scenario
selection changes both metrics and chart data. The ZIP contains full trades,
orders/rejections, signals, positions, actions, equity and reports for all scenarios.
Prediction diagnostics remain available separately. No refitting or broker order
is performed by this step.

Only raw executable prices are accepted. Saved source jobs or execution manifests
containing protected 2019 dates are rejected before prediction/price reads; choose
a physically separate permitted-date training run. Missing action/PIT evidence
requires exploratory mode and remains prominently disclosed; unknown events are
not certified absent. No backtest is automatically qualified or promoted.
See [Phase 12C usage and assumptions](phase12c/README.md) and
[the actual exploratory demonstration](phase12c/results.md).

## ML training and discovery

1. Open **Machine learning** / **Research**, or **Discovery**.
2. Select one eligible snapshot per equity plus SPY. Set **Research start date**
   and **Research end date**; all snapshots must cover that range, but may contain
   additional dates outside it. Eligibility is checked for the requested range.
3. Set run name, models, horizon, training/validation/evaluation windows, top
   holdings and seed. For discovery, also set the maximum trial count.
4. Click **Start ML training** or **Start bounded discovery**.
5. Open **View report**. The readable results show research dates, stocks and
   horizon; formatted accuracy, error, ranking and sample-count cards; model
   comparison; validation/evaluation charts and a table by time period; and
   data limitations. Expand the feature-importance section to inspect a period.
   Classifier probability errors are distinguished from percentage-point return
   errors, and missing metrics are displayed as unavailable rather than zero.
   The original report remains under **Raw report JSON** and **Download report JSON**.
   Existing reports use the new view without rerunning training. Prediction
   accuracy is not presented as proof of profitability or superiority to a naive
   baseline. Blocked jobs and partial downloads show their reasons and outcomes.

Models: Ridge, logistic regression, Random Forest, LightGBM and XGBoost. Training
uses the existing causal features and walk-forward ML/backtesting engine.
Discovery uses the existing Optuna/MLflow engine with bounded model parameters,
momentum/reversion feature bundles, rebalance cadence and doubled-cost checks.
Complete models, predictions, configurations, trade artifacts and registries stay
on the server; job reports are accessible without editing the static catalog.

All runs are **development research**, with no automatic qualification or promotion.
Separate runs must not reset the multiple-testing family of a later formal campaign.
The Phase 12 protocol, coverage goals and independent-confirmation gates are unchanged.

## Eligibility and current provider limitation

Alpaca and Databento return explicitly unadjusted prices, but OHLCV alone still
lacks the complete action and PIT universe bundle required by the trading engines.
Legacy Stooq snapshots retain their unknown-adjustment marker. Missing evidence
is shown as a blocker; the system does not invent actions or certify PIT membership.

Real development inputs need a verified unadjusted basis, declared PIT membership
and a validated complete action ledger matching the symbol and coverage. This gate
does not certify full Phase 12 identifier histories, terminal payouts, coverage,
independent event reconciliation or independent confirmation.

The earlier Stooq browser check returned HTTP 404. New dashboard requests now use
Alpaca or Databento; their real access is pending keys and host permissions as
recorded in [provider setup](market-data-setup.md). No successful real-data ML
result is claimed from the integration tests.

## Roles, budgets and recovery

Inspecting snapshots, jobs and reports uses viewer access. Submitting/cancelling
requires the existing **researcher** token through **Connect**. The browser accepts
typed fields, never a command, expression, configuration upload or filesystem path.

Jobs share one worker lane and a two-job queue. **Cancel** terminates the process
group including trial descendants. Uncertain jobs after restart become
`RECOVERY_REQUIRED` and block new launches until operator reconciliation. Requests,
checksums, configurations, reports and failures are retained.

Research limits: 3,000 selected research sessions, eight folds, five models per training run,
eight discovery trials, one CPU thread, 4 GiB address space, 900 CPU seconds and a
20-minute outer wall limit. Discovery also has per-trial CPU/time limits.
Insufficient history/windows fail with a reason. For date-bounded requests, the
worker verifies the source archives, then writes job-local immutable inputs and
clipped action ledgers containing only the requested dates. Training, validation,
feature warmup, labels and per-fold evaluation all use those inputs. No fitting
engine opens the original archives or prices after the selected end date. The
original library is unchanged; reports retain parent and derived snapshot IDs.
Legacy API requests without dates retain the previous pre-2019 guard.
This is development research, not certification of an untouched holdout. No job
enables live trading or releases a Phase 12 holdout.

## Server setup and verification

The default persistent library is `data/dashboard/library`. Administrators can
select an existing trusted library using `QUANTLAB_WORKFLOW_LIBRARY`. It must use
SnapshotStore layout, with action ledgers at `actions/<snapshot-id>.json` for raw
research inputs. Browser users cannot certify missing provider fields or supply paths.

Frontend tests cover request fields, refresh choice, eligibility, selection and
budgets. Browser tests cover submissions, selection and mobile layout. Backend
tests cover roles, bounds, malformed inputs, HTML rejection, cache reuse, real
subprocess execution and generated ML/discovery configurations. Engine integration
tests use explicit synthetic fixtures with a test-only selection injection; the
public input gate rejects synthetic data. No real reserved holdout is used.

Verification on 2026-11-12: full Python suite **332 passed, 11 skipped** (optional
or unavailable integrations), 545 dependency warnings; **9 frontend tests passed**;
**3 Chromium workflow tests passed**; production build, Ruff and diff whitespace
checks passed. Browser tests stub submission/eligibility responses; a separate
actual browser-to-backend download exercised the real worker/provider and recorded
the Stooq 404 above. The synthetic ML/discovery engine tests establish integration,
not real-data strategy performance.
