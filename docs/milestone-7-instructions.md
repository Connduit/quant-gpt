# Quant Research Lab — Milestone 7: Futures Research & Machine Learning

Milestones 1–6 have been implemented. Continue developing the existing Quant Research Lab repository according to the original blueprint and updated development roadmap.

Do not restart the project, unnecessarily rewrite existing components, or break existing equities functionality.

## Primary Objective

Expand Quant Research Lab to support quantitative futures research, intraday strategy discovery, machine learning, and realistic futures backtesting.

The primary instruments are:

- ES — E-mini S&P 500
- MES — Micro E-mini S&P 500
- NQ — E-mini Nasdaq-100
- MNQ — Micro E-mini Nasdaq-100

The system should eventually discover, evaluate, and compare futures trading strategies using machine learning and systematic experimentation.

Prioritize research correctness, realistic execution modeling, and statistical validity over achieving attractive backtested returns.

**This is a research-only milestone. Do not implement or enable live futures trading.**

---

## 1. Audit Existing Infrastructure

Before implementing new functionality:

1. Inspect the repository and review Milestones 1–6.
2. Run the existing automated test suite.
3. Review the historical data infrastructure.
4. Review the event-driven backtester.
5. Review strategy and ML model interfaces.
6. Review automated strategy discovery.
7. Review Milestone 5 validation and holdout protections.
8. Review portfolio construction and risk management.
9. Identify any assumptions that are specific to equities and cannot safely apply to futures.

Preserve working functionality.

Document any necessary architectural changes.

## 2. Futures Instrument Model

Implement an extensible futures instrument definition.

Each contract must support:

- Exchange.
- Product symbol.
- Contract month and year.
- Expiration date.
- Last trading date.
- Contract multiplier.
- Minimum tick size.
- Tick value.
- Trading hours.
- Currency.
- Initial and maintenance margin requirements where available.
- Settlement and marking conventions.
- Contract-specific market data identifiers.

Use authoritative exchange specifications where possible.

Do not hardcode broker margin requirements as permanent exchange-level constants.

The initial instrument set should include ES, MES, NQ, and MNQ.

Contract definitions must distinguish the futures product from individual expiring contracts.

## 3. Futures Market Data Infrastructure

Extend the existing market data provider architecture to support futures.

Required data:

- Historical OHLCV.
- Intraday bar data.
- Individual contract identifiers.
- Contract expiration metadata.
- Trading session information.
- Volume and open interest where available.
- Bid/ask data where available.

Prioritize one-minute historical bars for initial intraday research.

Support future expansion to tick, trade, quote, and order-book data.

### Data Providers

Investigate legitimate futures data providers, including Databento and any accessible sources already configured in the project.

Do not assume that Stooq provides suitable futures data merely because its equity downloads work.

If suitable historical futures data requires a paid subscription or credentials:

- Implement the provider interface.
- Document the data requirements and expected costs if verified.
- Identify which functionality can be tested with available data.
- Do not fabricate real market data.
- Do not silently substitute simulated prices for historical market data.

Keep offline tests functional using explicitly labeled deterministic fixtures.

## 4. Contract Expiration and Continuous Futures

Implement contract-aware historical data processing.

Support:

- Individual futures contracts.
- Contract expiration.
- Contract selection.
- Configurable roll schedules.
- Volume-based roll criteria.
- Calendar-based roll criteria.
- Continuous futures research series.
- Roll-adjusted chart series where appropriate.
- Correct execution on actual tradable contract prices.

**Critical:** A continuous futures series is a research representation, not a directly tradable instrument.

Do not calculate realistic fills or P&L using synthetic back-adjusted prices.

Backtesting must use actual contract prices, contract multipliers, and simulated roll transactions.

Include unit tests covering contract transitions.

## 5. Futures Trading Sessions

Implement exchange-aware futures trading calendars.

Support:

- Overnight sessions.
- Session boundaries.
- Exchange holidays.
- Early closes.
- Maintenance breaks.
- Daylight saving time.
- Regular trading hours.
- Extended trading hours.

Use timezone-aware timestamps.

Store timestamps in UTC while preserving exchange-local session definitions.

Intraday features must reset or persist across sessions according to their documented definitions.

