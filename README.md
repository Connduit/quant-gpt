# Quant Research Lab

CPU-compatible quantitative research infrastructure through Milestones 1–11,
including historical equities/futures, bounded ML discovery, statistical validation,
portfolios, paper simulation, a dashboard and controlled broker sandbox engineering.

Start with the [setup-to-strategy quick start](docs/quick-start.md),
the [complete feature usage guide](docs/user-guide.md) and
[exhaustive CLI reference](docs/cli-reference.md). The
[Phase 12 research audit](docs/phase12/README.md) records current data blockers;
no strategy currently qualifies for paper/live deployment.

The [complete project blueprint and roadmap](docs/blueprint.md) preserves the
original specification, including all core capabilities, market phases and ten
development milestones. It describes the long-term plan; this README documents
the current implementation.

The [subsequent development instructions](docs/development-instructions.md) update
the roadmap to 11 milestones. See [current progress](docs/progress.md), the
[architecture audit](docs/architecture-audit.md) and [backtesting guide](docs/backtesting.md).

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the checkout root:

```bash
uv sync --frozen --all-extras
uv run --frozen pytest -q
uv run --frozen ruff check src tests examples
```

The checked-in `uv.lock` pins dependencies. Use `uv lock` deliberately when updating
them. In the managed cloud environment, use `export UV_CACHE_DIR=/workspace/.cache/uv`
if the default cache is not writable. `uv run` activates the project's `.venv`
automatically; the earlier onboarding research sandbox is separate.

## Local environment file

Keep local settings in `.env` at the repository root. This file is excluded
from Git. To set up another computer, copy
`.env.example` to `.env`, fill in your provider credentials, and
generate distinct dashboard tokens with
`python -c "import secrets; print(secrets.token_urlsafe(32))"` for each role.
Use at least 24 characters per token. Keep the file private.

Install dependencies and build everything with one command (requires Python 3.12+,
uv, and Node.js with npm):

```bash
python build.py
```

Use `python3 build.py` if your system names Python `python3`. Rerun this command
after pulling updates. It stops if any installation or build step fails.

Start the local dashboard from the repository root:

```bash
python start.py
```

The start script loads the project's `.env` and binds to localhost. Stop it with
Ctrl+C. Use `python start.py --port 8001` to choose a different port.

Enter the matching viewer, operator, or researcher token from `.env` when the
dashboard requests access. Other CLI commands can use the same
`uv run --env-file .env` prefix. Existing shell variables take precedence;
unset an old value if you want the file's value to apply. Restart the dashboard
after editing `.env`.

The broker sandbox uses its separate
`QUANTLAB_ALPACA_PAPER_KEY` and `QUANTLAB_ALPACA_PAPER_SECRET` fields, which can
remain empty for dashboard use. Never commit `.env` or share its contents.

## Offline demonstration

The built-in **SYNTH** fixture is invented test data, not historical market data.
It covers January 2–8, 2024 (five XNYS sessions), with no credentials or network.

```bash
uv run quantlab --config configs/data.toml download SYNTH \
  --provider fixture --start 2024-01-02 --end 2024-01-08
```

The JSON result contains `snapshot_id`, `cached`, and the provenance manifest.
Replace `SNAPSHOT_ID` below with the returned full identifier:

```bash
uv run quantlab --config configs/data.toml inspect SNAPSHOT_ID
uv run quantlab --config configs/data.toml query SNAPSHOT_ID \
  --sql 'SELECT session_date, close, volume FROM bars ORDER BY session_date'
```

Identical downloads reuse a checksum-verified snapshot. `--refresh` obtains a new
immutable revision; old snapshots remain unchanged. JSON logs go to stderr and
JSON results to stdout. Failures return a nonzero exit code without publishing
partial snapshots.

## Historical equities

Alpaca is the default provider; Databento is available with an explicit dataset
and estimated download-cost cap. Configure [server secrets and data-host access](docs/market-data-setup.md),
then use the Data library dashboard forms, or optionally:

```bash
uv run quantlab --config configs/data.toml download SPY \
  --provider alpaca --alpaca-feed sip --start 2018-12-03 --end 2018-12-31
```

Raw minute data is aggregated over regular XNYS sessions, then validated and saved
as immutable daily snapshots. Feed/dataset variants have separate cache identities.
Databento checks coverage and estimated cost before each stream; its default cap
is zero. Stooq/LEAN remain explicit legacy CLI options for reproducibility, with
no automatic fallback. Current cloud probes found missing keys and blocked data
hosts; live provider access is not yet verified. Offline tests need no network.

## Configuration

`--config configs/data.toml` is explicit; configuration files are not auto-loaded.
Defaults: `./data`, provider `alpaca`, 30-second timeout and `INFO` logging.
TOML paths resolve relative to the configuration file.

Environment overrides: `QUANTLAB_DATA_DIR`, `QUANTLAB_PROVIDER`,
`QUANTLAB_TIMEOUT_SECONDS`, `QUANTLAB_LOG_LEVEL`. Environment paths and CLI
`--data-dir` paths resolve relative to the current directory. CLI `--data-dir`
and download `--provider` take precedence. Unknown keys and invalid values fail.
Global options precede subcommands. Alpaca and Databento require server-side keys.

