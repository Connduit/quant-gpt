# Phase 12A continuation — 12 November 2026

Status: **BLOCKED_DATA**. Updated Stooq policy is applied, but automated CSV access
has not succeeded. No new historical price snapshot, model fit, strategy evaluation,
candidate, promotion, holdout authorization, or broker operation was created.

## Repository and environment evidence

The selected executor is
`ccarenv_b64_Y2NhcmVudl9hN2ZkY2I3YjIzNDA4MTkxODJmNjliZTliMWM1YTYzOA`.
The initial local checkout was `b4b85ae` with only README. A read-only remote ref
inspection located completed work on remote `work`; fetching and fast-forwarding
restored `f8d2717b886cc037943da8ac05188c25c5526a6d`. No remote writes were made.

Environment status reports current observations, enforced restricted policy and
custom allowed host `stooq.com`; startup policy also includes it. Both desired and
observed local revision numbers remain `1`. A higher revision number is therefore
not the evidence of the update: the applied allowlist is. See
`phase12a-environment.json` for selected configuration-version identity.

Fresh requests retained inherited proxies and TLS verification. No proxy bypass,
certificate disabling, browser challenge automation, or paid API use occurred.

| Probe | Actual outcome | Interpretation |
| --- | --- | --- |
| Direct curl HTTPS, AAPL 2018-01-02–2018-01-10 | HTTP 200, HTML JavaScript browser-verification page | HTTPS transport works; CSV unavailable |
| Independent direct Python/httpx, identical URL | HTTP 404, Stooq-branded missing-page HTML | HTTP response received; CSV unavailable |
| Actual `StooqProvider.fetch`, same dates | `ProviderHTTPError`, HTTP 404 | Application data connectivity fails |

These responses do not establish the root cause of the differing curl/httpx
behavior, or prove the service globally unavailable. They do establish that the
earlier allowlist denial is no longer the only issue. An HTTP 200 alone must not
be classified as a successful provider test. Raw direct evidence remains ignored
under `work/phase12a/` and `data/phase12a/evidence/`; its hash and response
classification are in `phase12a-connectivity.json`.

## Coverage and reproducible acquisition

The tracked previous audit reports seven stocks plus SPY, 1,195 sessions each,
2014-04-03–2018-12-31, four stock sectors, incomplete reconstructed actions and
no certified PIT membership. That is historical evidence only. This task has
neither its ignored `data_quality.json`/snapshots nor its equity/futures canonical
holdout ledgers. Their absence was checked by path existence without opening any
protected archive. The previous audit cannot be reproduced from this checkout.
Restore the original artifacts and history; do not initialize substitute ledgers
that would erase holdout/search state.

New validated equity rows: **0**. New research snapshot IDs: **none**. HTML was
rejected rather than saved as market data. No fabricated prices or synthetic
replacement experiment was used.

`examples/phase12a_connectivity.py` reproduces the direct and actual-provider probes,
records response provenance, and permits diagnostic AAPL/IBM/SPY acquisition over
2008-01-02–2018-12-31 only if the provider probe succeeds. It uses the existing
validator and immutable snapshot store with manifest/hash, Parquet equality and
DuckDB count read-back. Those three-name snapshots, if obtained on a future run,
would still be research-ineligible: unknown adjustments and missing event/universe
products cannot pass the frozen campaign. No model dispatch is implemented in
this acquisition script. End bounds after 2018-12-31 are explicitly rejected.

Reproduce from repository root:

```bash
UV_CACHE_DIR="$PWD/work/uv-cache" uv sync --frozen --extra dev
.venv/bin/python examples/phase12a_connectivity.py
.venv/bin/pytest -q tests/test_phase12a.py tests/test_providers.py tests/test_validation.py tests/test_storage.py
```

Exit 2 is the expected data-gated result. Integrity/validation errors propagate as
errors rather than being relabeled successful downloads. Network evidence is
time-specific; repeat runs may receive different response bytes/statuses.

## Provider comparison

Documentation was inspected on 2026-11-12. No licensed Norgate, CRSP, Sharadar or
full QuantConnect export was available or empirically certified in this task.
Documentation-supported capabilities below are procurement candidates, not passed
acceptance tests.

| Solution | Evidence and potential use | Remaining platform gaps |
| --- | --- | --- |
| Stooq | Existing adapter; HTTPS now responds | Automated CSV failed; adjustment basis unspecified; no event or PIT bundle verified. Diagnostic price source only |
| Retained LEAN sample | Previous audit documents internally checked raw bars | Local artifacts absent; tiny retrospective universe, proxy actions and incomplete maps. Engineering/development evidence only |
| Full QuantConnect equities plus Security Master | Official docs describe map/factor files and splits, dividends, delistings and symbol-change events | Full purchased exports, pay dates, economic terminal payouts, universe membership and independent reconciliation remain unverified |
| Norgate Platinum/Diamond | Documented delisted prices, stable assetid and daily membership series; Windows exporter feasible | Cannot alone meet required identifier/event/terminal-return contract; actual export not available |
| Sharadar prices/actions/metadata/constituents | Official actions schema includes ticker changes, dividends, splits and counterparties; history from 1998 | No explicit pay-date field in inspected actions schema; final recovery values, identifier validity intervals, membership completeness and vintage semantics need export tests |
| CRSP US Stock + explicitly licensed universe data | Documented permanent IDs, active/inactive securities, distributions and delisting data; Linux delivery supported | Strongest documented research backbone; obtain licensed extracts, inspect missing/sentinel values, verify raw execution OHLC and acquire exact desired universe membership separately |

