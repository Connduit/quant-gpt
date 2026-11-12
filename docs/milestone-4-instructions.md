# Quant Research Lab — Milestone 4: Automated Strategy Discovery

Milestones 1–3 have been implemented. Continue developing the existing Quant Research Lab repository according to the original blueprint and updated development roadmap.

Do not restart the project, replace existing working systems, or unnecessarily rewrite previously completed components.

## Primary Objective

Implement an automated quantitative strategy research and discovery framework.

The system should systematically generate, configure, execute, compare, and track machine learning trading experiments to identify potentially profitable strategies across combinations of features, prediction targets, model architectures, and portfolio construction rules.

This milestone should transform the existing ML research pipeline into a repeatable, scalable experiment platform.

**The primary goal is to discover robust, statistically meaningful trading hypotheses rather than simply maximize historical backtest returns.**

## 1. Audit Existing Components

Before implementation:

1. Inspect the existing repository.
2. Verify the historical data pipeline.
3. Inspect the feature engineering engine.
4. Inspect existing ML training and prediction interfaces.
5. Inspect the event-driven backtester.
6. Review existing evaluation and walk-forward testing.
7. Run the existing test suite.
8. Identify reusable components and integration gaps.

Preserve working functionality and existing public interfaces whenever practical.

Document any necessary architectural changes.

## 2. Automated Experiment Engine

Build an experiment engine capable of executing configurable research experiments.

Every experiment should specify:

- Data source and dataset version.
- Tradable asset universe.
- Research hypothesis.
- Feature combinations.
- Prediction target and forecast horizon.
- ML model and hyperparameters.
- Training and validation windows.
- Trading signal construction rules.
- Portfolio construction rules.
- Rebalancing frequency.
- Transaction costs.
- Risk constraints.
- Evaluation metrics.
- Random seed.

Each experiment must be reproducible.

Create unique experiment identifiers and persist configurations, predictions, metrics, and artifacts.

Support running single experiments and batches of experiments.

## 3. Automated Search Spaces

Implement a configurable search-space system.

The experiment engine should explore combinations involving:

### Feature selection

- Momentum features.
- Mean-reversion features.
- Volatility features.
- Volume features.
- Market regime features.
- Technical indicator features.
- Cross-sectional relative-strength features.

### Prediction targets

- One-day forward returns.
- Five-day forward returns.
- Ten-day forward returns.
- Benchmark-relative returns.
- Directional classification.
- Volatility prediction.

### Model selection

- Ridge regression.
- Logistic regression for classification.
- Random Forest.
- LightGBM.
- XGBoost.

### Strategy construction

- Top-N stock ranking.
- Prediction thresholds.
- Volatility-adjusted ranking.
- Long-only portfolio construction.
- Different rebalancing frequencies.
- Different position-sizing approaches.
- Market regime filters.

The system should distinguish between valid and incompatible combinations.

Search spaces must be explicitly bounded and configurable.

Do not generate arbitrary, unbounded combinations.

## 4. Optuna Integration

Integrate Optuna as the initial hyperparameter optimization framework.

Support:

- Configurable search spaces.
- Reproducible trials.
- Trial pruning when statistically and operationally appropriate.
- Parallel execution with resource limits.
- Persistent study storage.
- Resuming interrupted studies.
- Recording failed and rejected trials.
- Experiment-level time and compute budgets.

Implement objectives that can combine predictive performance, risk-adjusted trading returns, drawdowns, turnover, and transaction costs.

Avoid optimizing exclusively for maximum historical returns or Sharpe ratio.

Use multiple chronological validation windows.

The optimization process must not repeatedly inspect or optimize against the reserved final test set.

## 5. MLflow Experiment Tracking

Integrate MLflow for experiment tracking.

Record:

- Experiment names and IDs.
- Git commit or code version.
- Dataset versions and hashes.
- Feature configurations.
- Model parameters.
- Training and validation windows.
- Random seeds.
- Model artifacts.
- Predictions.
- Backtest results.
- Performance metrics.
- Transaction cost assumptions.
- Failure reasons.
- Experiment execution status.

The system must support comparing completed trials and reproducing past experiments.

Keep Optuna's trial optimization state separate from MLflow's experiment records while linking them by stable identifiers.

## 6. Strategy Evaluation and Ranking

Implement a strategy comparison engine.

Calculate:

- Out-of-sample annualized return.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Profit factor.
- Win rate.
- Turnover.
- Transaction costs.
- Return stability across validation windows.
- Relative performance against SPY.
- Performance against non-ML strategies.

Design configurable eligibility filters.

For example, strategies may be rejected for:

- Excessive drawdowns.
- Too few trades.
- Unstable performance across windows.
- Excessive turnover.
- High transaction-cost sensitivity.
- Significant dependence on a small number of trades.
- Failed validation or suspected data leakage.

Do not treat arbitrary filtering thresholds as scientifically established.

Report both eligible and rejected strategies with explanations.

Rank surviving candidates using a transparent, documented scoring methodology.

The system must allow zero strategies to pass.