## Backtesting demonstration

```bash
uv run python examples/backtest_demo.py
```

This loads the existing **synthetic** fixture and runs momentum, mean reversion
and buy-and-hold, exporting trade logs, equity curves, orders, metrics, provenance
and benchmark comparisons under `data/backtests/milestone-2-demo`. Use
`--output data/backtests/another-run` to preserve prior results. No live execution
or profitability claim is involved.

To run an individual verified snapshot:

```bash
uv run quantlab --config configs/data.toml backtest SNAPSHOT_ID \
  --strategy momentum --lookback 2 --shares 10 --initial-cash 10000 \
  --output data/backtests/my-run
```

Daily closing signals execute only at a strictly later eligible session open.
Cash accounting includes commissions, spread/slippage, splits and cash dividends.
Stooq's unknown-adjustment prices are **rejected as execution inputs**; real runs
require declared unadjusted CSV data and a complete corporate-action ledger.
See [backtesting](docs/backtesting.md) for raw-data import, ledger format, metric
definitions and the hand-calculated accounting checks.

## Machine learning research

```bash
uv run --frozen --extra ml python examples/ml_research_demo.py
```

Runs a seeded **synthetic** multi-stock experiment with Ridge, logistic regression,
Random Forest, LightGBM and XGBoost. It produces purged walk-forward predictions,
shared-cash ranking backtests, SPY/random/momentum/mean-reversion/equal-weight
comparisons, saved models and reports. A final holdout is excluded from feature,
label, model and trading evaluation. Existing outputs are preserved; use `--output`
to choose a new directory. See the [ML research guide](docs/ml-research.md) for
feature/target definitions, YAML, model interfaces, timing checks and limitations.

Run a saved configuration:

```bash
uv run --frozen --extra ml quantlab research \
  --experiment data/ml-demo-inputs/experiment.yaml \
  --output data/research/repeated-config-run
```

## Architecture

- `config.py`, `logging.py`: validated TOML settings and UTC JSON logs.
- `data/providers/`: typed protocol, Stooq adapter and explicit synthetic fixture.
- `data/validation.py`: schema, finite/positive prices, OHLC consistency, integer
  nonnegative volume, duplicates and XNYS session completeness.
- `data/ingestion.py`: caching, validation and snapshot publication.
- `data/storage.py`: immutable CSV/Parquet/manifest snapshots, checksums and DuckDB.
- `cli.py`: download, CSV import, inspect, SELECT query and backtest commands.
- `backtesting/`: daily adapter, event replay, opening-print execution costs,
  corporate actions, decimal portfolio ledger, metrics and report exports.
- `strategies/`: immutable target signals, available-history contexts and baseline strategies.
- `features/`, `ml/`: configured causal features, execution-aligned datasets,
  chronological purging, CPU models, serialization and predictive evaluation.
- `research/`: YAML experiments and OOS ranking/backtest comparison reports.

See [data design](docs/data-design.md) for timestamp, adjustment and provenance
contracts, and [architecture](docs/architecture.md) for extension boundaries and
next steps.

These downloads **are not a survivorship-free, point-in-time research database**.
Corporate actions, delistings, historical universes and verified unadjusted
execution prices are not included. Vendor adjustment semantics are recorded as
unspecified, never assumed suitable for execution. Neither fixture data nor
vendor downloads establish a profitable strategy.

## Automated strategy discovery

```bash
uv run --frozen --all-extras python examples/discovery_demo.py --allow-factor-proxy
```

Runs a bounded real historical example with Optuna, local MLflow, immutable
experiment records, CPU resource limits, rejection rules and robustness diagnostics.
The recorded run used seven stocks plus SPY, four trials and six diagnostics;
zero strategies qualified and the 2019 holdout stayed untouched. The explicitly
selected factor-file alternative has incomplete corporate-action coverage and
unknown payment dates. See the [discovery guide](docs/discovery.md),
[results](docs/milestone-4-results.md) and [snapshot manifest](docs/milestone-4-datasets.json).
Milestone 5 adds selection-aware statistical diagnostics; see below.

## Statistical validation

```bash
uv run --frozen --all-extras python examples/statistical_validation_demo.py --output data/statistical/NEW_RUN
uv run --frozen --all-extras quantlab validate rejected --reports data/statistical/NEW_RUN
```

Uses saved discovery candidates and verified development-only real snapshots.
The framework adds configurable rolling/expanding retraining, interval purging,
holdout consumption controls, block-bootstrap uncertainty, PSR/DSR, search-history
corrections and execution robustness. Reused development windows are labeled as
diagnostics; no final holdout is evaluated. See [methodology](docs/statistical-validation.md),
[audit](docs/statistical-validation-audit.md) and [results](docs/milestone-5-results.md).
Milestone 6 now provides research-only multi-strategy portfolios.

## Multi-strategy portfolios

```bash
uv run --frozen --all-extras python examples/portfolio_demo.py --output data/portfolios/NEW_RUN --stress
```