## 6. Futures Backtesting Engine

Extend the existing event-driven backtester to support futures accounting.

Requirements:

- Long and short positions.
- Contract-based position sizing.
- Contract multipliers.
- Tick-size validation.
- Futures commissions.
- Exchange and regulatory fees where applicable.
- Bid/ask spread assumptions.
- Slippage modeling.
- Realized and unrealized P&L.
- Daily settlement and variation margin where appropriate.
- Margin requirements.
- Available buying power.
- Margin breaches.
- Forced liquidation policies.
- Contract expiration.
- Contract rolling.
- Overnight position handling.

Keep futures accounting separate from equity-specific cash accounting where necessary.

### P&L Formula

For a futures position:

\[
PnL = (P_{\mathrm{exit}}-P_{\mathrm{entry}})\times M \times N \times D
\]

Where:

- \(P_{\mathrm{exit}}\) = exit price.
- \(P_{\mathrm{entry}}\) = entry price.
- \(M\) = contract multiplier.
- \(N\) = number of contracts.
- \(D\) = position direction, +1 for long and −1 for short.

This formula represents gross trade P&L before fees and other costs.

Implement contract-aware order validation and position accounting.

Include hand-calculated tests for all four initial futures products.

## 7. Intraday Feature Engineering

Extend the feature engine with futures-specific features.

### Price and Momentum

- One-minute returns.
- Five-minute returns.
- Fifteen-minute returns.
- Intraday momentum.
- Opening-range highs and lows.
- Distance from session open.
- Previous session highs and lows.

### Volatility

- Intraday realized volatility.
- Rolling price ranges.
- ATR.
- Volatility expansion and contraction.
- Intraday volatility regimes.

### Volume

- Relative intraday volume.
- Volume spikes.
- VWAP.
- VWAP deviation.
- Volume-weighted momentum.

### Market Context

- Time of day.
- Session type.
- Overnight price movement.
- Prior session return.
- Market trend.
- Market volatility regime.
- ES/NQ relative strength where data permits.

All features must be computed using information available at prediction time.

Do not use completed session statistics before the session ends.

## 8. Initial Futures Strategy Families

Implement configurable baseline strategies.

### Strategy A — VWAP Mean Reversion

Research whether large deviations from VWAP tend to revert under particular market conditions.

Potential features:

- VWAP deviation.
- Realized volatility.
- Volume.
- Time of day.
- Trend strength.

### Strategy B — Opening-Range Breakout

Research whether breaks above or below the opening range predict continuation.

Potential features:

- Opening-range width.
- Breakout strength.
- Volume.
- Market volatility.
- Overnight return.

### Strategy C — Intraday Momentum

Research continuation over short time horizons.

Potential features:

- Recent returns.
- Volume acceleration.
- Volatility.
- Time of day.
- Trend strength.

### Strategy D — Regime-Aware Futures Trading

Research whether different market conditions favor different baseline strategies.

Potential regimes:

- Trending.
- Range-bound.
- High volatility.
- Low volatility.

Regime classifications must be based only on information available at the historical decision time.

These are hypotheses, not assumed profitable strategies.

## 9. Machine Learning Integration

Reuse the existing ML infrastructure.

Support futures research using:

- Ridge and logistic regression.
- Random Forest.
- LightGBM.
- XGBoost.

Research prediction targets such as:

- Forward five-minute return.
- Forward fifteen-minute return.
- Forward sixty-minute return.
- Probability of positive forward return.
- Volatility-adjusted future return.
- Probability of breakout continuation.

Include transaction costs when evaluating whether predicted returns are economically useful.

Models must be trained and evaluated using chronological splits.

Prevent leakage across overlapping intraday labels, trading sessions, and contract rolls.

Do not assume strong directional accuracy means a profitable trading strategy.

## 10. Automated Futures Strategy Discovery

Integrate futures strategies with the Milestone 4 automated discovery framework.

Support bounded searches across:

- Instruments.
- Timeframes.
- Feature groups.
- Prediction horizons.
- ML models.
- Entry thresholds.
- Exit rules.
- Stop-loss rules.
- Profit-taking rules.
- Market regimes.
- Position-sizing methods.