## 7. Preventing Overfitting During Discovery

Automated search increases the risk of data mining and false discoveries.

Implement safeguards appropriate to the current research framework:

- Chronological training and validation.
- Purging of overlapping forward-return labels.
- Embargo periods when necessary.
- Strict separation of training, validation, and final holdout data.
- Training-only preprocessing.
- Tracking the number of hypotheses and trials evaluated.
- Recording failed and discarded experiments.
- Parameter sensitivity analysis.
- Transaction-cost stress tests.
- Multiple independent validation windows.

Implement explicit safeguards that prevent Optuna and automated search from accessing final holdout data.

Include warnings about multiple testing and selection bias in strategy ranking reports.

Advanced statistical validation will be expanded in Milestone 5.

## 8. Strategy Robustness Analysis

For promising strategies, automatically evaluate:

- Performance under higher transaction costs.
- Alternative training periods.
- Alternative validation periods.
- Neighboring hyperparameter configurations.
- Different market environments.
- Different eligible stock universes where reliable historical data is available.
- Different position-sizing assumptions.

Generate a robustness report showing whether the strategy remains viable when assumptions change.

Do not modify the original experiment results when running robustness tests.

## 9. Parallel Research Execution

Support executing multiple independent experiments concurrently.

Requirements:

- Configurable worker count.
- CPU and memory limits where enforceable.
- Optional GPU resource assignment.
- Reliable experiment status tracking.
- Graceful failure recovery.
- Resume functionality.
- Prevention of duplicate experiments.
- Caching reusable historical features.

Keep the initial implementation simple.

Do not introduce distributed infrastructure such as Kubernetes unless there is a demonstrated need.

## 10. Research Reports

Create automated reports containing:

- Research hypothesis.
- Experiment configuration.
- Selected features.
- Model performance.
- Backtest results.
- Benchmark comparisons.
- Equity curves.
- Drawdown curves.
- Cost sensitivity.
- Walk-forward stability.
- Model and parameter comparisons.
- Rejected candidates and rejection reasons.
- Limitations and potential biases.

The reports should clearly distinguish:

1. In-sample training performance.
2. Validation performance.
3. Final untouched holdout performance, when separately authorized for final evaluation.

Do not report validation results as independent final test results.

## 11. Command-Line Interface

Extend the existing CLI to support:

- Running an individual experiment.
- Running an Optuna study.
- Listing experiments.
- Comparing experiment results.
- Reproducing an earlier experiment.
- Generating research reports.
- Viewing rejected trials.
- Resuming interrupted studies.

Use the existing CLI conventions and configuration system.

## 12. Example End-to-End Discovery Experiment

Create a runnable example that:

1. Loads real historical equities data through the existing pipeline.
2. Defines a bounded research search space.
3. Selects valid feature groups and prediction targets.
4. Trains candidate ML models.
5. Generates properly timed out-of-sample predictions.
6. Converts predictions into trading signals.
7. Executes strategies through the existing event-driven backtester.
8. Evaluates transaction-cost-adjusted performance.
9. Runs multiple trials using Optuna.
10. Tracks experiments in MLflow.
11. Compares candidates against baseline strategies.
12. Produces an experiment ranking and robustness report.

Keep the demonstration computationally manageable.

Clearly document any limitations in the market data.

Do not fabricate returns or claim that a profitable strategy has been discovered unless supported by actual results.

## 13. Testing Requirements

Add tests covering:

- Search-space validation.
- Deterministic trial configuration.
- Experiment reproducibility.
- Optuna integration.
- MLflow tracking.
- Model compatibility.
- Failed experiment recovery.
- Resource budget enforcement.
- Duplicate detection.
- Chronological data splitting.
- Look-ahead bias prevention.
- Holdout data isolation.
- Strategy ranking.
- Rejection criteria.
- Robustness calculations.
- Integration with the existing backtester.

Tests should use deterministic fixtures whenever possible.

## 14. Documentation

Update the documentation to explain:

- Automated experiment architecture.
- Search-space configuration.
- Optuna optimization.
- MLflow tracking.
- Running and resuming research studies.
- Reproducing experiments.
- Strategy evaluation.
- Ranking methodology.
- Statistical limitations.
- Future improvements.

Update the overall project roadmap and development progress.

## 15. Completion Requirements

Milestone 4 is complete when:

- Automated research experiments can be configured and executed.
- Optuna can search bounded model and strategy configurations.
- MLflow records experiment history.
- Experiments can be resumed and reproduced.
- Candidate strategies are evaluated using the existing backtester.
- Strategies are compared against appropriate baselines.
- Robustness reports can be generated.
- Holdout isolation is enforced.
- Failed and rejected experiments remain visible.
- Automated tests pass.
- A complete end-to-end experiment runs successfully.

After finishing:

1. Summarize the implementation.
2. Show the test results.
3. Show the results of the demonstration experiment.
4. Explain known limitations.
5. Identify what remains for Milestone 5.

**Do not automatically begin Milestone 5.**

Begin implementing Milestone 4 using the current repository.