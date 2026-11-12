# Futures implementation audit

The [full request](milestone-7-instructions.md) is preserved. Actual contracts,
contract multipliers, quarter-point ticks, UTC bars, Chicago sessions, margin
checks, signed whole-contract accounting, variation settlement, roll decisions,
causal features, purged rolling/expanding validation, bounded discovery and
holdout protection extend the existing engine rather than replace it.

ES/MES/NQ/MNQ engineering is covered by tests. Actual downloaded coverage is
ESZ13 only. Pinned LEAN `Data/market-hours/market-hours-database.json` declares
UTC data timestamps for Future-cme-ES; archive prices are actual contract prices,
not equity-scaled or back-adjusted. The manifest records all source payload hashes.
Calendar tests cover DST, maintenance and supplied exceptions; this five-day RTH
sample does not certify all historical ETH halts, holidays or expiry exceptions.
Continuous adjusted charts are explicitly nontradable and unsuitable for causal
features. No actual roll occurs in the short real demonstration.

Initial/maintenance margins $12,000/$10,000 are research assumptions, not verified
2013 CME or broker rates. Official daily settlements require a dated external
source; the demonstration explicitly uses a last-observation proxy. Fees and
slippage are assumptions. Quotes do not guarantee execution. Open interest is
used only after its observation timestamp. No certified historical margin history,
long independent OOS record, or complete instrument-wide data was obtained.

The optional official Databento SDK adapter checks credentials and an explicit
cost budget. No key is configured; no paid request or external live streaming was
attempted. Tests use injected clients. Stooq remains subject to the separate
[older-runtime allowlist blocker](stooq-reverification.md); this futures source
works through the inherited proxy without TLS changes or network workarounds.

Shared equity split validation retains its default keys; futures uses explicit
contract/time observation keys. Shared portfolio limit comparisons are reused.
Same-clock closes stage new signals until older opening orders are processed;
repeated targets cannot starve pending orders. Risk liquidation occurs at a later
eligible opening, and account insolvency retains debt rather than fabricating cash.

Archive data remain under vendor licensing terms; no raw vendor data is committed.
The reserved future period was registered SEALED but never fetched or evaluated.
No paper/live permission, strategy promotion or profitability claim results.
