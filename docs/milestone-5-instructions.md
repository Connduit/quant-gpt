# Quant Research Lab — Milestone 5: Statistical Validation & Overfitting Protection

Milestones 1–4 have been implemented. Continue developing the existing Quant Research Lab repository according to the original blueprint and updated development roadmap.

Do not restart the project or unnecessarily rewrite existing components.

## Primary Objective

Build a rigorous statistical validation framework that determines whether strategies discovered by our automated ML research engine demonstrate credible, repeatable, out-of-sample predictive and trading performance.

The system must be capable of rejecting strategies that appear profitable due to overfitting, data leakage, selection bias, unrealistic execution assumptions, or random chance.

**The objective is not to maximize historical performance. It is to evaluate whether discovered strategies have evidence of a durable statistical edge.**

## 1. Audit the Existing Research Pipeline

Before implementing new functionality:

1. Inspect the entire repository.
2. Review the data ingestion and corporate-action handling.
3. Inspect the feature engineering pipeline.
4. Review the ML training and prediction interfaces.
5. Inspect automated discovery and Optuna optimization.
6. Verify existing chronological validation.
7. Review the event-driven backtester.
8. Inspect the strategy evaluation and ranking system.
9. Run existing tests and document their results.

Identify statistical weaknesses, leakage risks, and integration gaps.

Preserve existing working functionality.

## 2. Advanced Walk-Forward Validation

Implement configurable rolling and expanding walk-forward validation.

Support:

- Rolling training windows.
- Expanding training windows.
- Configurable validation windows.
- Configurable retraining frequency.
- Multiple chronological evaluation folds.
- Explicit data availability timestamps.
- Configurable gaps between training and validation.
- Aggregated out-of-sample performance analysis.

Ensure that each historical prediction uses only models and information that would have been available at the prediction time.

Include a report showing performance for each walk-forward period.

## 3. Purged Validation and Embargo

Implement leakage-resistant validation for overlapping forward-return labels.

Requirements:

- Track the start and end timestamps of each label's information interval.
- Purge training examples whose information intervals overlap validation/test observations.
- Support configurable embargo periods where appropriate.
- Handle multiple assets sharing overlapping market information.
- Validate timestamp boundaries and label alignment.
- Provide automated tests proving that overlapping samples cannot leak across splits.

Do not assume a fixed number of calendar days is equivalent to a number of trading sessions.

## 4. Final Holdout Isolation

Implement strict separation between:

1. Training data.
2. Hyperparameter optimization data.
3. Strategy-selection validation data.
4. Final untouched holdout data.

The automated strategy discovery engine must not access final holdout results while choosing features, models, parameters, or portfolio rules.

Requirements:

- Define immutable holdout manifests.
- Prevent routine research jobs from reading holdout data.
- Record all final holdout evaluations.
- Require explicit authorization to release final holdout results.
- Mark the holdout as consumed after evaluation.
- Prevent accidental reuse of the same holdout as fresh independent evidence.

Do not run final holdout evaluations as part of this milestone's demonstration.

## 5. Multiple-Testing and Data-Snooping Controls

The automated discovery platform may evaluate hundreds or thousands of candidate strategies.

Implement appropriate methods for evaluating selection bias, including:

- Tracking every tested hypothesis and strategy variant.
- Recording rejected and failed trials.
- Estimating effective search complexity.
- Deflated Sharpe Ratio where assumptions permit.
- Probabilistic Sharpe Ratio.
- Multiple-comparison-aware bootstrap methods where appropriate.
- False discovery rate controls for suitable statistical tests.

Document assumptions and limitations.

Do not present any single statistical test as proof that a strategy will remain profitable.

## 6. Bootstrap and Monte Carlo Analysis

Implement statistical uncertainty analysis using methods appropriate for financial time series.

Support:

- Block bootstrap.
- Stationary bootstrap where justified.
- Bootstrap confidence intervals for selected metrics.
- Simulated alternative return paths.
- Drawdown distribution analysis.
- Return stability analysis.

Avoid naive independent random resampling when serial dependence materially affects results.

Clearly distinguish confidence intervals, historical simulations, and forecasts.

## 7. Strategy Robustness Testing

Automatically evaluate promising strategies under:

- Increased commissions.
- Increased slippage.
- Alternative execution delays.
- Different validation periods.
- Nearby hyperparameter configurations.
- Different market volatility regimes.
- Alternative position-sizing rules.
- Different stock universes where reliable historical coverage exists.

Generate a robustness report.

Assess whether profitability disappears under small changes to assumptions.

