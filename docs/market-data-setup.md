# Alpaca and Databento historical data setup

The project and dashboard now default to **Alpaca**. The dashboard offers Alpaca
and Databento; it no longer submits Stooq downloads. Old Stooq snapshots and the
explicit legacy CLI option remain readable for reproducibility. No automatic
provider/feed fallback occurs.

## Required environment settings

Open **API keys** in the dashboard sidebar (or **Manage API keys** in Data library).
Connect with your operator access token in the top bar, enter the masked Alpaca
key ID/secret pair or Databento key, and click **Save**. Inputs clear after saving;
stored values are never fetched back into the website. New download jobs use the
saved keys immediately without a server restart.

Managed environment **Secrets** or a protected server environment remain supported
as an alternative. Use only the dedicated settings form for browser entry; do not
enter provider keys in the dashboard access-token field, reports, chat or source files.

| Provider | Server secret names | HTTPS allowlist host |
| --- | --- | --- |
| Alpaca market data | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | `data.alpaca.markets` |
| Databento historical | `DATABENTO_API_KEY` | `hist.databento.com` |

Restrict credential destinations to the corresponding data host. Neither integration
requires a trading/order host. These are separate from `QUANTLAB_ALPACA_PAPER_*`
broker credentials. No live-trading permission is enabled.

Apply/publish hosting/network or environment-key changes and restart the dashboard
server as needed. Website-saved credentials apply to new jobs immediately. Use the
existing `QUANTLAB_RESEARCHER_TOKEN` through **Connect** to submit jobs; managing
credentials requires `QUANTLAB_OPERATOR_TOKEN`. Status reports configuration and
source (dashboard/environment/none) without returning values; it does not verify
connectivity or entitlement.

**Remove** deletes the website-saved override and restores any environment keys
for that provider. Saving Alpaca replaces both fields together. Running jobs keep
their starting keys. HTTPS is required except on loopback connections; saving a key
does not change hosting firewall rules or start a data download.

Saved keys are Fernet-encrypted under `data/dashboard/credentials/providers.enc`.
The directory is mode 0700 and files are mode 0600. A private local `master.key`
is created automatically, so no encryption-key setup is required to use the page.
For managed deployments, `QUANTLAB_CREDENTIALS_MASTER_KEY` can instead supply a
Fernet encryption key outside the data volume. Back up the store and its original
encryption key securely; losing or changing the key prevents decryption. File
encryption and host filesystem permissions are separate protections, not a claim
that another process with the same OS account cannot access the files.

Actual checks on 2026-11-12 found all three key names absent and both HTTPS hosts
denied with proxy `403 Forbidden`. The attached environment still allows only
Stooq as a custom host. The environment-change tool is unavailable here, so these
settings must be applied through the environment settings interface. No paid stream
was requested. See `provider-setup-connectivity.json` for the recorded probe results.

## Dashboard operation

Open **Data library**, select **Historical data provider**, enter symbols/dates,
then click **Download & create snapshots**. The existing job queue, cancellation,
snapshot validation, immutable history and downloadable reports remain in use.
Downloads accept completed historical dates after 2018. Reserved holdout
snapshots can be downloaded and listed but remain blocked from training/discovery.

**Alpaca:** select `sip` for consolidated US equities or explicitly select `iex`
for IEX-only data. Authentication, feed entitlements and historical availability
are verified by the API, not inferred from key presence. Raw 1-minute bars are
paginated with explicit bounds and `asof=<request end date>` so historical ticker
mappings are anchored to the requested period rather than today.
There is no silent downgrade from SIP to IEX. Rate limits fail with a clear status;
the integration does not retry automatically.

**Databento:** select `XNAS.ITCH` or `DBEQ.BASIC` and an estimated USD cost cap.
Zero is the default and permits only zero-cost estimates. Each symbol's coverage
and estimated cost are checked before opening its stream. Estimates are reserved
against a single cap shared across the job, including failed streams. Cached
snapshots do not consume the cap. Vendor billing may differ from its estimate;
this is a pre-download estimate guard, not a hard account billing limit. Downloads
are bounded to 31 calendar days per job and $100 maximum estimated authorization.