Primary sources: [QuantConnect Security Master](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-security-master),
[Sharadar actions schema](https://sharadar.com/docs/actions),
[Sharadar stock schema](https://sharadar.com/docs/stocks),
[CRSP product and delivery](https://www.crsp.org/research/crsp-us-stock-databases-2025-layout/),
[CRSP file layouts](https://www.crsp.org/wp-content/uploads/2023/10/crsp_us_stock.pdf).

### Norgate requirement verdict

The [vendor FAQ](https://norgatedata.com/data-package-faq.php) explicitly excludes
prior tickers/names, historical classifications, detailed merger consideration,
delisting returns and post-delisting events. Its permanent assetid is useful but
does not replace historical external identifiers. Daily effective membership is
documented; announcement dates and temporary inclusions are absent. Corrections
have no vendor version history. Thus Norgate alone **fails** the platform contract.

The [content tables](https://norgatedata.com/data-content-tables.php) include
delisted securities with Platinum/Diamond, but exclude OTC-only delisted common
stocks and several other security types. Earlier coverage is not universally
complete. The old published delisted count is not a current export count.

The [Python documentation](https://pypi.org/project/norgatedata/) requires running
Windows NDU and an active subscription. It exposes explicit price adjustments,
assetid lookup, membership and capital-event indicators. A binary event flag is
not a split-ratio/consideration ledger. Dividend amounts depend on adjustment
mode and use entitlement-day dating; that is not payment-date evidence. Current
documentation differs on major-exchange indicator inception (FAQ 1990 versus
Python 2000); resolve with an actual bounded export before use.

### Proposed Windows-to-Linux workflow

This is an implementation contract, not a tested export or a claim of license
permission. Confirm private cloud storage/export rights before operating it.

1. On a dedicated licensed Windows account, run NDU to completion, then prevent
   updates during the bounded export. Record NDU/package versions, update time,
   subscription coverage, export start/end and source revision where available.
2. Enumerate current **and delisted** databases by assetid, retaining security type,
   first/last quoted date and export failures. Do not select today's constituents.
3. Export explicitly bounded pre-holdout raw OHLCV with adjustment NONE and padding
   NONE. Also export separately named adjusted comparison series and available
   dividends, capital-event flags, membership and major-exchange indicators.
   Supply an explicit end date to every call; defaults may include protected data.
4. Store typed Parquet/CSV, UTC retrieval timestamps, all parameters, counts,
   per-file SHA-256 and a canonical bundle manifest. Treat missing/unsupported
   fields as missing, never as no-event or nonmembership. Export failure must
   prevent publishing the bundle. Archive immutable versions to capture revisions.
5. Transfer only the bounded bundle to Linux under permitted license terms.
   Verify hashes and date bounds before opening payloads. Join on assetid plus
   independently verified effective-dated mappings, never current ticker alone.
6. Independently reconcile membership transitions, splits, ordinary/special
   dividends, spin-offs, mergers, bankruptcies and terminal payouts. Norgate's
   unavailable fields require another licensed source. Never liquidate at the
   final bar merely because hindsight reveals it was the last tradable date.

## Recommendation and acceptance gates

Prefer a licensed **CRSP research backbone plus separately verified target-universe
membership and execution-price coverage**, subject to sample-export acceptance.
This recommendation follows documented field fit, not an assertion of complete
data. CRSP missing delisting-return codes must remain missing, not become zero.
Do not mechanically add delisting returns to a return field that already includes
them; pin the exact file format and methodology first.

Norgate can be a useful Windows-ingested secondary price/membership check, or a
lower-cost component supplemented by verified security-master and action data.
It is not a complete substitute under the existing requirements. Sharadar and
QuantConnect deserve bounded sample-export evaluation before any subscription
choice; APIs and adjustment factors alone do not establish ledger completeness.

Before fitting, require a report of per-security coverage and listing intervals,
at least 100 stocks/eight sectors/2,000 sessions per frozen protocol, delisted
names and terminal outcomes, effective-dated identifier and membership tables,
explicit missing-data policy, complete actions including pay dates and independent
event checks. Calendar checks must respect real listing/suspension intervals;
do not forward-fill missing prices. Record publication/knowledge timestamps
separately from effective dates. As-revised history is not an as-known vintage.

Restore canonical ledgers/search history and freeze an independent confirmation
plan outside reused validation and reserved holdout. Implement and test a
prefix-only research adapter that never opens protected payloads. Keep dated
cost/liquidity assumptions and all attempted fits in the original trial family.
No requirements were relaxed to make a small ML experiment run.

## Research result and verification

**No eligible real-data ML experiment was run.** Fits/trials/candidates are zero;
returns, Sharpe, confidence intervals and p-values are unavailable. The conditional
data-readiness prerequisite was not met. Equity 2019 and reserved futures data
were not requested or opened. Canonical ledgers are missing here, so their current
SEALED state cannot be independently attested. Live trading remained disabled;
no broker/execution entry point was invoked.

Focused validation: **39 passed**, 36 dependency deprecation warnings. Ruff passed
for the new acquisition script and tests. Tests include rejecting protected bounds
and proving that an HTTP 200 verification page creates no snapshot through the
actual provider. Full ML/frontend/broker suites were not rerun; no engine code
changed. Remaining blockers are automated Stooq access, missing retained artifacts,
licensed complete exports, independent reconciliation and the research adapter/
confirmation prerequisites above.
