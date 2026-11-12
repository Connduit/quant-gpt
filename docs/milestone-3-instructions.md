# Quant Research Lab — Milestone 3: Feature Engineering & Machine Learning

Milestones 1 and 2 have been implemented. Continue developing the existing Quant Research Lab repository according to the original project blueprint and updated development roadmap.

Do not restart the project or unnecessarily rewrite existing components.

## Objective

Implement the first complete machine learning research pipeline capable of analyzing historical stock market data, learning predictive relationships, generating trading signals, and evaluating those signals through our existing event-driven backtesting engine.

The objective is not simply to predict stock prices. It is to determine whether machine learning can produce statistically meaningful, economically useful trading signals that outperform simple baseline strategies after realistic transaction costs.

## 1. Review Existing Implementation

Before writing new code:

- Inspect the current data infrastructure and backtesting engine.
- Review existing strategy interfaces and configuration systems.
- Identify integration requirements.
- Preserve backward compatibility where practical.
- Verify that Milestones 1 and 2 still function correctly.

Make targeted architectural improvements only when necessary.

## 2. Feature Engineering Engine

Implement a modular feature engineering system supporting:

**Price and momentum features**
- Returns over 1, 3, 5, 10, 20, and 60 trading days.
- Log returns.
- Momentum and relative strength.
- Distance from moving averages.
- Rolling highs and lows.

**Volatility features**
- Rolling realized volatility.
- Average True Range.
- Volatility ratios.
- Downside volatility.
- Volatility changes.

**Volume features**
- Relative volume.
- Dollar volume.
- Volume momentum.
- Volume moving averages.

**Technical indicators**
- RSI.
- MACD.
- Bollinger Bands.
- Moving average crossovers.

**Market context**
- SPY momentum.
- SPY volatility.
- Sector-relative strength where data is available.
- Broad market trend.

Every feature must use only information available at the prediction timestamp.

Make feature calculations configurable, reusable, and independently testable.

## 3. ML Dataset Generation

Implement a dataset builder that converts historical market data into supervised learning datasets.

Support configurable prediction horizons, initially:

- 1 trading day
- 5 trading days
- 10 trading days

Primary prediction target:

**Forward five-day stock excess return relative to SPY.**

Include optional classification targets for predicting whether future excess returns are positive.

Requirements:

- Point-in-time feature alignment.
- Explicit prediction and execution timestamps.
- Proper handling of missing data.
- No future information in model inputs.
- Chronological train/validation/test splits.
- Purging overlapping labels where needed.
- Training-only preprocessing and normalization.
- Configurable ticker universes.
- Reproducible dataset generation.

Do not use a current-only stock universe to make claims about unbiased historical results. Clearly document any survivorship bias in the available datasets.

## 4. Machine Learning Models

Implement a common model interface supporting:

1. Ridge regression.
2. Logistic regression.
3. Random Forest.
4. LightGBM.
5. XGBoost.

Use appropriate models for regression versus classification targets.

All models must support:

- Training.
- Prediction.
- Evaluation.
- Serialization.
- Loading previously trained models.
- Configurable hyperparameters.
- Reproducible random seeds.

Initially use CPU training. GPU acceleration may be added where beneficial, but it must remain optional.

## 5. ML-Based Trading Strategy

Implement an ML stock-ranking strategy integrated with the existing backtesting engine.

Example workflow:

1. Calculate historical features.
2. Train a model on prior historical data.
3. Generate predictions for eligible stocks.
4. Rank stocks by predicted forward excess return.
5. Select the highest-ranked candidates.
6. Construct positions using configurable portfolio rules.
7. Rebalance at a configurable frequency.
8. Execute trades through the existing backtesting engine.
9. Evaluate net performance after transaction costs.

Support configurable:

- Number of selected stocks.
- Minimum liquidity.
- Rebalancing frequency.
- Maximum position size.
- Cash allocation.
- Market regime filters.

Default to long-only strategies without leverage.

Ensure each backtest prediction comes from a model that could actually have been trained using only information available at that point in history.

Do not train on the full dataset and then backtest predictions over that same period.

## 6. Model Evaluation

Evaluate predictive performance using:

- Mean squared error.
- Mean absolute error.
- Directional accuracy.
- Rank information coefficient.
- Prediction calibration for probabilistic classifiers.
- Feature importance where supported.

Evaluate trading performance using:

- Annualized return.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Profit factor.
- Turnover.
- Transaction costs.
- Performance relative to SPY.

Compare ML strategies against:

- Buy-and-hold SPY.
- Random stock rankings.
- Simple momentum.
- Simple mean reversion.
- Equal-weighted eligible stock portfolios where appropriate.

Random baselines must be reproducible.

The system should explicitly report when ML fails to outperform simpler methods.

## 7. Walk-Forward Testing

Implement a basic chronological walk-forward evaluation process.

For example:

- Train on an initial historical window.
- Validate on a subsequent window.
- Generate out-of-sample predictions.
- Advance the training window.
- Retrain according to a configurable schedule.
- Repeat.

Avoid leakage caused by overlapping prediction horizons.

Keep a final holdout period untouched for later independent evaluation.

Full automated strategy discovery and advanced statistical validation remain future milestones.

## 8. Experiment Configuration

Allow experiments to be defined using YAML configuration files.

Example:

```yaml
experiment:
  name: ml_stock_ranking_v1

data:
  prediction_horizon: 5
  benchmark: SPY

model:
  type: lightgbm
  objective: regression

strategy:
  type: ml_ranking
  top_n: 10
  rebalance_frequency: weekly
  long_only: true

validation:
  method: walk_forward
  training_years: 5
  validation_months: 6

execution:
  slippage_bps: 5
```

Extend this configuration with all necessary parameters while keeping it simple and documented.

## 9. Testing Requirements

Add automated tests verifying:

- Feature calculation correctness.
- Prediction target alignment.
- No look-ahead bias.
- Chronological splitting.
- Overlapping label handling.
- Model training and inference.
- Model serialization.
- Strategy signal generation.
- Rebalancing.
- Compatibility with the existing backtesting engine.
- Reproducibility.

Use deterministic synthetic data for numerical unit tests.

Use real historical data for integration demonstrations when available, clearly identifying its source and limitations.

## 10. End-to-End Demonstration

Create a runnable research example that:

1. Loads historical stock data.
2. Generates features.
3. Creates properly aligned training datasets.
4. Trains baseline and ML models.
5. Generates out-of-sample predictions.
6. Constructs an ML-based portfolio.
7. Runs the existing event-driven backtester.
8. Calculates predictive and trading metrics.
9. Compares results against baseline strategies.
10. Exports a research report.

The report should show both model performance and actual simulated trading performance.

Do not fabricate profitable results or treat synthetic test outcomes as evidence of a genuine trading edge.

## 11. Documentation

Update the project documentation with:

- ML architecture.
- Feature definitions.
- Target definitions.
- Training and testing methodology.
- Model interfaces.
- Strategy integration.
- Configuration examples.
- Commands for running experiments.
- Known limitations.

Update the overall development roadmap.

## 12. Completion Criteria

Milestone 3 is complete only when:

- All required features are implemented.
- ML models train and generate predictions.
- Predictions are strictly out of sample.
- An ML trading strategy executes through the existing backtester.
- Performance can be compared against non-ML baselines.
- Automated tests pass.
- An end-to-end research experiment runs successfully.
- Results and limitations are documented.

Do not begin Milestone 4 automatically.

After implementation, summarize what was built, show the test results and example experiment output, explain any unresolved limitations, and identify what will be needed for automated strategy discovery.

**Begin implementing Milestone 3 using the existing codebase.**