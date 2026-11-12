# Quant Research Lab

CPU-compatible historical US equities infrastructure and daily event-driven
backtesting, causal features and CPU machine learning research. Milestones 1–5
are implemented, including bounded discovery and statistical validation.

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

## Free historical equities

The adapter uses [Stooq's daily CSV endpoint](https://stooq.com/q/d/?s=spy.us),
which requires no paid subscription or API key:

```bash
uv run quantlab --config configs/data.toml download SPY \
  --provider stooq --start 2024-01-02 --end 2024-01-08
```

Use local US tickers such as `SPY` or `AAPL`; the adapter adds the vendor's `.us`
suffix. Dates are inclusive and must precede today's UTC date. Only daily US
equities with XNYS-compatible sessions are supported. Check current vendor usage
and redistribution terms before using or sharing downloads. Rate limits,
unavailable symbols, CAPTCHA responses and source changes produce errors,
never a silent fixture fallback. There are no automatic retries.

**Cloud access:** Stooq remains blocked by the enforced proxy allowlist. The
working `lean` fallback has verified real HTTPS downloads and immutable snapshots
for SPY and seven stocks. See [connectivity evidence, integration tests and data
limitations](docs/market-data-verification.md). Offline tests need no network.

## Configuration

`--config configs/data.toml` is explicit; configuration files are not auto-loaded.
Defaults: `./data`, provider `stooq`, 30-second timeout and `INFO` logging.
TOML paths resolve relative to the configuration file.

Environment overrides: `QUANTLAB_DATA_DIR`, `QUANTLAB_PROVIDER`,
`QUANTLAB_TIMEOUT_SECONDS`, `QUANTLAB_LOG_LEVEL`. Environment paths and CLI
`--data-dir` paths resolve relative to the current directory. CLI `--data-dir`
and download `--provider` take precedence. Unknown keys and invalid values fail.
Global options precede subcommands. Neither provider needs API secrets.

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
Milestone 6 has not started.
