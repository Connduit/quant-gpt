# Real market-data access verification

On November 12, 2026, a fresh `httpx.Client` request using the application's
inherited proxy and CA trust produced **`httpx.ProxyError: 403 Forbidden`** for
`https://stooq.com/q/d/l/?s=spy.us&d1=20180102&d2=20180110&i=d`.
Runtime status reported current observations and an enforced restricted policy
without `stooq.com`. This is an HTTPS proxy CONNECT policy rejection, before
origin TLS/HTTP. It does not demonstrate a Stooq outage or an origin DNS/firewall
failure. Proxy reachability and HTTPS work for the allowed fallback hostname.
TLS verification remained enabled. No proxy, DNS or security bypass was used.
See [sanitized connectivity evidence](market-data-connectivity.json).

## Required supported Stooq configuration

The environment administrator/user must allow the exact HTTPS destination host
`stooq.com` (port 443), save/apply that setting to this running environment, and
publish the reusable configuration for future tasks. The existing onboarding
draft already contains the host, but draft saving did not apply it to the
running instance. No current-instance network-change tool is available here.
After application, refresh runtime status and use a fresh connection:

```bash
QUANTLAB_LIVE_PROVIDERS=1 QUANTLAB_LIVE_PROVIDER=stooq uv run --all-extras pytest -m live -q
```

No credentials are required. Any redirect destination would need separate
verification/permission. Successful Stooq downloads would still have unspecified
adjustment semantics and would not establish corporate-action coverage.

## Verified working alternative

The interchangeable `LeanProvider` downloads a pinned QuantConnect LEAN daily
archive over permitted HTTPS to `raw.githubusercontent.com`. A fresh SPY ZIP
request returned **200**, 103,363 bytes. The application then downloaded,
normalized and stored eight real daily histories: AAPL, AIG, BAC, FB, GOOGL, IBM,
WM and SPY. Each contains 1,195 complete XNYS sessions from April 3, 2014 through
December 31, 2018. No reserved 2019 observations were used. Exact snapshot IDs,
source hashes, dates and action limitations are in the
[dataset manifest](market-data-verification-datasets.json). Inputs are local at
`data/network-verification/real-inputs`; raw vendor data is ignored by Git.

```bash
uv run quantlab --data-dir data/live-download download SPY --provider lean --start 2018-01-02 --end 2018-01-10
QUANTLAB_LIVE_PROVIDERS=1 uv run --all-extras pytest -m live -q
```

The CLI download uses the existing ingestion/storage interface; corporate-action
ledgers are a separate requirement. The universe importer additionally fetches
factor files and an independent pinned Plotly/Yahoo Apple price reference. All
prices and volume pass existing normalization, timestamp, symbol, OHLC and XNYS
missing-session checks. LEAN source specifies raw prices scaled from deci-cents;
the 2014 Apple split and 506 independent price observations support that
interpretation. The independent check is limited to Apple prices, not all events.

**Complete corporate-action coverage is unavailable.** Factor changes are
represented, but their rounding, missing payment dates, and possible noncash
corporate events prevent certification. Unknown payment dates remain null;
distributions are non-spendable receivables, not invented cash payments. The
explicit factor proxy is supported for diagnostic research only. Static selected
survivors are not a historical membership universe. No fully action-aware or
unbiased-universe claim is made.

This archival alternative has no authentication, subscription charge or published
service-level/rate-limit guarantee. It is a bounded historical sample, not a
current comprehensive vendor feed. Requests have timeouts and no automatic retry
loop. Source data is attributed to AlgoSeek with all rights reserved; public
GitHub availability does not grant redistribution/commercial-use rights. Consult
upstream terms for intended use. Raw files are not committed. See LEAN's pinned
`Data/equity/usa/readme.md` and source references in the manifest.

## Test behavior and research integration

Offline/mocked tests remain enabled. Live tests are marked `live` and skipped
unless `QUANTLAB_LIVE_PROVIDERS=1`. Transport/proxy/TLS and HTTP-status failures
use separate provider exception classes and live failure messages; malformed
payload and normalized-data failures remain data/application errors. Default
live tests exercise SPY, Apple and IBM through full ingestion and reload.

Milestone 5 uses these verified pre-holdout histories and the existing sealed
research artifacts. Its reports must retain the action/universe limitations;
synthetic fixtures test functionality only. Stooq itself remains blocked until
the supported setting is applied. The working alternative satisfies real HTTPS,
application download, validation, snapshot and research-loading requirements.

Verification: **170 offline tests passed, three live tests skipped by default**;
the explicit live run passed all **three provider round trips**. The first
concurrent baseline run encountered the intentional code-change integrity guard
while provider edits were in progress (169 passed, one failed); the unchanged
source rerun passed all 170.