Databento's actual metadata determines coverage. Published documentation describes
XNAS.ITCH history beginning in May 2018 and DBEQ.BASIC beginning in 2023.
Both can be downloaded within provider coverage; the research holdout boundary
continues to govern eligibility for training/discovery. Dataset venue coverage is preserved
in provenance and is not relabeled consolidated SIP. Multiple resolved instrument
IDs for one request are rejected until a verified identifier-mapping workflow exists.

Both providers aggregate raw minute bars over XNYS regular sessions, respecting
DST and early closes. The daily open/close are first/last supplied regular-session
minute prices, not certified opening/closing auction prices. No-trade minutes are
not invented; missing entire sessions fail the existing strict validator. Databento
UTC-day `ohlcv-1d` data is deliberately not relabeled as exchange-session OHLCV.

Snapshots contain the derived daily CSV and Parquet, request/feed/dataset/aggregation
provenance, and integrity hashes. Alpaca page-response hashes are retained in
provenance; full original vendor minute payloads are not retained by this adapter.
Provider names include feed/dataset and aggregation version so caches cannot cross
these settings. Refresh preserves prior versions.

Raw prices still do not provide certified corporate-action ledgers, terminal payouts,
historical identifier mappings or PIT universe membership. Existing ML/discovery
data gates stay in place; these adapters alone do not qualify a Phase 12 campaign.
No trained real-data model or complete-provider claim is made from offline tests.

## Installation and deployment

The existing all-extras install includes everything. A dedicated `market-data`
extra also installs the official Databento SDK without requiring futures features.
Alpaca uses the existing HTTP client; no brokerage SDK is needed.

`.env.example` lists the required names. Put settings in the root
`.env` file and start the dashboard with `uv run --env-file .env --frozen
--all-extras quantlab dashboard`. Broker sandbox credentials remain separate. Only download workers receive credentials
for their selected provider. ML/discovery/agent jobs receive none of these keys.
The existing Databento futures adapter remains available for `GLBX.MDP3`, with its
own explicit cost cap; it is not replaced by the equity adapter.

Optional CLI equivalents remain available: `download --provider alpaca --alpaca-feed
sip`, or `download --provider databento --databento-dataset XNAS.ITCH
--maximum-download-cost 0`, with the existing symbol/start/end arguments.

Primary references: [Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbarsingle-1),
[Databento historical API](https://databento.com/docs/api-historical),
[Databento OHLCV semantics](https://databento.com/docs/schemas/ohlcv).

Databento also documents retroactive Nasdaq instrument-ID and coverage changes
effective October 31, 2026. Pin export versions and revalidate identity mappings
after refreshes: [Nasdaq history changes](https://databento.com/blog/nasdaq-historical-data-changes-2026-09).

Verification on 2026-11-12: **355 Python tests passed, 11 skipped**, **13 frontend
tests passed**, **6 Chromium workflow tests passed**, production build and Ruff
passed. Tests cover pagination, raw/feed selection, half-day regular-session
aggregation, cost/coverage refusal, cache separation and selected-provider-only
worker credentials. Provider responses in tests are mocked; these checks do not
establish real account entitlements or certify historical data completeness.

Credential settings tests also cover encrypted files and permissions, persistence,
operator-only mutations, HTTPS enforcement, validation-error redaction, removal,
environment fallback and immediate worker injection. A separate real-browser check
saved dummy keys through the actual backend, reloaded the page to verify empty
inputs, and removed them. No real API keys or paid downloads were used.

### Historical ticker mappings

Alpaca requests use `asof=<request end date>` with `adjustment=raw`. This keeps
historical ticker mappings bounded to the requested period, including META's
previous FB symbol. Disabling mappings with `asof=-` omits that earlier history;
the completeness validator correctly rejects it. The mapping setting is recorded
in source provenance, and the provider identity is versioned
`raw-rth-minute-asof-end-v2` to avoid reusing earlier cache semantics. This is not
point-in-time universe certification or corporate-action price adjustment.
