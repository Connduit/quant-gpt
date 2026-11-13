# Phase 12C — saved ML predictions to strategy profitability

Implemented as an extension of the existing backtester, not a replacement. The
original Phase 12 campaign remains data-blocked; this phase does not waive its
100-stock/PIT/event/independent-confirmation requirements or qualify a strategy.

## Dashboard flow

1. Update/build/start the `work` branch dashboard.
2. Run ML on a physically date-bounded snapshot outside protected periods. For
   OHLC-only downloads select **Exploratory ML — prediction only** explicitly.
3. In **Equity workflow jobs**, open the completed training **View report**.
4. Use **Evaluate strategy profitability**. Choose the saved model, dates, initial
   capital, top N, score/probability threshold, rebalance/maximum holding periods,
   cash fraction and stock target weight. Expand risk limits/costs if needed.
5. Click **Evaluate strategy** using a researcher token. This queues a bounded,
   isolated worker; it does not refit the model or submit a broker order.
6. Open the resulting `profitability` job. Net results lead: equity/drawdown,
   benchmarks, costs, period performance, validation/data status and actual fills.
   Switch cost scenarios to update both metrics and curves. Prediction diagnostics
   remain secondary. Download the ZIP for every scenario's complete CSV logs.

Saved jobs containing protected 2019 inputs are rejected **before prediction and
price reads**, even if a smaller evaluation range is requested. Re-run a physically
separate permitted-date training job instead. Both job and input-manifest bounds,
source lineage, prediction/dataset hashes, per-fold model hashes, feature schemas,
fold clock evidence and first-eligible execution timestamps are checked.
Adjusted snapshots cannot serve as cash execution prices. Synthetic inputs are
engineering fixtures, not accepted as real profitability evidence.

## Executable rules

- Long only; one shared USD cash account, no borrowing or short sales.
- BUY increases a target, SELL reduces it, EXIT targets zero, HOLD leaves it
  unchanged. Signals use only available saved OOS scores and lagged features.
- Top-N selects highest scores after the raw return/probability threshold. Optional
  volatility adjustment ranks score divided by known volatility **after** applying
  a probability threshold; it never applies probability cutoffs to score/volatility.
- Position targets share the non-cash allocation, capped by the stock target
  weight. Existing portfolio risk sizing is reused; pre-fill checks use observed
  opening prices, available cash/fees and gross/position budget. Sells fund buys.
- Rebalance at the specified exchange-session interval. Exit after the configured
  holding interval; a symbol forced out for expiry cannot immediately re-enter in
  the same rebalance. Stop after a close breaches the daily-loss/drawdown limit,
  and exit at the next eligible open. Stops cannot guarantee gap-free losses.
- Weights/cash are entry/rebalance targets; marked-price drift may exceed targets
  between decisions. Whole-share orders are the default; fractional orders can
  be selected. Splits can create fractional entitlements; cash-in-lieu is unsupported.
- Market fills occur strictly after signal availability, at the first eligible
  opening. Final liquidation is scheduled before the predeclared last open and
  incurs the same commissions, spread, slippage and impact.
- SPY buy/hold and equal-weight references share capital, dates, cash reserve and
  execution costs, but have no per-stock cap/active drawdown stop. Their exposure
  is reported instead of claiming identical risk. Momentum ranks positive known
  momentum; mean reversion ranks negative known MA distance. Cash earns 0%.

## Costs and reporting

Baseline defaults: $0.005/share commission, 2 bps full spread (half per fill),
5 bps slippage and 1 bp fixed assumed impact. Low/high multiply **all** baseline
cost inputs by 0.5/2. Inputs can be changed in the dashboard; assumptions are not
claimed to be calibrated venue/liquidity estimates. Fees are included in cash/P&L,
not subtracted twice. A zero-cost replay is independent; different sizing/rejections
mean gross cannot be reconstructed by adding reported dollars to net returns.

CSV artifacts include trades, orders/rejections, BUY/SELL/HOLD/EXIT signals,
positions, corporate actions and equity; a verified prediction CSV pins the model
version behind each score. JSON contains net/gross metrics, monthly/yearly returns,
conditional regime means, exposure, turnover, costs, diagnostics and sensitivities.
Turnover is absolute executed notional / mean equity (two-way, not halved). Win
rate/profit factor/average P&L use sell fills, including partial exits, not independent
round trips. Undefined ratios are null. Regimes use ex-post SPY daily path direction
only for description; they do not influence signals.

## Data and statistical safeguards

Strict mode retains raw-price, complete-action and point-in-time membership gates.
Exploratory backtests require raw validated observations and an explicit incomplete
mode. Missing event evidence is represented as `complete: false`,
`coverage_method: unverified_events`, with UNKNOWN coverage limitations; it is not
an assertion that zero events occurred. Unknown-event ledgers require explicit
opt-in in the daily-data adapter. Large unexplained raw opening discontinuities
stop incomplete-evidence simulations rather than infer splits. Known splits,
reverse splits and dividends retain existing decimal accounting; no adjusted/raw
mixing or double application. Symbol-change/delisting-marked inputs without a
validated lifecycle adapter fail closed. Missing terminal payouts or membership
are never fabricated. Missing events can invalidate exploratory wealth/returns.

Discovery already simulated trades; Phase 12C adds an unconditional rejection of
nonpositive mean or compounded net validation return. Prediction skill remains diagnostic and
contributes zero to strategy ranking. Drawdowns, turnover, costs, baseline excess,
window consistency and cost sensitivity remain ranking/gating terms. Registry,
failed/rejected attempts, multiple-testing/statistical and holdout safeguards remain.
Nearby rebalance/holding settings are evaluated for stability, not optimized into
an automatic winner. All profitability attempts, including repeats, failures and
recoverable interruptions, are retained in a persistent server registry.

Bootstrap active-return intervals and deflated-Sharpe estimates are explicitly
conditional diagnostics. Full external search history/independent confirmation
are unknown, so no FDR-adjusted qualification is claimed. `qualified`,
`promotion_allowed` and `live_enabled` remain false. No final holdout is opened,
authorized or consumed; no paper/live promotion or broker transaction occurs.

## Demonstration and reproducibility

See `results.md`, `demo/simulation-report.json`, `demo/benchmark-comparison.csv`,
`demo/baseline-*` CSV logs and `demo/simulation-artifacts.zip`. These contain actual
simulated outputs from verified bounded provider observations, not invented returns.
They remain exploratory because action/universe certification is absent.
Raw vendor archives, models, source-job library and private registry are kept out
of Git. With permitted Alpaca SIP credentials, a fresh reproduction is:

```bash
uv run --env-file .env --frozen --all-extras python examples/phase12c_profitability.py --root work/phase12c-demo
```

The script requests only 2016-01-01–2018-12-31 SIP **daily raw** bars, validates
observations, fits bounded chronological Ridge predictions and replays the same
strategy/baselines/costs. It refuses to overwrite an existing root. It does not
request protected 2019 prices. Numerical reproducibility also depends on pinned
code/dependencies and immutable provider response versions; fresh vendor revisions
are different inputs, not evidence of exact reproduction.
