# Stooq allowlist recheck before Milestone 6

After the user's allowlist update, fresh Python `httpx.Client` requests to
`https://stooq.com` and its actual SPY CSV endpoint both still failed with
**`ProxyError: 403 Forbidden`**. The actual `StooqProvider.fetch` produced
`ProviderNetworkError: Stooq network request failed (ProxyError); check proxy
allowlist, connectivity and CA trust`, caused by that same `403 Forbidden`.
See [exact sanitized evidence](stooq-reverification.json).

This task still reports enforced runtime policy revision **1**, current
observations, no custom allowed hosts, and no `stooq.com` in effective hosts.
It is running the older attached configuration. The saved draft contains
`stooq.com`, but draft editing alone did not apply it to this instance.
No current-instance policy-change tool is offered. The administrator/user must
apply/save the updated policy to the current instance or start a fresh task from
the updated published configuration. Then test again with a fresh Python client.
TLS verification and inherited proxy/CA settings were preserved throughout.

Since Stooq is denied before origin TLS/HTTP, no six-symbol Stooq download or
price-adjustment/corporate-action verification can be claimed. No repeated
blocked symbol requests, fabricated observations, or validation relaxation was
used. Stooq's adapter continues declaring adjustment semantics unspecified;
OHLCV alone supplies no corporate-action ledger. Those prices are rejected by
the backtest adapter until raw semantics and sourced actions are established.

The existing verified alternative is the pinned LEAN archive: freshly downloaded,
normalized, Parquet-stored SPY and seven US stocks, 2014–2018, with DuckDB reads,
feature construction, ML/discovery workers and real statistical validation.
All four M5 candidates and eight robustness scenarios were rejected. The
[network/data report](market-data-verification.md), [snapshot IDs](market-data-verification-datasets.json),
[independent action-reference check](market-data-action-crosscheck.json) and
[M5 results](milestone-5-results.md) document coverage and limitations. Eight
independently inferred Apple distribution dates match the proxy in the limited
reference period; that does not certify complete events or payment dates.

Milestone 6 therefore uses those pre-holdout snapshots for explicitly research-only
portfolio mechanics. No Stooq research experiment, certified corporate-action
claim, strategy promotion or 2019 holdout evaluation is asserted. The requested
Stooq-specific verification remains blocked; the working alternative remains
verified. A future comprehensive provider needs contractual raw OHLCV semantics,
authoritative split/dividend/payment and other-event records, historical membership,
coverage and usage rights. No paid credentials are required for the bounded
archival fallback; it is not a comprehensive ongoing market-data service.
