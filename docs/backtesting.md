# Milestone 2: daily event-driven backtesting

## Run the end-to-end demonstration

From the repository root:

```bash
uv sync --frozen --extra dev
uv run python examples/backtest_demo.py
```

In this cloud environment, first set `export UV_CACHE_DIR=/workspace/.cache/uv`.
The demo loads the existing synthetic SYNTH fixture through Milestone 1 ingestion,
validates and verifies its immutable snapshot, then runs momentum, mean reversion
and buy-and-hold. Every strategy produces fills. All results are **hypothetical
and synthetic**, not market performance or evidence of a profitable strategy.
No network, subscription, broker or ML training is used.

Results go to `data/backtests/milestone-2-demo/{momentum,mean-reversion,buy-and-hold}`.
Use `--output data/backtests/another-run` for a new run; existing directories are
never overwritten. Use `--data-dir` to change snapshot storage. The demo publishes
all three reports together after successful execution.

To run a single strategy, first download SYNTH as documented in the README and
substitute its returned identifier below:

```bash
uv run quantlab --config configs/data.toml backtest SNAPSHOT_ID \
  --strategy momentum --lookback 2 --shares 10 --initial-cash 10000 \
  --commission-per-share 0.005 --commission-fixed 0 \
  --minimum-commission 0 --slippage-bps 1 --spread-bps 2 \
  --output data/backtests/my-momentum-run
```

`--strategy mean-reversion --lookback 2 --threshold 0.001` uses a 0.1% entry
threshold for the small fixture. Strategy thresholds are fractions, not basis
points. Defaults are 20-session lookbacks, momentum threshold 0, mean-reversion
threshold 0.02, 10 shares, $100,000 initial cash, $0.005/share commission,
zero fixed/minimum commission, 1 bp slippage and zero spread.

## Event and information contract

Replay uses a priority queue ordered by UTC event time and a deterministic
same-time order: split, dividend entitlement, dividend payment, open, close,
bar availability. Session times come from XNYS, including DST and early closes.

- The reporting ledger marks positions at each actual session close.
- Strategies see a bar only at `available_at`, on or after that close. With the
  original provider policy this is midnight New York on the following calendar day.
- A target creates a market order at the callback time. It can fill only at an
  opening print **strictly later** than submission. A late bar misses an already
  elapsed open and waits for the next eligible session. Same-open signals cannot
  retroactively execute at that open.
- Strategy account views use observable prices (opening prints or published
  closes), not the reporting ledger's unavailable daily close. History and account
  views are immutable, and execution policies receive no daily high/low/close.
- Callbacks after the final simulated close are not run. Outstanding orders at
  that close expire; positions remain marked, with no invented liquidation.
- Only one target per symbol per callback is allowed. A new target cancels an
  outstanding target order before computing the new delta against actual holdings.

Momentum enters when the close/lookback-close return exceeds its threshold and
exits otherwise. It requires lookback+1 available closes. Mean reversion enters
below the trailing mean by its threshold and exits at/above the mean; its window
includes the current available close. Both hold existing share quantities between
entry/exit signals rather than silently rebalancing after splits. Buy-and-hold
submits once on the first available bar and retains any resulting position.

This prevents simulator look-ahead through its normal interfaces; it does not
certify source data as point-in-time or sandbox arbitrary Python code.

## Execution and accounting

The initial account supports one USD equity/ETF per run, long-only, cash-funded,
with fractional quantities allowed. Orders fill fully or are rejected. Insufficient
cash includes all commissions; unpaid dividend receivables cannot fund buys.
Gaps can make a previously affordable target unaffordable. There is no automatic
quantity clipping, retry, leverage or borrowing.

Fill price = opening price plus adverse slippage and half the full spread for
buys, minus both for sells. Commission per fill is the larger of the minimum
commission and fixed commission plus per-share commission. Total impact must be
below 100%. High/low/volume are never used to infer opening liquidity, constrain
fills or make the execution model appear realistic using future information.

Money and quantities use Decimal arithmetic at a fixed 34-digit precision in the
replay. Entry commission is included in average cost. Partial sales allocate that
basis proportionally; realized P&L subtracts exit commission. Monetary outputs
serialize as decimal strings and are not rounded to broker settlement cents.
The input Milestone 1 OHLC schema remains float64; prices enter accounting through
their decimal string representation.

At every valuation the engine checks:

```text
equity = cash + marked positions + dividend receivables
       = initial cash + realized P&L + unrealized P&L + dividend income
```

Hand-calculated test (initial cash $10,000, $1/order + $0.10/share commission):

| Event | Cash | Remaining shares | Average cost | Realized P&L |
| --- | ---: | ---: | ---: | ---: |
| Buy 10 at $110, fee $2 | 8,898.00 | 10 | 110.20 | 0 |
| Sell 4 at $120, fee $1.40 | 9,376.60 | 6 | 110.20 | 37.80 |
| Sell 6 at $130, fee $1.60 | 10,155.00 | 0 | 0 | 155.00 |

After the first buy, a $115 close gives equity $10,048 and unrealized P&L $48.
After the partial sale, a $120 close gives equity $10,096.60, realized P&L $37.80
and unrealized P&L $58.80. Tests assert these exact values, not just approximate
end returns.

## Corporate actions and real-data inputs

The built-in synthetic fixture assumes no actions. Real inputs must explicitly
be unadjusted and must have a complete sourced action ledger covering the entire
requested date range. Adjusted or unknown-adjustment inputs are rejected to avoid
executing synthetic prices or double-counting corporate actions. In particular,
Stooq snapshots remain readable but are not accepted as execution prices.

