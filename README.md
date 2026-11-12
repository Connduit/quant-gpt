# Quant Research Lab

Milestone 1: a CPU-compatible, reproducible historical US equities data foundation.
No strategies, predictions, backtests or trading execution are implemented yet.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the checkout root:

```bash
uv sync --frozen --extra dev
uv run --frozen pytest -q
uv run --frozen ruff check src tests
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

**Cloud access:** HTTPS to `stooq.com` must be permitted. The initial onboarding
request was blocked by the proxy; real downloads have not been verified here.
Offline and mocked HTTP tests do not need that access.

## Configuration

`--config configs/data.toml` is explicit; configuration files are not auto-loaded.
Defaults: `./data`, provider `stooq`, 30-second timeout and `INFO` logging.
TOML paths resolve relative to the configuration file.

Environment overrides: `QUANTLAB_DATA_DIR`, `QUANTLAB_PROVIDER`,
`QUANTLAB_TIMEOUT_SECONDS`, `QUANTLAB_LOG_LEVEL`. Environment paths and CLI
`--data-dir` paths resolve relative to the current directory. CLI `--data-dir`
and download `--provider` take precedence. Unknown keys and invalid values fail.
Global options precede subcommands. Neither provider needs API secrets.

## Architecture

- `config.py`, `logging.py`: validated TOML settings and UTC JSON logs.
- `data/providers/`: typed protocol, Stooq adapter and explicit synthetic fixture.
- `data/validation.py`: schema, finite/positive prices, OHLC consistency, integer
  nonnegative volume, duplicates and XNYS session completeness.
- `data/ingestion.py`: caching, validation and snapshot publication.
- `data/storage.py`: immutable CSV/Parquet/manifest snapshots, checksums and DuckDB.
- `cli.py`: download, inspect and SELECT query commands.

See [data design](docs/data-design.md) for timestamp, adjustment and provenance
contracts, and [architecture](docs/architecture.md) for extension boundaries and
next steps.

These downloads **are not a survivorship-free, point-in-time research database**.
Corporate actions, delistings, historical universes and verified unadjusted
execution prices are not included. Vendor adjustment semantics are recorded as
unspecified, never assumed suitable for execution. Neither fixture data nor
vendor downloads establish a profitable strategy.
