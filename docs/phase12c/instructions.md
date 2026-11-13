# Quant Research Lab — Phase 12C: ML-to-Strategy Integration & Profitability Evaluation

## Primary Objective

Transition Quant Research Lab from primarily evaluating ML prediction quality to systematically evaluating **executable trading strategies and their net financial performance**.

The ultimate objective is to discover, validate, and eventually deploy quantitative trading algorithms capable of producing sustainable risk-adjusted returns.

ML is one possible source of trading signals. It is not the final product.

The primary research output must be evidence of trading profitability after realistic costs, risk limits, and independent validation.

Do not restart the repository or rebuild previously completed milestones.

## 1. Audit the Existing Pipeline

Inspect:

- Saved ML predictions.
- Prediction timestamps.
- Model versions.
- Feature definitions.
- Historical dataset snapshots.
- Existing backtesting engine.
- Portfolio construction.
- Risk management.
- Corporate-action handling.
- Strategy discovery.
- Statistical validation.

Determine whether existing predictions can be converted into executable trading decisions without look-ahead bias.

Identify missing functionality and reuse existing implementations.

Run the existing test suite before making changes.

## 2. Convert Predictions Into Trading Signals

Implement a reusable ML-to-strategy adapter.

Support explicit rules for:

- BUY.
- SELL.
- HOLD.
- EXIT.
- Target position sizing.
- Rebalancing.
- Cash allocation.

Initially support:

1. Top-N predicted return ranking.
2. Positive predicted-return thresholds.
3. Volatility-adjusted rankings.
4. Probability-based entry thresholds.
5. Long-only portfolio construction.
6. Configurable maximum position weights.

Require all signals to reference predictions that were available before their simulated execution time.

Avoid unnecessary strategy complexity.

## 3. Execution and Position Management

Integrate signals with the existing event-driven backtester.

Support:

- Market orders.
- Next-session execution.
- Configurable holding periods.
- Rebalancing schedules.
- Position exits.
- Portfolio cash accounting.
- Fractional or whole-share assumptions.
- Insufficient buying-power checks.
- Order rejection reporting.

Prevent same-bar execution when the signal relies on that bar's completed data.

## 4. Realistic Transaction Costs

Include:

- Commissions.
- Bid/ask spread.
- Slippage.
- Market impact assumptions where appropriate.
- Turnover.
- Position liquidation costs.

Support multiple cost scenarios.

At minimum:

- Low-cost scenario.
- Baseline-cost scenario.
- High-cost scenario.

Do not report gross returns as net returns.

## 5. Corporate Actions and Data Integrity

Verify that the backtester correctly handles:

- Stock splits.
- Reverse splits.
- Cash dividends.
- Price adjustment conventions.
- Symbol changes.
- Delisted securities where data is available.

Do not double-count dividends or apply split adjustments twice.

Use raw executable prices when required by the accounting model.

Maintain clear separation between:

- Adjusted research prices.
- Raw execution prices.
- Corporate-action event ledgers.

If corporate-action or historical-universe coverage is incomplete, label the results as exploratory.

Do not silently disable data-quality gates to produce attractive results.

## 6. Benchmark Comparisons

Compare strategies against:

- Buy-and-hold SPY.
- Equal-weighted eligible stocks.
- Simple momentum.
- Simple mean reversion.
- Cash or a risk-free baseline where appropriate.

Use equivalent evaluation periods and consistent cost assumptions.

Include portfolio exposure differences when interpreting relative performance.

## 7. Trading Performance Metrics

Calculate and report:

- Total return.
- Annualized return.
- Annualized volatility.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Calmar ratio.
- Profit factor.
- Win rate.
- Average trade P&L.
- Number of trades.
- Portfolio turnover.
- Commission costs.
- Spread costs.
- Slippage costs.
- Monthly returns.
- Yearly returns.
- Performance by market regime.
- Benchmark-relative returns.

Clearly separate gross performance from net performance.

## 8. Profitability-Focused Strategy Discovery

Update the automated discovery engine so that experiments evaluate executable strategy performance, not prediction metrics alone.

Use objective functions that consider:

- Net returns.
- Drawdowns.
- Risk-adjusted performance.
- Turnover.
- Transaction costs.
- Consistency across validation periods.
- Statistical uncertainty.

A candidate with excellent prediction accuracy but negative net trading returns must not qualify as profitable.

Avoid optimizing solely for maximum historical CAGR or Sharpe ratio.

Require adequate trade counts and meaningful performance across independent validation periods.

Track all tested configurations, including failures.

## 9. Out-of-Sample Validation

Preserve existing statistical safeguards:

- Chronological training and validation.
- Purging and embargo where needed.
- Untouched final holdout periods.
- Multiple-testing corrections.
- Robustness tests.
- Cost sensitivity analysis.
- Parameter stability analysis.

Use only the permitted validation periods during strategy discovery.

Do not consume protected final holdouts.

Do not automatically promote strategies to paper or live trading.

## 10. End-to-End Profitability Demonstration

Using the existing verified historical data and saved out-of-sample predictions:

1. Load the dataset.
2. Verify prediction timestamps.
3. Convert predictions into trading signals.
4. Construct a portfolio.
5. Execute simulated trades.
6. Apply commissions, spread, and slippage.
7. Apply existing risk controls.
8. Calculate net portfolio returns.
9. Compare against SPY and equal-weight holdings.
10. Calculate drawdowns and risk-adjusted metrics.
11. Generate equity curves and trade logs.
12. Produce a comprehensive performance report.

Run at least one ML-driven strategy and one simple non-ML baseline.

If the datasets lack sufficient corporate-action or point-in-time evidence, run only a clearly labeled exploratory demonstration using valid available observations.

Do not claim validated historical profitability from incomplete datasets.

## 11. Automated Tests

Add deterministic tests for:

- Prediction-to-signal conversion.
- Signal timestamp alignment.
- Position sizing.
- Rebalancing.
- Order execution timing.
- Transaction costs.
- Cash accounting.
- Corporate-action adjustments.
- Benchmark alignment.
- Net return calculations.
- Turnover.
- Drawdown.
- Portfolio valuation.
- Strategy ranking.
- Look-ahead bias prevention.
- Research-readiness gates.

Use hand-calculated trade examples to verify financial correctness.

## 12. Dashboard Integration

Update the dashboard so that trading performance takes priority over prediction accuracy.

The primary strategy research views should display:

- Net equity curve.
- Benchmark-relative performance.
- Maximum drawdown.
- Annualized return.
- Sharpe and Sortino ratios.
- Turnover.
- Trading costs.
- Performance by period.
- Statistical validation status.

Keep model prediction metrics available as diagnostic information.

Do not label exploratory backtests as validated trading results.

## 13. Final Deliverables

Provide:

1. A summary of the ML-to-strategy integration.
2. Explicit trading rules for each demonstrated strategy.
3. Actual simulated trade logs.
4. Net performance reports.
5. Benchmark comparisons.
6. Transaction cost breakdown.
7. Drawdown analysis.
8. Research-data limitations.
9. Statistical validation status.
10. Automated test results.
11. Recommendations for the next research campaign.

Do not fabricate performance results or weaken existing data-quality safeguards.

## Final Directive

The primary measure of success is whether the platform can rigorously determine if a trading strategy would have made money after costs under historically executable assumptions.

Predictive accuracy is a supporting diagnostic metric.

**Implement Phase 12C using the existing repository and demonstrate the complete prediction-to-profitability research workflow.**

Do not begin live trading or consume protected holdouts.