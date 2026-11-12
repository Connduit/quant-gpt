# Quant Research Lab — Milestone 6: Portfolio Construction, Optimization & Risk Management

Milestones 1–5 have been implemented. Continue developing the existing Quant Research Lab repository using the original project blueprint and updated roadmap.

Do not restart the project or unnecessarily rewrite existing components.

## Primary Objective

Build a multi-strategy portfolio construction and risk management system that can combine independently researched quantitative trading strategies, allocate capital between them, manage correlated exposures, and enforce portfolio-wide risk constraints.

The system must support strategies that use machine learning as well as conventional systematic strategies.

**The primary objective is to construct robust portfolios capable of generating sustainable risk-adjusted returns while controlling downside risk.**

No portfolio optimization method should assume that historical performance guarantees future profitability.

## 1. Audit Existing Infrastructure

Before implementation:

1. Inspect the existing repository and completed milestones.
2. Run the current automated test suite.
3. Review event-driven backtesting and portfolio accounting.
4. Inspect ML strategy signal interfaces.
5. Review automated strategy discovery results.
6. Inspect Milestone 5 validation reports and candidate statuses.
7. Identify reusable components and architectural integration requirements.
8. Preserve existing functionality.

Document any necessary architectural changes.

## 2. Multi-Strategy Portfolio Architecture

Implement a portfolio framework capable of managing multiple strategies simultaneously.

Requirements:

- Register independent strategies.
- Accept their signals and target positions.
- Maintain separate strategy-level virtual portfolios.
- Maintain an authoritative combined portfolio.
- Prevent double-counting shared cash or positions.
- Support shared capital constraints.
- Track strategy-level and portfolio-level profit and loss.
- Support assets shared between strategies.
- Net opposing strategy orders where appropriate.
- Preserve strategy attribution when positions are netted.
- Track exposure and risk across all strategies.

Create extensible interfaces for future equities and futures strategies.

## 3. Capital Allocation Methods

Implement multiple portfolio allocation approaches.

Start with:

- Equal weighting.
- Fixed configurable weights.
- Inverse volatility weighting.
- Risk parity or risk budgeting.
- Volatility targeting.

Consider constrained mean-variance optimization as an optional additional method.

Requirements:

- Estimate volatility and covariance using only information available at allocation time.
- Handle missing or insufficient history.
- Support regularized covariance estimates where appropriate.
- Avoid unstable weights caused by noisy expected-return estimates.
- Apply concentration and exposure limits.
- Respect available capital and leverage constraints.
- Allow allocations to cash.

Do not implement complex ML-based capital allocation before establishing reliable baseline methods.

## 4. Strategy Selection and Eligibility

Integrate with Milestone 5 statistical validation.

Only strategies meeting defined eligibility rules should be candidates for production allocation.

Support:

- Research-only strategies.
- Rejected strategies.
- Strategies requiring additional validation.
- Strategies eligible for paper trading.
- Suspended strategies.

The portfolio engine must not automatically promote a strategy into live trading.

Implement explicit strategy eligibility and approval checks.

## 5. Correlation and Diversification Analysis

Calculate:

- Rolling return correlations.
- Strategy covariance matrices.
- Portfolio volatility.
- Marginal risk contributions.
- Risk concentration.
- Strategy exposure overlap.
- Portfolio diversification metrics.

Identify strategies that appear independent individually but have highly correlated losses during stressed markets.

Report correlation instability across different historical periods.

Do not assume that low historical correlation guarantees future diversification.

## 6. Position Sizing

Implement configurable position sizing methods:

- Fixed fractional sizing.
- Volatility-adjusted sizing.
- ATR-based sizing.
- Target portfolio weight sizing.
- Risk-budget-based sizing.

Position sizing must respect:

- Available buying power.
- Maximum per-position allocation.
- Portfolio exposure limits.
- Instrument contract multipliers.
- Minimum tradable quantities.
- Transaction costs.
- Risk constraints.

Keep instrument-specific sizing logic extensible for future futures support.

## 7. Portfolio Risk Management

Implement configurable limits for:

- Maximum portfolio gross exposure.
- Maximum net exposure.
- Maximum position concentration.
- Maximum sector exposure.
- Maximum correlated exposure.
- Maximum strategy allocation.
- Maximum leverage.
- Maximum daily loss.
- Maximum portfolio drawdown.
- Maximum per-strategy drawdown.

Risk rules must be enforced before orders are accepted.

Implement structured risk-decision outputs explaining why orders are approved, reduced, or rejected.

## 8. Drawdown and Strategy Suspension

Implement monitoring capable of:

- Tracking rolling drawdowns.
- Detecting strategy performance degradation.
- Suspending strategies after predefined risk breaches.
- Reducing portfolio exposure under stress.
- Blocking new positions when risk limits are exceeded.
- Allowing controlled manual reactivation.

Avoid continuously changing parameters in response to short-term losses without proper validation.

Do not automatically liquidate all positions on an arbitrary drawdown threshold without a documented and tested liquidation policy.

## 9. Portfolio Rebalancing

Support:

- Daily, weekly, and monthly schedules.
- Threshold-based rebalancing.
- Minimum trade-size requirements.
- Transaction-cost-aware rebalancing.
- Configurable turnover limits.
- Cash buffers.
- Rebalancing logs.

Avoid excessive trading caused by minor changes in target weights.

## 10. Portfolio-Level Backtesting

Integrate the portfolio engine with the existing event-driven backtester.

The combined backtest must simulate:

- Multiple active strategies.
- Shared account equity and cash.
- Competing orders.
- Position netting.
- Portfolio allocation.
- Transaction costs.
- Portfolio-wide risk constraints.
- Strategy-level attribution.
- Rebalancing.
- Suspensions.

All allocation decisions must be based only on information available at that historical time.

Avoid constructing portfolio weights using future realized strategy performance.

## 11. Performance Evaluation

Generate portfolio reports containing:

- Annualized return.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Portfolio volatility.
- Strategy correlations.
- Risk contributions.
- Capital allocations.
- Portfolio turnover.
- Transaction costs.
- Strategy-level P&L.
- Portfolio-level P&L.
- Benchmark-relative performance.

Compare:

1. Individual strategies.
2. Equal-weight portfolios.
3. Inverse-volatility portfolios.
4. Risk-budgeted portfolios.
5. Relevant benchmarks.

Clearly distinguish in-sample, validation, and untouched final holdout performance.

## 12. Stress Testing

Evaluate portfolio behavior under:

- Higher trading costs.
- Increased volatility.
- Sudden correlation increases.
- Large overnight price gaps.
- Strategy underperformance.
- Liquidity constraints.
- Missing market data.
- Failed or rejected orders.
- Temporary broker disconnection scenarios where applicable.

Use both historical scenarios and explicitly labeled hypothetical scenarios.

Do not represent simulated stress results as forecasts.

## 13. CLI and Configuration

Extend the existing CLI to support:

- Creating portfolio configurations.
- Registering strategies.
- Assigning allocation methods.
- Running portfolio backtests.
- Calculating risk exposures.
- Running stress tests.
- Generating portfolio reports.

Use YAML configuration and existing project conventions.

## 14. Testing

Add deterministic tests for:

- Shared cash accounting.
- Strategy position attribution.
- Order netting.
- Position sizing.
- Covariance estimation.
- Portfolio weights.
- Exposure constraints.
- Risk-limit enforcement.
- Drawdown calculations.
- Strategy suspension.
- Rebalancing.
- Look-ahead prevention.
- Multi-strategy backtesting.
- Portfolio P&L reconciliation.

Include hand-calculated financial examples to verify numerical correctness.

## 15. End-to-End Demonstration

Using existing verified historical research snapshots:

1. Load at least two independently evaluated strategies.
2. Verify their research eligibility.
3. Construct an equal-weight portfolio.
4. Construct an inverse-volatility portfolio.
5. Backtest both using historical data.
6. Apply transaction costs and risk constraints.
7. Compare individual and combined strategy performance.
8. Generate an allocation and risk report.
9. Explain diversification benefits or shortcomings.

Use only permitted historical research windows.

Do not access the reserved final holdout.

If no existing strategies qualify for paper trading, demonstrate the mechanics with explicitly labeled research-only strategies rather than incorrectly promoting failed candidates.

## 16. Documentation

Update:

- Architecture documentation.
- Portfolio design.
- Allocation methodology.
- Risk management.
- Strategy eligibility.
- Backtesting integration.
- Configuration examples.
- Testing instructions.
- Development roadmap.

## 17. Completion Criteria

Milestone 6 is complete when:

- Multiple strategies can operate in one simulated portfolio.
- Shared capital is accounted for correctly.
- Allocation methods work.
- Risk limits are enforced.
- Position sizing is functional.
- Strategy-level attribution reconciles with portfolio results.
- Portfolio backtests execute end-to-end.
- Stress testing works.
- Reports are reproducible.
- Automated tests pass.

After implementation:

1. Summarize all changes.
2. Report test results.
3. Show the portfolio demonstration output.
4. Identify validated and research-only strategies.
5. Document limitations.
6. Explain what is needed for Milestone 7.

Do not automatically begin Milestone 7.

Begin implementing Milestone 6 using the existing repository.