One shared cash account, strategy attribution/netting, equal/fixed/inverse-volatility/
risk-parity/volatility-target allocations, sizing, pre-trade risk controls,
suspensions and stress reports. The real example uses two rejected candidates
for research mechanics only; neither is promoted. See [design](docs/portfolio.md)
and [actual results](docs/milestone-6-results.md).

## Futures research

```bash
uv run --frozen --all-extras python examples/futures_demo.py --output data/futures/NEW_RUN
```

Actual-contract ES/MES/NQ/MNQ accounting, causal intraday features, CPU ML,
purged validation and bounded discovery. The verified archival ES example has
only two OOS sessions; all nine candidates remain rejected. No live trading.
See [design](docs/futures.md), [audit](docs/futures-audit.md), and
[actual results](docs/milestone-7-results.md).

## Simulated paper execution

```bash
uv run --frozen --all-extras python examples/paper_demo.py --output data/paper/NEW_RUN
```

Durable orders, one equity/futures account, portfolio risk, model-pinned inference,
restart reconciliation and local alerts. Current strategies are RESEARCH only;
no live streaming is verified. See [operation](docs/paper-trading.md) and
[actual replay results](docs/milestone-8-results.md). Real-money orders are unavailable.

## Research dashboard

```bash
python build.py
python start.py
```

Open `http://127.0.0.1:8000`. The dashboard inspects curated research, models,
validation, backtests, portfolios and journaled paper state. Default local access
is read-only; confirmed writes require role tokens. See [operation](docs/dashboard.md),
[verification](docs/milestone-9-results.md), and [screenshot](docs/dashboard-overview.png).

The Data library now includes historical-download and immutable-snapshot forms.
Alpaca is the default, with Databento as an explicit alternative. Configure
[provider secrets and data hosts](docs/market-data-setup.md) before downloading.
The **API keys** page accepts masked provider keys with operator authorization,
stores them encrypted and applies changes to new downloads without a restart.
Machine learning and Discovery include bounded equity research forms, snapshot
selection, job cancellation and downloadable reports. These require researcher
access and eligible inputs covering the selected research date range. Larger
snapshots are automatically sliced before fitting; Stooq-only snapshots do not satisfy the
raw-price/action/PIT research gate. See [guided workflows](docs/dashboard-workflows.md).

## Bounded research agent

```bash
uv run --frozen --all-extras quantlab agent run --agent-config configs/agent.example.yaml \
  --root data/agent --scripted-engineering
```

Strict plans, approved datasets/tools, persistent research memory, bounded
Optuna/MLflow execution and statistical rejection. The real-data engineering run
used a scripted planner; external LLM integration is unverified. No broker,
holdout-evaluation, generated-code execution or promotion authority is available.
See [operation](docs/research-agent.md) and [actual results](docs/milestone-10-results.md).

## Controlled execution and go-live readiness

```bash
uv run --frozen --all-extras quantlab execution sandbox-demo --output data/execution/NEW_RUN
uv run --frozen --all-extras quantlab execution readiness
```

Signed sandbox scopes, durable orders, shared risk, reconciliation, recovery,
kill controls and deployment artifacts. Current broker verification uses explicit
mocks: external PAPER access is blocked and no strategies qualify. **Real-money
execution remains disabled.** See the [readiness report](docs/go-live-readiness.md),
[execution design](docs/controlled-execution.md) and [deployment guide](docs/production.md).

## What needs to be rebuilt after a change?

Run commands from the repository root. For the dashboard, install dependencies
with `python build.py`, which installs locked Python and frontend dependencies
and builds the dashboard.
Use the installation commands above for the Python application.

| Change | Required action |
| --- | --- |
| README or other documentation | No application rebuild. |
| Application source | Run the build for the affected application, if it has a compilation step, then restart it. An interpreted application generally only needs a restart; a development server with reload enabled may handle source changes automatically. |
| Dependency manifest or lockfile | Install the updated dependencies, then rebuild and restart the affected application. |
| Build configuration or generated-code inputs | Rerun the relevant generation and build steps, then restart the affected application. |
| Runtime environment variables or API credentials | Restart the process so it reads the new values. Rebuild only if the application embeds those variables at build time. |

## Alpaca credentials

Configure these names in the cloud environment settings, with the corresponding
credential in each variable's **value** field:

- `APCA_API_KEY_ID`: Alpaca key ID.
- `APCA_API_SECRET_KEY`: matching Alpaca secret key.
The paper-trading endpoint is `https://paper-api.alpaca.markets`.
The controlled broker sandbox uses `QUANTLAB_ALPACA_PAPER_KEY` and
`QUANTLAB_ALPACA_PAPER_SECRET`; see [deployment](docs/production.md).

Do not use an API key as the variable name or commit credentials to the
repository. The cloud network allowlist must permit the chosen Alpaca hostname
before requests can reach it. A read-only `GET /v2/account` on the selected
trading endpoint can verify authentication without placing orders. HTTP 200
confirms authentication; a proxy connection denial does not establish whether
the credentials are valid. Paper and live trading use different credentials
and endpoints.