Use Optuna and MLflow through the existing experiment interfaces.

Track all tested configurations, including failures.

Apply the statistical validation methods from Milestone 5.

Do not access the protected final holdout during model discovery or optimization.

## 11. Futures Risk Management

Integrate futures with the Milestone 6 risk engine.

Implement:

- Maximum contracts per instrument.
- Maximum notional exposure.
- Maximum margin utilization.
- Maximum leverage.
- Maximum daily loss.
- Maximum strategy drawdown.
- Maximum portfolio drawdown.
- Contract-aware tick risk.
- Pre-trade risk checks.
- Margin breach handling.
- Trading suspension after critical risk events.

Support risk limits separately for paper trading, research, and eventual live trading.

The system must not assume that stop orders guarantee maximum losses.

## 12. Performance Analysis

Generate futures-specific research reports including:

- Gross P&L.
- Net P&L.
- Commissions and fees.
- Slippage.
- Average profit per contract.
- Win rate.
- Profit factor.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Trade frequency.
- Performance by time of day.
- Performance by market regime.
- Long versus short performance.
- Margin utilization.
- Contract roll costs.
- Benchmark comparison where appropriate.

Compare baseline strategies against ML-based futures strategies.

Report when ML fails to improve results.

## 13. CLI and Configuration

Extend the existing CLI with commands for:

- Importing futures contract data.
- Validating futures history.
- Building continuous research series.
- Running futures backtests.
- Training futures ML models.
- Running futures discovery experiments.
- Generating futures validation reports.

Use YAML configurations and existing command conventions.

## 14. Automated Tests

Add tests covering:

- Contract specifications.
- Tick values.
- Contract multipliers.
- Long and short P&L.
- Futures margin accounting.
- Daily settlement.
- Session boundaries.
- Daylight saving transitions.
- Contract expiration.
- Contract rolling.
- Intraday feature timing.
- Order execution.
- Cost calculations.
- ML label alignment.
- Purged chronological validation.
- Holdout isolation.
- Portfolio risk constraints.
- Regression compatibility with equities functionality.

Include deterministic tests with manually verified calculations.

## 15. End-to-End Demonstration

Create a runnable futures research demonstration that:

1. Loads historical data for MES or ES.
2. Validates contract metadata and trading sessions.
3. Generates intraday features.
4. Runs a baseline strategy.
5. Trains at least one ML model.
6. Produces out-of-sample predictions.
7. Runs event-driven futures backtests.
8. Applies commissions, slippage, and margin rules.
9. Compares ML and baseline strategies.
10. Produces a research and validation report.

Use actual historical market data when accessible.

If real futures data is unavailable, demonstrate the engineering pipeline using clearly labeled synthetic test fixtures, but do not claim a real-data research result.

Document precisely what is missing for real-data validation.

Do not consume the reserved final holdout.

## 16. Documentation

Update:

- Futures architecture.
- Contract specifications.
- Data provider integration.
- Contract rolling methodology.
- Futures backtesting.
- Intraday ML features.
- Futures strategy discovery.
- Risk management.
- CLI usage.
- Testing instructions.
- Data limitations.
- Development roadmap.

## 17. Completion Criteria

Milestone 7 is complete when:

- Futures instruments are represented correctly.
- Historical contract data can be ingested through the provider architecture.
- Contract rolling is implemented.
- Futures accounting is numerically correct.
- Intraday features are available.
- Baseline futures strategies run.
- Futures ML models can train and generate out-of-sample predictions.
- Futures discovery experiments integrate with the existing research engine.
- Statistical validation and holdout protections remain enforced.
- Futures risk constraints operate correctly.
- All relevant tests pass.
- The end-to-end demonstration executes successfully with available data.

Clearly distinguish engineering completion from real-market empirical validation.

After completion:

1. Summarize implemented functionality.
2. Report test results.
3. Identify the futures data provider used.
4. Report whether real historical futures downloads succeeded.
5. Show baseline versus ML strategy performance, if real data is available.
6. Identify data and statistical limitations.
7. Explain what remains for Milestone 8.

**Do not automatically begin Milestone 8.**

Begin implementing Milestone 7 using the existing repository.