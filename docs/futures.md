# Futures research, contracts and intraday ML

Milestone 7 adds a separate futures accounting/execution adapter. The original
cash-equity engine and portfolio interfaces remain intact. See the
[full request](milestone-7-instructions.md), [audit](futures-audit.md) and
[actual results](milestone-7-results.md).

## Products, contracts and sources

| Product | Multiplier (USD/point) | Minimum tick | Tick value |
| --- | ---: | ---: | ---: |
| ES | 50 | 0.25 | 12.50 |
| MES | 5 | 0.25 | 1.25 |
| NQ | 20 | 0.25 | 5.00 |
| MNQ | 2 | 0.25 | 0.50 |

These standard CME specifications are represented by product definitions and
cross-checked against the pinned LEAN symbol-properties database. Reference
[CME equity-index product specifications](https://www.cmegroup.com/markets/equities.html).
Each individually expiring contract separately records month/year, exchange,
currency, last-trade/expiration timestamps, metadata source and provider symbols.
Margin is **not** a permanent product constant: dated initial/maintenance values
and a source/assumption are required before execution. The real demo's $12,000 /
$10,000 ES margin values are explicit research assumptions, not certified 2013
exchange/broker requirements. Modern broker rates cannot silently price the past.

`LeanFuturesProvider` downloads pinned actual-contract trade, quote and open-interest
ZIP members through ordinary verified HTTPS. The pinned market-hours database
declares ES data timestamps **UTC**; exchange-local Chicago time is kept separately.
Prices use the futures CSV format directly, unlike equity deci-cent scaling.
Source URLs and checksums are preserved. The bounded archive is AlgoSeek-derived,
not a comprehensive present-day feed; public availability is not a commercial
redistribution license. Raw files remain ignored under `data/`.

`DatabentoProvider` implements GLBX.MDP3 raw-symbol one-minute history via the
installed SDK. It requires `DATABENTO_API_KEY`, a suitable licensed account and
HTTPS permission for `hist.databento.com`. It quotes estimated cost before data
retrieval; default quoted-cost cap zero blocks paid downloads. Provider-side
account limits remain appropriate because an estimate is not a contractual
billing guarantee. Actual pricing/subscriptions were not verified without
credentials. No paid request was made. Offline tests inject a client and verify
cost rejection, schema and provider symbol mapping. SDK float-price/UTC-index
conversion signatures were checked. Never silently substitute fixtures or a
continuous symbol for an individual contract.

## Validation, sessions and immutable storage

`FuturesStore` creates content-addressed immutable Parquet/CSV/manifest snapshots.
Every read verifies manifest and artifact hashes. DuckDB reuses the existing
SELECT-only, external-access-disabled query boundary. Metadata distinguishes
actual contract prices, synthetic fixtures and nontradable research series.
Validation checks contract mapping, UTC-aware timestamps, minute alignment,
positive tick-aligned OHLC, volume, quote consistency, expiry and missing minutes.
Entire missing sessions are detected. Partial requested intervals and explicitly
sparse histories are labeled; statistical research requires complete configured
contract sessions. Missing data is never turned into fabricated flat bars.

`FuturesCalendar` uses CMES exchange-calendar sessions, Chicago-local definitions,
UTC storage, maintenance breaks, DST and explicit dated holiday/early-close
exceptions. The initial real demonstration selects the declared **08:30–15:00 CT
cash-index research window**, not all Globex hours. ETH supports overnight labels
and configurable maintenance/holiday exceptions. Historical changes to index
futures halts and exchange exceptions require authoritative dated overrides;
the default modern calendar is not certified for every historical ETH date.
The five demonstrated ordinary RTH sessions passed all 390-minute checks.

## Rolling and continuous representations

Calendar roll lead time is an explicit count of calendar days before last trade.
Volume selection uses only published volume through the decision timestamp in
the latest observed session. Contract chains advance forward and do not bounce
back to an older expiry after rolling. Both actual leg prices must be available
for a chart roll gap. No future completed-session volume selects today's contract.

A selected-contract continuous series is a **research representation**. Back
adjustment adds known roll gaps to earlier chart levels ex post and is explicitly
`tradable: false`, `feature_safe: false`. Execution rejects these representations.
Backtests use actual expiring contracts and explicit old-leg/new-leg targets;
price differences between expiries are not manufactured trading profits.
Actual roll fees/impact are reported. Real-sample dates contain no roll; transitions
and raw-price P&L are tested with explicitly synthetic contract scenarios.

## Accounting and execution

Futures cash does not pay the full contract notional. The ledger tracks signed
whole-contract quantities, entry price, settlement basis, fees, lifetime trade P&L,
unrealized P&L, initial/maintenance margin and buying power. Gross trade P&L is
`(exit-entry) * multiplier * contracts * direction`. Settlement transfers variation
to cash and resets settlement basis, without realizing the same lifetime profit
twice. Sourced official prices require an explicit publication timestamp;
otherwise a declared last-observed-session-close proxy may be selected. The
proxy is **not official CME settlement**. Final views reconcile to initial capital
plus lifetime realized/unrealized P&L less fees.

Orders must exist strictly before the execution opening. At a simultaneous
bar-close/open clock, new close signals are staged until older opening orders
are resolved. Identical targets retain their pending identity, so repeated signals
cannot starve execution. New same-clock signals cannot cancel an already eligible
opening order. Quotes use actual bid/ask **open** fields when supplied, plus
configured adverse tick slippage; future high/low/close fields do not determine
that fill. Quote/trade bar opens are minute-level reference models, not guaranteed
microsecond fills. When quotes are absent, declared adverse spread/slippage tick
assumptions apply, rounded conservatively to a valid tick.

Fees separate commission, exchange and regulatory assumptions. Prior published
volume limits participation; displayed quotes do not guarantee fills. Risk
checks run at admission and again at the actual opening, bounding contracts per
product, notional, leverage, margin utilization and loss/drawdown. Portfolio sizing
and generic limit checks are reused from Milestone 6. Reductions can close risk
while increases are suspended. Maintenance breaches queue liquidation for the
**next eligible quote/open**, so gaps can exceed intended loss limits. Insolvency
records debt and undefined ratios rather than inventing a zero-loss reset.

Expiry and session-flat actions use public scheduled deadlines and actual quotes;
no missing exit price is fabricated. `hold`, `flat_rth` and `flat_session` policies
make overnight behavior explicit. Unresolved orders/positions at end of data are
reported. The futures adapter is research-only; no live execution command exists.

## Features, labels and model evaluation

Minute features include 1/5/15-minute returns, intraday momentum, observed session
open distance, frozen opening ranges, previous observed session high/low/return,
rolling ranges, ATR, realized volatility, expansion/contraction, volatility regime,
relative volume, spikes/acceleration, bar-price VWAP proxy/deviation,
volume-weighted momentum, time of day, session type, overnight movement so far
and market trend. ES/NQ relative strength is available with synchronized data;
parallel contracts use a deterministic observed-volume reference. A bar-derived
VWAP proxy is not full trade-level VWAP. Rolling windows reset at session/gap
boundaries; completed previous-session context persists only after it is observed.
Opening-range statistics remain unavailable until the range is complete.

Labels enter at the next **strictly later** opening and exit 5/15/60 actual minutes
later. Labels cannot cross missing-minute gaps, sessions, contract identity or
holdout boundaries. Start/end/known-at timestamps are explicit. Direction,
volatility-adjusted return and breakout-continuation labels are supported. Shared
information-interval validation and global cross-contract purging protect splits;
embargo/gap counts use the observed canonical minute grid. Rolling/expanding
training and inner validation precede each evaluation session. Source caches and
workers physically exclude the reserved final period.

Ridge/logistic regression, Random Forest, LightGBM and XGBoost reuse the existing
seeded CPU model/preprocessing API. Only whitelisted causal feature names reach
training. Forecasts record model availability and maximum training-label time.
Decision cadences of 1/5/15 minutes subsample canonical one-minute features; they
do not relabel a five-minute bar as a one-minute observation. Predictive metrics
are descriptive; temporal within-session rank correlation is not cross-sectional
IC or independent significance. Profitability is evaluated through actual
contract replay after fees, margin and execution assumptions.

Baseline hypotheses are VWAP mean reversion, opening-range breakout, momentum,
regime-aware switching and a session buy-and-hold control. Entry, close-triggered
stop/take-profit, holding time, regime and sizing rules are bounded configurable
hypotheses, not assumed profitable strategies. Stops trigger later execution and
cannot guarantee a maximum loss.

## Discovery and uncertainty

The shared resource-limited experiment supervisor dispatches futures definitions
through a fixed evaluator, not arbitrary generated code. Registry, Optuna and
local MLflow retain trials, controls, failures, duplicate claims and lineage.
Indexed seeded random proposals, conditional model spaces, CPU/memory/wall budgets,
controller locking, pruning boundaries and explicit resume policies remain in force.
Every conventional control is separately recorded. Historical searches in retained
futures registries are counted for multiplicity; none become fresh independent
evidence because a new output directory was chosen.

The real sample supplies only **two OOS daily observations**. Daily PSR/DSR are
unavailable, one-sided p-values stay conservative at one, and BY-adjusted values
stay one. Conditional within-session minute block-bootstrap intervals are reported
as engineering diagnostics, not independent-day proof. Net returns and benchmark
comparisons do not authorize paper/live deployment. The shortlist can be empty.

## Commands

```bash
uv sync --frozen --all-extras
uv run --frozen --all-extras python examples/futures_demo.py --output data/futures/NEW_RUN
uv run --frozen --all-extras quantlab futures specifications
uv run --frozen --all-extras quantlab futures research --research-config configs/futures-research.example.yaml --output data/futures/ANOTHER_RUN
uv run --frozen --all-extras quantlab futures validation-report --root data/futures/NEW_RUN
```

`examples/futures_demo.py --synthetic` explicitly opts into invented fixtures and
labels all results synthetic; there is no automatic fallback. The real default
reuses verified retained archives or downloads ESZ13 for October 7–11, 2013,
generates a populated YAML with actual IDs, and preserves prior output directories.
`train`/`discover` run the same full bounded research pipeline; `resume` requires
unchanged code/data/configuration and retains optimizer/attempt history.

`futures import --provider lean --include-auxiliary --contracts
configs/futures-contracts.example.yaml --contract ESZ13 --store DIRECTORY
--start 2013-10-07T13:30:00+00:00 --end 2013-10-11T20:00:00+00:00` ingests history.
`--provider databento --maximum-download-cost N` explicitly opts into that SDK
and quote cap. CSV import additionally requires `--csv`, `--source` and the
explicit `--raw-contract-prices` declaration. Use `--synthetic` for invented CSVs.

`inspect`, `query` and `validate-history` accept `--store DIRECTORY SNAPSHOT_ID`;
query additionally requires `--sql`. `continuous` accepts `--store`, `--snapshots`,
`--output`, optional calendar/volume roll criteria and `--back-adjust`, and writes
nontradable chart artifacts. `backtest` accepts snapshots, a baseline `--family`,
`--holdout-start` and a new output directory; it labels that full permitted-range
run as research rather than automatically calling it independent OOS evidence.

The populated [research](../configs/futures-research.example.yaml) and
[contract](../configs/futures-contracts.example.yaml) configurations record the
current dataset. Model loading is for trusted local artifacts only. Source and
wheel builds preserve CPU compatibility. Optional live archive tests use
`QUANTLAB_LIVE_FUTURES=1`; no paid/live feed is needed for the core suite.
