# Quant Research Lab: complete usage guide

This is the operating guide for the code through Milestones 1–11 and the Phase 12
research preflight. It covers every public command family and the supporting
features, with detailed schemas linked where appropriate. Run commands from the
repository root. `SNAPSHOT_ID`, `SESSION_ID`, `ATTEMPT_ID` and `NEW_RUN` are
placeholders: substitute actual IDs and a new output directory, respectively.
Do not paste the whole document into a terminal as one script.

**Current state:** no strategy is qualified for real-time paper deployment, no
external broker/feed/LLM integration is empirically verified, and LIVE trading is
disabled. The [Phase 12 report](phase12/README.md) records why the available equity
data cannot support a scientifically credible new discovery campaign. Historical
examples demonstrate software behavior, not investable strategies.

## Contents

1. [Install, configure and check](#install-configure-and-check)
2. [Download, import, inspect and query data](#download-import-inspect-and-query-data)
3. [Backtesting and baseline strategies](#backtesting-and-baseline-strategies)
4. [Features, targets and machine learning](#features-targets-and-machine-learning)
5. [Discovery, tracking and reproducibility](#discovery-tracking-and-reproducibility)
6. [Statistical validation and holdouts](#statistical-validation-and-holdouts)
7. [Portfolio construction and risk](#portfolio-construction-and-risk)
8. [Futures data, research and accounting](#futures-data-research-and-accounting)
9. [Market feeds and simulated paper trading](#market-feeds-and-simulated-paper-trading)
10. [Dashboard and API](#dashboard-and-api)
11. [Bounded research agent](#bounded-research-agent)
12. [Controlled broker sandbox](#controlled-broker-sandbox)
13. [Deployment, recovery and incidents](#deployment-recovery-and-incidents)
14. [Phase 12 research workflow](#phase-12-research-workflow)
15. [Files, Python extension points and troubleshooting](#files-python-extension-points-and-troubleshooting)
16. [Complete CLI reference](#complete-cli-reference)

## Install, configure and check

Use Python 3.12+ and `uv`. The dashboard additionally requires Node 20.19+ or
22.12+. Install locked dependencies:

```bash
uv sync --frozen --all-extras
uv run --frozen quantlab --help
uv run --frozen pytest -q
uv run --frozen ruff check src tests examples
```

In managed Cloud, `export UV_CACHE_DIR=/workspace/.cache/uv` selects a writable
cache. `uv run` activates `.venv` automatically. `--extra ml` installs the CPU
research stack; `--all-extras` is the simplest full development installation.
Do not update lockfiles just to run examples. `uv lock` deliberately changes
Python dependency resolution. Dashboard installation uses `npm --prefix dashboard ci`.

Data commands accept explicit `--config configs/data.toml` **before** the
subcommand. Defaults are `./data`, Stooq, 30 seconds and INFO. TOML paths resolve
relative to the TOML file. Environment settings `QUANTLAB_DATA_DIR`,
`QUANTLAB_PROVIDER`, `QUANTLAB_TIMEOUT_SECONDS`, `QUANTLAB_LOG_LEVEL` override
TOML; environment and CLI paths resolve from the working directory. CLI
`--data-dir` and download `--provider` take precedence. Unknown fields fail.
JSON results go to stdout; UTC structured logs go to stderr. Nonzero exits mean
failure, except the documented Phase 12 insufficient-data exit 2.

External services require permitted hosts, TLS trust, credentials and appropriate
entitlements independently. Use inherited proxy/CA settings. Keep secrets in
managed settings, never Git, URLs or frontend build variables. Current Cloud
Stooq error is `ProxyError: 403 Forbidden`; see [fresh evidence](phase12/connectivity.json).
Applying/publishing a setting is separate from saving an environment draft.

## Download, import, inspect and query data

Start offline with the invented five-session fixture:

```bash
uv run --frozen quantlab --config configs/data.toml download SYNTH \
  --provider fixture --start 2024-01-02 --end 2024-01-08
```

Copy the returned full 64-character `snapshot_id`:

```bash
uv run --frozen quantlab --config configs/data.toml inspect SNAPSHOT_ID
uv run --frozen quantlab --config configs/data.toml query SNAPSHOT_ID \
  --sql 'SELECT session_date, close, volume FROM bars ORDER BY session_date'
```

`inspect` verifies manifest and file hashes before returning provenance and
summary. `query` permits one SELECT over `bars`; external file/network/extension
access is disabled. It is not an arbitrary DuckDB administration console.

For legitimate real historical downloads, choose `--provider stooq` or `lean` and
explicit completed dates. Stooq maps local `AAPL` to `aapl.us`. LEAN is a pinned
historical sample archive, not a current feed or complete market database. The
existing data is seven survivor-selected stocks plus SPY. No source silently
falls back to fixtures. Check licensing before using or redistributing any data.

```bash
# Requires working Stooq permission; unknown adjustment semantics remain recorded.
uv run --frozen quantlab download SPY --provider stooq \
  --start 2018-01-02 --end 2018-01-12
# Your own authorized source; declaring unadjusted requires evidence.
uv run --frozen quantlab import-csv AAPL --csv /path/to/development-only.csv \
  --source 'reviewed vendor and version' --price-basis unadjusted \
  --start 2018-01-02 --end 2018-01-12
```

CSV columns are `Date,Open,High,Low,Close,Volume`. The validator rejects missing
values, duplicates, nonfinite/nonpositive prices, invalid OHLC relationships,
negative/nonintegral volume and missing XNYS sessions. All dates are inclusive,
and must precede today's UTC date. `--refresh` downloads a new immutable revision;
`--extend PARENT_ID` requests an append under the ingestion rules. Cached reads
are checksum-verified. Never modify an existing snapshot to repair data.

Each snapshot stores `source.csv`, `bars.parquet` and `manifest.json` under
`data/snapshots/ID/`, including provider/request, hashes, software, retrieval,
price basis and availability metadata. A snapshot is not an action ledger or a
PIT universe. Corporate actions and historical membership require separate evidence.
Stooq prices are `vendor_adjustment_unspecified` and rejected for execution.
Details: [data design](data-design.md), [verification](market-data-verification.md).

## Backtesting and baseline strategies

The offline demonstration is safe software practice:

```bash
uv run --frozen python examples/backtest_demo.py --output data/backtests/NEW_RUN
```

It runs momentum, mean reversion and buy-and-hold on synthetic data, exporting
orders, fills/trade logs, equity, metrics and benchmark comparisons. An individual
verified execution-ready snapshot can be replayed with:

```bash
uv run --frozen quantlab backtest SNAPSHOT_ID --strategy momentum \
  --lookback 20 --shares 10 --initial-cash 100000 \
  --commission-per-share 0.005 --slippage-bps 5 --spread-bps 2 \
  --actions /path/to/complete-actions.json --output data/backtests/NEW_RUN
```

Use `--strategy mean-reversion` or `buy-hold` for alternatives. Thresholds are
fractions, e.g. `0.02`; slippage/spread are basis points and spread is the full
bid/ask spread. Fixed and minimum commission settings are also available.
Signals from a closing observation execute only at a strictly later eligible
session open. Cash, positions, fills, fees, splits and dividend receivables use
explicit accounting; the engine does not manufacture cash from absent pay dates.
Metrics include return/drawdown, risk, turnover and benchmark diagnostics; read
sample-size limits rather than interpreting annualization as proof.

For real execution inputs supply documented raw prices and the sourced action
ledger schema in [backtesting.md](backtesting.md). The explicit factor-file proxy
exists for historical diagnostics but remains incomplete and disallowed for
Phase 12 qualification. Custom strategies implement the existing target-signal
interface and only use the provided available-history context; do not inspect
future rows inside strategy code.

## Features, targets and machine learning

```bash
uv run --frozen --all-extras python examples/ml_research_demo.py --output data/research/NEW_RUN
uv run --frozen --all-extras quantlab research \
  --experiment /path/to/reviewed-development-only.yaml --output data/research/ANOTHER_RUN
```

The demo is explicitly synthetic. Start from
[ml-research.example.yaml](../configs/ml-research.example.yaml); replace each
snapshot/action/source path, universe, dates and outputs deliberately. Research
YAML is distinct from data TOML, discovery study YAML and Phase 12 protocol YAML.

Causal feature groups cover momentum/lagged returns, mean reversion, volatility,
volume/liquidity, market regime, technical indicators and relative strength.
Window lengths are configured by `FeatureConfig`. Features exclude future labels
and timing columns; preprocessing is fitted on training data. Targets include
stock/excess return, positive-excess direction and future volatility, with allowed
horizons 1/5/10 sessions in discovery. Return labels use next-eligible-open to
horizon-open total returns, not same-close executable returns. Volatility target
has its own definition; it is not a direction label.

Models: Ridge regression; logistic classification; Random Forest, LightGBM and
CPU XGBoost regression/classification. Model-target mismatches fail. Seeds,
threads, feature schema, train preprocessing and dependency versions are pinned.
Walk-forward training uses chronological validation, purge and embargo; portfolio
replay uses OOS scores, shared cash and known-at-decision sizing. Comparisons
include momentum, mean reversion, equal-weight, random and SPY where configured.
Score ranking is not a pairwise/listwise learning-to-rank implementation.

Outputs include fold predictions, predictive metrics, portfolio comparisons,
model metadata/serialization and provenance. Load only trusted model artifacts
with matching versions; joblib/pickle is not an untrusted input format. Offline
`examples/model_analytics.py` extracts coefficients/diagnostics from reviewed,
version-compatible artifacts; the web API does not deserialize them. Run that
script's `--help` for its explicit artifact/output arguments.
`examples/verify_action_reference.py` separately checks the archived independent
action reference; inspect its `--help` and coverage limitations before use. It
does not certify a full event ledger or remove Phase 12 data gates.

**Holdout caution:** the legacy runner reads configured snapshots before filtering.
For a no-protected-byte-read requirement, use physically development-only inputs;
do not point it at a full snapshot containing the final holdout. Phase 12 fitting
is blocked pending a reviewed safe adapter and eligible data. Full schemas,
feature/label formulas and model interfaces: [ml-research.md](ml-research.md).

## Discovery, tracking and reproducibility

Use [discovery.example.yaml](../configs/discovery.example.yaml) to specify a
bounded study referencing a reviewed research YAML. It fixes feature sets,
conditional model spaces, target/horizon, scoring, portfolio rules, budgets and
eligibility. Finite integer/float/categorical spaces are supported; arbitrary
Python/eval and generated combinations are not.

`quantlab discovery` supports `run`, `batch`, `study`, `resume`, `list`, `compare`, `report`,
`reproduce` and `rejected`; use the generated [CLI reference](cli-reference.md)
for exact required arguments. `study` launches the configured bounded search; `resume`
retains its policy/data identity and budgets. `run` evaluates a configuration, `batch` takes multiple
parameter files; reproduction selects an actual attempt. Lists, comparisons and reports distinguish eligible, rejected and failed attempts.
No report alone qualifies a strategy.

SQLite stores immutable experiment definitions and numbered attempts; each
attempt records parameters, seed, data seal, code identity, role, timing,
resources, metrics, failures and artifacts. Optuna drives bounded proposals;
local MLflow records tracking/artifact links. Completed duplicates reuse actual
results rather than counting as new independent evidence. Failures/prunes count
against budgets and remain in history. One controller owns a root. Use a new
root for a changed policy; never clear failures to improve reported performance.

Historical demonstration entry point:
`examples/discovery_demo.py --allow-factor-proxy`. It downloads archive data and
runs a deliberately small diagnostic study. **Do not run it for Phase 12**: its
preparation opens original full-period snapshots before producing development
seals. `--synthetic` is an explicit software-test alternative, never market
profitability evidence. Read [discovery.md](discovery.md) before reproducing a
historical run outside this campaign.

## Statistical validation and holdouts

Start from [validation.example.yaml](../configs/validation.example.yaml). The
validation pipeline imports candidates, retains search history and runs rolling
or expanding chronological refits, costs, robustness and statistical diagnostics.
`quantlab validate` exposes `run`, `walk-forward`, `robustness`, `confidence-intervals`, `multiple-testing`,
`report`, `compare`, `list`, `rejected` and `eligible`; exact syntax
is in the CLI reference. Reports retain rejections instead of publishing only a
shortlist. `examples/statistical_validation_demo.py` reproduces the old diagnostic
workflow; it is not the Phase 12 campaign and its archive-verification preparation
must not run under the current no-protected-byte-read policy.

Block-bootstrap intervals acknowledge serial dependence. PSR/DSR and family
corrections require their assumptions/sample size/history; unavailable values
stay null. Reused development windows are diagnostics, not independent
confirmation. Transactions costs, regime/parameter sensitivity, concentration,
instability and failed evaluations belong in the result. Inspect both candidate
rejections and the complete multiple-testing history, including controls/variants.

Holdout vaults persist SEALED/authorization/consumption states under canonical
SQLite ledgers. They are not a way to get another tuning period. No audit,
agent, dashboard or campaign grants automatic evaluation permission. Never reset
a vault, copy it to evade history, or read reserved bars/results for convenience.
Phase 12 reads only ID/state metadata. Details:
[statistical-validation.md](statistical-validation.md),
[audit](statistical-validation-audit.md).

## Portfolio construction and risk

```bash
uv run --frozen --all-extras python examples/portfolio_demo.py \
  --output data/portfolios/NEW_RUN --stress
```

This is a research mechanics demonstration using previously rejected candidates;
it does not make them eligible. Begin real configuration work from
[portfolio.example.yaml](../configs/portfolio.example.yaml). `quantlab portfolio`
supports `create`, `register`, `allocate`, `backtest`, `stress`, `report`, `risk`
and `strategies`. Create references validated source/input files and dates;
register names/strategy IDs; allocate selects `equal`, `fixed`,
`inverse_volatility`, `risk_parity` or `volatility_target`.

Multiple strategies share one cash account. Target aggregation/netting and
attribution are explicit rather than independently funding each strategy.
Allocation and sizing use observable information. Limits cover gross/net and
leverage exposure, position/sector/correlated/strategy concentration, liquidity,
orders, cash and drawdowns/losses. Suspension and stress outputs explain blocked
allocations. Unknown correlations are conservatively grouped. No optimization
method can turn negative/unsupported strategies into a qualified investment.
Full settings and reports: [portfolio.md](portfolio.md).

## Futures data, research and accounting

```bash
uv run --frozen --all-extras quantlab futures specifications
uv run --frozen --all-extras python examples/futures_demo.py --output data/futures/NEW_RUN
```

Specifications cover ES/MES/NQ/MNQ multipliers, ticks and contract accounting.
The actual recorded real archive is ESZ13, five regular sessions in October 2013;
two OOS sessions cannot establish strategy significance. It does not verify
multi-year MES/NQ/MNQ downloads or realistic historical margin schedules.

`futures import` uses an explicit contract-spec file, contract, date range,
store and provider (`lean`, licensed `databento`, or your authorized `csv`).
Databento requires configured credentials/entitlements and an explicit maximum
download cost; zero budget does not authorize a paid request. Raw-contract
prices, auxiliary quote/OI inclusion, sparse coverage and synthetic status are
explicit flags rather than inferred. Use `inspect`, SELECT-only `query` and
`validate-history` to check returned snapshot IDs before research.

`continuous` supports calendar/lagged-volume rolls and optional back-adjustment
for research features. Execution still uses actual contracts and prices; adjusted
continuous series are not directly tradable. `backtest` selects momentum, VWAP,
opening-range, regime or buy/hold controls and requires an explicit holdout start.
`train`, `research`, `discover`, `resume`, `report`, `validation-report` use the
reviewed futures config. See the CLI reference for flags and
[futures-research.example.yaml](../configs/futures-research.example.yaml).

Accounting uses signed integer contracts, tick rounding, multipliers, fees,
realized/unrealized P&L, initial/maintenance margin and rolls; it does not debit
full notional as stock purchase cash. Futures features are causal intraday
observations, not equity features silently relabeled. Overlapping-label purging,
cost stress, resource supervision and rejected candidates remain explicit.
Details: [futures.md](futures.md), [coverage audit](futures-audit.md).

## Market feeds and simulated paper trading

```bash
uv run --frozen --all-extras python examples/paper_demo.py --output data/paper/NEW_RUN
uv run --frozen --all-extras quantlab paper positions --database data/paper/NEW_RUN/account.sqlite
uv run --frozen --all-extras quantlab paper report --database data/paper/NEW_RUN/account.sqlite
```

The demo replays archival data and explicitly modeled liquidity. It is not a
verified realtime feed or actual broker paper account. `paper replay --output`
provides the CLI replay workflow. `paper start --paper-config` runs the reviewed
simulated service using [paper.example.yaml](../configs/paper.example.yaml);
it requires pre-provisioned deployment eligibility for real-time strategies.
Research-only strategies may be used in historical replay, not self-promoted.

Read commands: `positions`, `orders`, `fills`, `equity`, `strategies`, `logs`,
`report`, each with `--database`. Controls: `pause`, `resume`, `stop`, `kill`,
`reset-kill`, `connect`, `disconnect`, with database and reason (strategy where
applicable). Controls are durable requests; **queued is not applied**. The
running single account writer journals acknowledgement. Kill blocks new fills
and cancels pending simulated orders, retaining positions; no automatic
liquidation occurs. Resume is separate from kill reset and eligibility checks.

MarketEvent validates UTC observation/receive time, instrument, bid/ask/size,
sequence and replay/delayed/realtime mode. Duplicate/out-of-order/gap handling,
freshness and session checks fail closed. Official Alpaca REST/WebSocket quote
adapters use `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY`; IEX/SIP/delayed entitlements
differ. No credential or allowlist means no verified external stream. A futures
licensed-client boundary is not a deployed verified streaming transport.

OMS supports market, limit, stop, stop-limit, DAY/GTC, partial fills, cancellation,
expiry and rejection. Only later quotes beyond configured latency can fill;
participation consumes shared observable liquidity. Stable client IDs reject
changed intent. Pending orders reserve risk/cash; multiple strategies share one
master equity/futures account. Trade-only updates do not invent executable quotes.
Models require pinned hashes, exact schema/dependencies and trusted artifacts.
Prediction latency/drift/outcome logs are monitoring hooks, not auto-retraining.
SQLite WAL/FULL journals, state hashes and financial reconstruction support
restart. Details and modeled-depth assumptions: [paper-trading.md](paper-trading.md).

## Dashboard and API

```bash
npm --prefix dashboard ci
npm --prefix dashboard run build
uv run --frozen --all-extras quantlab dashboard --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Development frontend:
`npm --prefix dashboard run dev -- --port 5173`; its API proxy expects the backend.
Stop foreground servers with Ctrl-C. The production backend serves the built UI.

Views cover overview, datasets/provenance, experiments, model analytics,
discovery, validation, backtests, portfolios, paper, agent, live readiness and
health. Search/sort/page, compare selected summaries, inspect full actual JSON,
export JSON and paper-fill CSV, and read measured equity/drawdown/exposure charts.
Missing observations are unavailable, never favorable defaults. SSE refresh and
polling update artifacts/account state; they are not proof of live market data.

[dashboard.catalog.yaml](../configs/dashboard.catalog.yaml) is the curated
allowlist. Add reviewed report/database/chart paths after generating artifacts;
ignored local `data/` will be missing in a fresh checkout. Do not catalog protected
holdout data. Health and final-holdout badges inspect approved metadata only.

Loopback defaults to read-only. Remote binding requires role tokens, each distinct
and at least 24 characters: `QUANTLAB_VIEWER_TOKEN`, `QUANTLAB_OPERATOR_TOKEN`,
`QUANTLAB_RESEARCHER_TOKEN`. Enter a token through the UI; it stays in memory,
not browser persistent storage. Viewer reads, researcher submits/cancels named
bounded jobs, operator queues confirmed paper controls with reasons. Neither role
can invent a strategy approval or activate LIVE. API jobs accept approved arguments,
not arbitrary commands/paths/Python. Inspect the FastAPI schema at `/docs` for
exact routes and typed payloads; use bearer authentication for protected requests.

Remote hosting needs reviewed TLS/authentication/reverse-proxy controls. If using
the ASGI factory directly, set `QUANTLAB_BIND_HOST` to the actual interface.
Details: [dashboard.md](dashboard.md), [architecture](dashboard-architecture.md).

## Bounded research agent

```bash
uv run --frozen --all-extras quantlab agent run \
  --agent-config configs/agent.example.yaml --root data/agent --scripted-engineering
uv run --frozen --all-extras quantlab agent list --root data/agent
uv run --frozen --all-extras quantlab agent report --root data/agent --session SESSION_ID
uv run --frozen --all-extras quantlab agent pause --root data/agent \
  --session SESSION_ID --reason 'review observations'
```

The initial executable adapter is **futures-only**. Scripted engineering is a
fixed planner, not an LLM. Plans specify hypothesis, biases, rejection, market,
data, model, target and evaluation. Independent policy validates exact tool/data
scope; model text cannot change risk, costs, holdout access or budgets.

For an actual OpenAI-compatible HTTPS or explicitly local HTTP LLM, review the
endpoint, model, structured-output/tool capabilities, pricing and positive spend
budget, configure `QUANTLAB_LLM_API_KEY` securely, then omit the scripted flag.
Defaults deliberately block paid calls. Reservations conservatively count toward
spend even on uncertain failures; provider usage is logged separately and is not
an invoice. No blind retries after uncertain billing. External LLM behavior is
unverified here.

`resume`, `cancel`, `emergency-stop` persist control reasons. Resume retains policy,
source/data identity, history and all budgets; then start the same policy/session
with `run --session`. Changed code/policy invalidates resume. Limits include
iterations, controls/failed trials, wall time, resources, concurrency, token/context
size and API spend. Stored memory includes failures and deduplication, not invented
prior research. `propose-code --text FILE` quarantines text; it never executes or
applies code. There is no generated-code sandbox executor, broker tool, equity
campaign executor, promotion permission or holdout evaluation tool. Full operation:
[research-agent.md](research-agent.md).

## Controlled broker sandbox

```bash
uv run --frozen --all-extras quantlab execution sandbox-demo --output data/execution/NEW_RUN
uv run --frozen --all-extras quantlab execution readiness
uv run --frozen --all-extras quantlab execution inspect --database data/execution/NEW_RUN/oms.sqlite
```

The demo uses an explicit **mock broker and synthetic engineering quotes**.
`readiness` reports blockers; it cannot enable LIVE. Distinguish BACKTEST, local
PAPER simulation and BROKER_SANDBOX. The only external broker adapter is Alpaca's
PAPER equity endpoint; it rejects futures and has no live-host fallback.

For a separately reviewed actual PAPER engineering test, copy and review
[execution.sandbox.example.yaml](../configs/execution.sandbox.example.yaml), exact
account, official feed/entitlements, PAPER keys, private signing key, risk and
bounded signal. The commands `approve-sandbox-test --actor --reason --minutes
--output` and `service --execution-config` require that reviewed config. Default
service behavior monitors. `--arm-approved-sandbox-test` can submit one bounded
PAPER test order only when all gates pass. **Do not run arming/approval as a setup
step.** A sandbox test approval is not research qualification or deployment approval.
See [production.md](production.md) for the complete reviewed sequence.

Signed capabilities bind operation/payload/account/mode/expiry; strategy approval
also pins model, definition, risk and source. Durable intent and stable client IDs
precede HTTP. Uncertain acknowledgement suspends; reconcile by ID rather than
blindly resubmitting. Broker cash/positions/open orders/activities must reconcile;
fees, paging limits and unsupported non-fill activities are explicit limitations.

`execution pause --strategy --reason`, `kill --reason [--cancel-open]`, `backup`
and `restore` all require a database. Kill immediately persists a new-order block;
external cancellation is separately requested and must reconcile. Positions remain.
No emergency liquidation policy is enabled. Reset/rearming needs reviewed state,
fresh observations and explicit authority; old approval/code does not auto-resume.
No setting or checklist makes LIVE available. Details:
[controlled-execution.md](controlled-execution.md), [readiness](go-live-readiness.md).

## Deployment, recovery and incidents

Review [production.md](production.md), [incident-response.md](incident-response.md),
`deploy/compose.yaml`, cloud override and systemd examples before running services.
Containers are a deployment option, not required for local research. Compose
defaults to the dashboard; the sandbox profile remains separate and unarmed.
The nonroot image has read-only roots, dropped capabilities, resource limits and
persistent state. Data mounts need UID/GID 10001 ownership. Keep managed Cloud CA
trust/proxy settings; the cloud override mounts CA at runtime. Liveness is not
trading readiness. Research loops are not unlimited restart services.

Use the supported SQLite backup API rather than copying a live main file without
its WAL. For a verified execution database:

```bash
uv run --frozen --all-extras quantlab execution backup \
  --database data/execution/NEW_RUN/oms.sqlite --output data/execution/backup.sqlite
uv run --frozen --all-extras quantlab execution restore \
  --database data/execution/backup.sqlite --output data/execution/RESTORED.sqlite
```

Keep backups encrypted/off-machine, signing keys separate, and test a new restore
destination. Restarts verify hashes/accounting and remain suspended. Reconcile
before any reviewed resume. Never delete journals, reset funds or change client
IDs to conceal an uncertain order. Incident response distinguishes blocking new
orders, cancelling orders and liquidating positions; these are different actions.
Alerts remain local structured records unless an explicitly authorized transport
is configured. No external notifications are sent by this guide.

## Phase 12 research workflow

Read [the initial report](phase12/README.md), [full instructions](phase12/instructions.md),
[backlog](phase12/research-backlog.yaml), [protocol](../configs/phase12/equity-ml-campaign.yaml)
and [candidate registry](phase12/candidate-registry.json).

```bash
uv run --frozen --all-extras python examples/phase12_equity_campaign.py
```

This reads only existing pre-holdout normalized snapshots and registry/ledger
metadata, checks integrity and writes `docs/phase12/preflight.json`. Expected exit
2 means BLOCKED_DATA. It never fits models or schedules work; the protocol is not
native research YAML. Missing local inputs or broken integrity fail distinctly.
Current results: eight audited snapshots; zero fits/trials/candidates/promotions.
The initial eight model/feature hypotheses remain proposals.

Next work is complete certified PIT/action/delisting data, a reviewed prefix-only
equity adapter, independent confirmation dates and calibrated costs/capacity.
Do not turn on proxy-action opt-ins to bypass scientific gates. The reserved 2019
equity and 2013-10-14 futures periods remain untouched. No salary-replacement or
capital feasibility estimate is supported by current evidence. Expansion and
deployment require separate authorization after the initial result review.

## Files, Python extension points and troubleshooting

| Location | Purpose and normal use |
| --- | --- |
| `configs/` | Copy reviewed examples for each distinct schema; do not share one config across command families |
| `src/quantlab/data/` | `DataRequest`, provider protocol/Download, validation, ingestion, `SnapshotStore`; extend with a legitimate source adapter |
| `backtesting/`, `strategies/` | Daily adapters, target signals, event replay, actions, costs/accounting; add causal strategies through the existing interface |
| `features/`, `ml/`, `research/` | FeatureConfig, native labels/folds, ModelSpec/ResearchModel, experiment loading/running; preserve training-only fitting |
| `discovery/`, `statistical/` | Seals, registries, supervised workers, tracking, validation, statistical reports and canonical holdout controls |
| `portfolio/`, `futures/` | Shared allocations/risk and actual-contract accounting/data/research |
| `paper/`, `execution/` | Market events, simulated OMS, journals and separately authorized sandbox adapter |
| `agent/`, `web/`, `dashboard/` | Bounded orchestration, curated authenticated API and UI |
| `examples/` | Explicit software/historical workflows and operational audit scripts; inspect `--help` before execution |
| `tests/`, `dashboard/src`, browser tests | Accounting/causality/integrity/control regression checks and UI checks |
| `data/` | Ignored vendor data, snapshots, models, registries, vaults and reports; back up deliberately |
| `docs/blueprint.md`, `progress.md` | Preserved roadmap and historical implementation status; Phase 12 report gives current empirical status |

No package-internal class is a new permission boundary: Python APIs must preserve
same data/holdout/risk controls as CLI. See [architecture](architecture.md) and
[architecture audit](architecture-audit.md) for boundaries and examples. Trusted
local code is not an OS sandbox for arbitrary imported user Python.

| Symptom | Interpretation and next action |
| --- | --- |
| Proxy 403 | Check current attached instance's enforced host policy; apply supported settings and retry fresh, never bypass TLS/proxy |
| No CSV/unknown symbol | Check local/vendor mapping, requested dates and actual response; no synthetic fallback |
| Session/schema/hash failure | Quarantine bad revision, verify source and create a new snapshot; do not edit immutable files |
| Adjusted/unknown basis rejected | Obtain evidenced unadjusted bars and event coverage |
| Missing artifacts/dashboard blank | Reproduce or supply intended ignored data and review catalog paths; unavailable is correct |
| Model version/source mismatch | Use exact trusted artifact dependencies/source; regenerate reviewed runs rather than rewriting metadata |
| Duplicate/failed trial | Read registry reason/worker log; retain history and budgets |
| Paused/killed after restart | Inspect journal, queue acknowledgements, fresh data and reconciliation; restore alone does not authorize resume |
| Missing statistics | Too little independent evidence or unsupported assumptions; never fill null with zero |
| No candidates | Read all rejections and data gates; do not relax filters after inspecting results |

Offline verification: `uv run --frozen --all-extras pytest -q` and Ruff. Frontend:
`npm --prefix dashboard test`, `npm --prefix dashboard run build`,
`npm --prefix dashboard run test:e2e` (requires the browser/runtime setup described
in the dashboard guide). Live tests are optional and explicitly gated; inspect
`tests/test_live*` and documented environment switches before enabling. Do not
run archive live tests during Phase 12 if they fetch full protected source archives.
No mocked/offline pass establishes external connectivity.

## Complete CLI reference

The [generated reference](cli-reference.md) includes **every leaf command and its
actual `--help`**, including required flags, choices and defaults. It is generated
from the checked-in parser without dispatching commands or downloading anything.
Use `uv run --frozen quantlab COMMAND --help` for the running checkout. This guide
explains workflows and prerequisites; the reference supplies exhaustive syntax.
