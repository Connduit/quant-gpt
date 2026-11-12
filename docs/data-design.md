# Data contract

The first slice is daily US equities. The normalized schema is independent of
vendor CSV formats. Intraday/futures support will require additional adapters.

| Column | Type | Meaning |
| --- | --- | --- |
| symbol | string | Uppercase local ticker; SYNTH is test-only |
| session_date | date | Exchange-local trading session label |
| timestamp | UTC datetime, microseconds | Scheduled XNYS regular-session close |
| available_at | UTC datetime, microseconds | Following calendar day midnight in New York |
| exchange_timezone | string | America/New_York |
| open/high/low/close | float64 | Vendor prices; basis recorded in manifest |
| volume | int64 | Nonnegative vendor share volume |

Session closes account for holidays, early closes and DST using the recorded
exchange-calendars version. `timestamp` is not a vendor publication timestamp.
`available_at` is only an assumed conservative research cutoff, **not verified
historical knowledge time**. `retrieved_at` records snapshot creation in UTC.
Adjusted history and revisions may incorporate later information, so every
snapshot is marked `point_in_time: false`. Future causal research needs actual
publication/revision times and corporate action history.

Validation rejects malformed/missing values, nonfinite/nonpositive prices,
inconsistent OHLC, fractional/negative/overflowing volume, duplicate dates,
non-session dates and missing expected sessions. Valid vendor rows outside the
requested inclusive range are filtered; remaining rows are sorted. No forward
fill, interpolation or silent deduplication occurs.

Completeness assumes continuously listed, actively trading XNYS-compatible
securities. IPO boundaries, delistings and suspensions require narrower requests
or a future lifecycle-aware policy. XNYS is the session convention, not an
assertion of each ticker's listing venue.

## Storage and queries

```text
data/snapshots/<sha256>/
  source.csv       # exact source payload
  bars.parquet     # validated normalized bars, zstd
  manifest.json    # request, provenance, checksums, versions and limitations
```

Publication uses a temporary directory and same-filesystem atomic rename. The
identifier is SHA-256 of canonical manifest JSON, which includes SHA-256 checksums
of source CSV and Parquet. Reads and cache reuse verify all three. Checksums
protect against accidental corruption, not attackers able to replace the store.
Never edit published snapshots; refresh instead.

Exact provider/symbol/date requests reuse the newest verified snapshot.
`--refresh` downloads the full range into a new revision even if prices did not
change. Corruption fails closed instead of silently overwriting history.
The initial filesystem cache scans manifests and targets individual research use.

DuckDB exposes verified data through the Arrow-backed `bars` relation. Queries
accept one SELECT; external file, network and extension access is disabled.
Queries cannot alter snapshots. Each snapshot loads into memory; larger datasets
will need a partitioned catalog and bounded query/resource controls.
Decimal SQL results (including DuckDB's widened integer sums) serialize as JSON
strings to preserve precision. Integer and floating columns retain numeric JSON types.

## Incremental ingestion

The API and CLI can extend compatible snapshots while preserving the parent:

```bash
uv run quantlab download SYNTH --provider fixture --start 2024-01-02 --end 2024-01-04
# Substitute the returned parent ID below.
uv run quantlab download SYNTH --provider fixture --start 2024-01-02 --end 2024-01-08 \
  --extend PARENT_SNAPSHOT_ID
```

Only dates after the parent's last session are requested. The child manifest
references the parent. Its CSV holds the extension response; its Parquet holds
the combined range. Follow parent links for earlier raw payloads. Start, symbol,
provider, synthetic status and price basis must remain compatible.

**Stooq extension is rejected:** unspecified corporate-action adjustments may
revise the entire history. Mixing old and new vintages could produce inconsistent
prices. Use full-range refresh until corporate-action-aware revision handling
exists. Incremental append is tested with the synthetic fixture and reserved
for future providers with declared compatible semantics.

This milestone does not supply dividends, splits, delistings, historical tradable
universes, sectors, bid/ask or verified execution prices. These gaps must be
addressed before credible strategy validation.
