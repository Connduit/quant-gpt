# Historical data and equity research in the dashboard

Once the server is running and a researcher is connected, these workflows require
no command-line input. Existing curated result panels remain below the new forms.

## Download and create snapshots

Open **Data library**, enter US symbols (include SPY for benchmark research),
choose dates and click **Download & create snapshots**. At most 12 symbols and
ten years for Alpaca (31 calendar days for Databento) are accepted per request.
Select Alpaca/SIP or IEX, or Databento/dataset and estimated cost cap. See
[provider setup](market-data-setup.md) for secrets, allowlist and entitlement details.
Downloads support completed historical dates, including dates after 2018.
Newer snapshots appear in the library, but reserved holdout data remains
unavailable for training/discovery.

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

## ML training and discovery

1. Open **Machine learning** / **Research**, or **Discovery**.
2. Select one eligible snapshot per equity plus SPY with identical date coverage.
3. Set run name, models, horizon, training/validation/evaluation windows, top
   holdings and seed. For discovery, also set the maximum trial count.
4. Click **Start ML training** or **Start bounded discovery**.
5. Inspect the job report for fold metrics, baseline comparisons, costs, rejected
   attempts, provenance and limitations. Download its JSON if needed.

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

Research limits: 3,000 source sessions, eight folds, five models per training run,
eight discovery trials, one CPU thread, 4 GiB address space, 900 CPU seconds and a
20-minute outer wall limit. Discovery also has per-trial CPU/time limits.
Insufficient history/windows fail with a reason. Reserved holdout archives are
excluded before payload reads through the new prefix-only paths. No job enables
live trading or releases a holdout.

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