Do not treat robustness experiments on repeatedly inspected data as independent evidence.

## 8. Statistical Significance and Economic Value

Evaluate both predictive performance and actual financial usefulness.

Include:

- Out-of-sample return analysis.
- Risk-adjusted performance.
- Benchmark-relative returns.
- Drawdown analysis.
- Turnover.
- Exposure.
- Transaction costs.
- Trade count and effective sample size.
- Dependence on unusually profitable trades.
- Confidence intervals where methodologically valid.

A strategy with statistically detectable predictive power but unprofitable execution should not be considered viable.

A strategy with high backtested returns but weak statistical evidence should be flagged.

## 9. Strategy Validation Report

Create an automated report containing:

- Strategy identifier and configuration.
- Dataset versions and time periods.
- Discovery experiment history.
- Number of tested variants.
- Walk-forward performance by fold.
- Predictive metrics.
- Net trading performance.
- Statistical uncertainty.
- Multiple-testing adjustments.
- Robustness results.
- Known data limitations.
- Potential survivorship bias.
- Execution assumptions.
- Rejection reasons.
- Final research status.

Use clearly defined statuses:

- REJECTED
- INSUFFICIENT_EVIDENCE
- REQUIRES_FURTHER_TESTING
- VALIDATED_FOR_PAPER_TRADING

The final status must be determined using documented research rules.

VALIDATED_FOR_PAPER_TRADING does not imply proven future profitability or authorization for live trading.

## 10. Integration With Automated Strategy Discovery

Integrate statistical validation with the Milestone 4 discovery framework.

The system should support:

1. Running discovery experiments.
2. Selecting candidates using training and validation data.
3. Executing advanced statistical tests on permitted research windows.
4. Rejecting candidates that fail validation.
5. Generating research reports.
6. Producing a shortlist for potential paper trading.

The framework must allow zero strategies to pass.

Preserve the separation between strategy discovery and independent final evaluation.

## 11. CLI Integration

Extend the existing CLI to support:

- Running walk-forward validation.
- Running statistical robustness tests.
- Generating confidence intervals.
- Evaluating multiple-testing risk.
- Producing validation reports.
- Comparing validation outcomes.
- Listing rejected and eligible candidates.

Follow the existing command-line architecture.

## 12. Automated Tests

Add deterministic tests covering:

- Chronological split integrity.
- Rolling and expanding windows.
- Purging and embargo correctness.
- Cross-asset label overlap.
- Holdout isolation.
- Multiple-testing calculations.
- Bootstrap calculations.
- Confidence interval behavior.
- Robustness simulations.
- Validation status assignments.
- Reproducibility.
- Integration with the existing discovery framework.

Use known numerical examples and deterministic synthetic data.

## 13. End-to-End Demonstration

Create a reproducible demonstration using existing verified real-data research snapshots.

The demonstration should:

1. Load previously discovered candidate strategies.
2. Run advanced walk-forward validation.
3. Perform appropriate multiple-testing adjustments.
4. Generate bootstrap-based uncertainty estimates.
5. Stress-test transaction costs and execution assumptions.
6. Evaluate strategy stability.
7. Produce a candidate validation report.
8. Identify rejected and potentially paper-tradable candidates.

Do not access the reserved final holdout period.

Do not fabricate favorable results.

It is acceptable and expected for all candidates to fail validation if the evidence is insufficient.

## 14. Documentation

Update the documentation with:

- Statistical validation methodology.
- Walk-forward evaluation.
- Purging and embargo.
- Holdout isolation.
- Multiple-testing controls.
- Bootstrap methodology.
- Robustness testing.
- Research status definitions.
- Known assumptions and limitations.
- Commands for running validation.

Update project progress tracking.

## 15. Completion Requirements

Milestone 5 is complete when:

- Advanced chronological validation works.
- Overlapping labels are handled correctly.
- Final holdout isolation is enforced.
- Multiple-testing controls are implemented.
- Bootstrap uncertainty analysis is available.
- Robustness testing is integrated.
- Candidate strategies receive evidence-based validation statuses.
- Research reports are reproducible.
- Automated tests pass.
- The end-to-end demonstration runs successfully.

After completing Milestone 5:

1. Summarize all implemented components.
2. Report all test results.
3. Show actual strategy validation outcomes.
4. Identify which candidates, if any, qualify for paper trading.
5. Explain remaining statistical limitations.
6. Identify requirements for Milestone 6.

**Do not automatically begin Milestone 6.**

Begin implementing Milestone 5 using the existing repository.