Import an actual raw OHLCV file using the same Date/Open/High/Low/Close/Volume CSV
schema and validation as Milestone 1:

```bash
uv run quantlab --config configs/data.toml import-csv AAPL \
  --csv /path/to/unadjusted-bars.csv --source 'vendor and dataset revision' \
  --price-basis unadjusted --start 2024-01-02 --end 2024-12-31
uv run quantlab --config configs/data.toml backtest RETURNED_SNAPSHOT_ID \
  --actions /path/to/complete-actions.json --strategy momentum \
  --output data/backtests/raw-data-run
```

Import always reads the file into a new snapshot, so a cached same-date request
cannot conceal a local file revision. `--price-basis adjusted` permits storage and
inspection, but backtesting rejects it. Labels and completeness are caller
assertions, not independent vendor certification; do not relabel adjusted data
as raw merely to pass validation.

Ledger shape below uses **invented actions for illustration**, not the built-in
fixture's action history. Supply matching real records for actual imported prices:

```json
{
  "symbol": "SYNTH",
  "coverage_start": "2024-01-02",
  "coverage_end": "2024-01-08",
  "source": "explicitly synthetic schema example",
  "complete": true,
  "splits": [{"date": "2024-01-04", "ratio": "2"}],
  "dividends": [{"ex_date": "2024-01-05", "pay_date": "2024-01-08", "amount": "0.25"}]
}
```

Split ratios mean new shares per old share. Before the effective session's open,
a split scales holdings and pending quantities and inversely scales average cost.
Available historical **prices** are rebased only when that split becomes effective;
volume remains original traded shares. No future split enters earlier signals.
Forward and reverse splits preserve portfolio value when raw prices change
proportionately. Fractional residuals are retained; cash-in-lieu is not modeled.

Ordinary cash dividends accrue a receivable for shares held immediately before the
ex-date open, after any same-day split. Ex-date buys do not earn the dividend;
ex-date sells retain it. Per-share amounts are in post-split share units when
split and dividend share an effective date. Cash is credited at pay-date midnight
New York, or after entitlement if ex and pay date are the same. A receivable due
after simulation end remains in final equity without becoming spendable cash.
No strategy is given the future action ledger.

## Reports and metric definitions

Each output directory contains `trades.csv`, `equity.csv`, `orders.csv`,
`signals.csv`, `corporate_actions.csv`, `benchmark_equity.csv`,
`benchmark_trades.csv`, `benchmark_orders.json` and `report.json`.
The equity file includes position/cash history, daily returns, drawdowns, exposure,
realized/unrealized P&L, dividend income/receivables and cumulative cost breakdown.
Trades are executed fills, including partial position exits, not inferred
round-trip trade groupings. Orders retain original and split-adjusted quantities,
final status, resolution time and rejection/expiry reason.

The JSON report records strategy parameters, initial capital, costs, the complete
action ledger, source snapshot manifest, package source hash, software/Python and
dependency versions, output checksums and a deterministic run ID. Repeating the
same immutable input and parameters produces the same report identity. Custom
strategies should be configured dataclasses; otherwise uncaptured custom state
is explicitly flagged. CSV/JSON artifacts can be consumed by a later dashboard
without sharing mutable replay state.

- Total return uses final marked equity versus initial capital.
- Annualized return compounds over observed sessions at 252 sessions/year.
- Sharpe uses arithmetic daily excess returns with zero risk-free rate and sample
  standard deviation. Annualized volatility also uses sample standard deviation.
- Sortino uses all-session mean squared negative returns as downside deviation.
- Maximum drawdown is the most negative equity/previous-peak minus one, including
  initial capital as the first peak. Zero terminal equity is a -100% total return;
  subsequent zero-equity sessions have zero incremental return.
- Gross turnover is total absolute filled notional divided by average close equity.
- Exposure and time-in-market use session-close observations.
- Win rate, average exit P&L and profit factor use realized P&L per sell fill,
  including allocated commissions, excluding separately recorded dividend income.
- Undefined ratios are null, not NaN/infinity. Extreme overflowing annualization
  is also null. Cash, commissions and monetary P&L remain decimal strings.

The benchmark is same-symbol buy-and-hold using the same initial cash, costs,
calendar, availability and action ledger. The CLI gives it the same fixed entry
share quantity as the selected strategy; residual cash remains idle. It is **not**
a fully invested index return. Excess return is the arithmetic difference in total
returns, not alpha or statistical significance. No-fill strategies/benchmarks and
rejected orders are reported rather than treated as successful investment runs.

## Verification and limitations

Run `uv run --frozen pytest -q` and `uv run --frozen ruff check src tests examples`.
Tests cover exact accounting, split/reverse split handling, pending orders,
dividend entitlements/payments, receivable funding restrictions, gaps, costs,
zero equity, late availability, same-open rejection, future-price mutation,
immutable contexts, all baseline exports, raw CSV import and the demo subprocess.

This is daily, one-instrument cash-equity simulation. It does not implement limit
orders, partial market fills, queue priority, latency, liquidity/market impact,
shorting, margin, taxes, interest, FX, tick/settlement rounding, cash-in-lieu,
mergers, spin-offs, delistings, special due-bill dividend rules, multiple assets,
futures or live brokers. Avoid unsupported corporate-action windows. Strategy
history is in memory. Availability, historical universe membership and vendor
revisions are not independently certified point-in-time. These limits are not
removed by passing accounting tests or by a positive hypothetical return.

Milestone 3 is not started; review this milestone before requesting it.
