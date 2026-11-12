# Quant Research Lab — Development Instructions (Post-Milestone 1)

You have already received the complete Quant Research Lab blueprint and implemented Milestone 1.

**Do not restart the project or recreate the existing codebase.** Continue developing the current repository using the original blueprint as the master specification.

## 1. Review the Existing Architecture

Before implementing additional functionality:

1. Inspect the existing repository and all code created during Milestone 1.
2. Review the original project blueprint and its 12 core capabilities.
3. Identify architectural weaknesses that could interfere with future development.
4. Verify that the existing design can support:
   - Historical and real-time market data.
   - Equities, ETFs, and futures.
   - Machine learning and deep learning models.
   - Automated strategy discovery and experimentation.
   - Event-driven backtesting.
   - Walk-forward validation and overfitting protection.
   - Portfolio optimization.
   - Risk management.
   - Paper and live trading.
   - AI research agents.
   - Monitoring and visualization.
5. Identify missing abstractions, interfaces, or dependencies that should be addressed now.
6. Preserve existing working functionality and avoid unnecessary rewrites.

Make targeted architectural improvements only where justified by concrete requirements.

Document any significant architectural decisions.

## 2. Development Philosophy

The long-term objective is to build an AI-powered quantitative research platform capable of discovering, testing, and deploying trading strategies that may eventually generate sustainable income.

The most important feature is **the ability to systematically discover genuine statistical trading advantages using AI, machine learning, and rigorous experimentation.**

We are not building a conventional trading bot that merely executes hard-coded technical indicators.

The platform should eventually be capable of:

- Discovering potential predictive relationships in market data.
- Evaluating thousands of research hypotheses.
- Training and comparing different machine learning models.
- Identifying suitable trading strategies for different market regimes.
- Optimizing trading parameters without excessive overfitting.
- Comparing strategies across asset classes.
- Combining independent trading strategies into portfolios.
- Monitoring performance degradation.
- Automatically proposing new research experiments.

However, all discovered strategies must undergo rigorous out-of-sample validation. Automated experimentation must not become an uncontrolled search for historically profitable but statistically meaningless strategies.

AI should assist with research and hypothesis generation, not bypass validation or risk controls.

## 3. Implementation Strategy

Use an **architecture-first, milestone-based development approach**.

The overall architecture must account for every core capability, but features should be implemented sequentially.

For every milestone:

1. Review the relevant requirements from the original blueprint.
2. Identify dependencies on existing modules.
3. Implement complete, working functionality for that milestone.
4. Write meaningful unit and integration tests.
5. Verify numerical correctness and financial accounting where relevant.
6. Run the tests and resolve failures.
7. Provide a runnable end-to-end example.
8. Update documentation and development progress.
9. Identify remaining limitations.
10. Explain what should be implemented next.

Avoid placeholder implementations, unnecessary mock functionality, and premature complexity.

Synthetic data may be used for deterministic unit tests, but it must be clearly identified and must not be used to claim real trading performance.

Do not claim a component is complete unless its requirements are implemented and its tests pass.

## 4. Updated Development Priorities

Milestone 1 — Project Foundation and Historical Data Infrastructure

**Status: Previously implemented. Audit and verify; do not rebuild unnecessarily.**

Milestone 2 — Event-Driven Backtesting Engine

Implement realistic historical execution, order handling, fills, transaction costs, cash accounting, position management, performance metrics, and strategy interfaces.

Milestone 3 — Feature Engineering and Machine Learning

Build the feature pipeline, historical training datasets, baseline statistical models, LightGBM, XGBoost, and ML-based stock ranking strategies.

Milestone 4 — Automated Strategy Discovery

Create a configurable experiment framework for evaluating alternative features, models, strategies, and parameter combinations. Integrate Optuna and MLflow.

Milestone 5 — Statistical Validation

Implement chronological walk-forward testing, purged validation where appropriate, leakage detection, parameter robustness analysis, multiple-testing controls, and untouched final holdout testing.

**Important:** Basic leakage prevention, chronological validation, and realistic simulation must be implemented as soon as they are needed by earlier milestones. Do not defer essential correctness safeguards until Milestone 5.

Milestone 6 — Portfolio Construction and Risk Management

Implement multi-strategy portfolios, capital allocation, exposure limits, volatility targeting, drawdown monitoring, and risk constraints.

Milestone 7 — Futures Research

Expand the platform to ES, MES, NQ, and MNQ with contract-aware data, intraday features, futures accounting, and realistic futures backtesting.

Milestone 8 — Paper Trading

Integrate live market data, paper execution, order tracking, risk monitoring, and reconciliation.

Milestone 9 — Dashboard

Build a React/TypeScript frontend with a FastAPI backend for inspecting experiments, models, backtests, portfolios, and trading activity.

Milestone 10 — AI Research Agent

Build a controlled AI research assistant capable of proposing hypotheses, generating experiment configurations, executing permitted research tasks, and analyzing results.

Milestone 11 — Controlled Live Execution

Integrate supported brokers, add broker reconciliation and execution safeguards, and prepare the system for small-scale live deployment.

Live trading must remain disabled by default and require explicit authorization. Do not assume the system is ready to trade real money merely because this milestone is implemented.

## 5. Design for Future AI Capabilities

Although advanced AI functionality will come later, make architectural decisions now that support:

- Multiple interchangeable ML models.
- Automated feature generation.
- Configurable prediction targets.
- Reproducible experiment definitions.
- Distributed or parallel experiments.
- CPU and GPU training.
- Experiment history and model versioning.
- Strategy comparison and selection.
- Regime classification.
- Model retraining and monitoring.
- Autonomous research agents operating inside restricted research environments.

Maintain clear boundaries between research agents, backtesting, portfolio management, and broker execution.

Do not implement complex neural networks, reinforcement learning, or unrestricted autonomous agents before establishing reliable statistical and ML baselines.

## 6. Immediate Task — Milestone 2

After auditing Milestone 1, begin implementing the event-driven backtesting engine.

The initial version should support:

- Daily US equity market data from the existing data pipeline.
- A well-defined strategy interface.
- Chronological market event processing.
- Signal generation.
- Market orders and an extensible order model.
- Realistic next-session execution for signals based on daily closing data.
- Configurable commissions and slippage.
- Cash and position accounting.
- Corporate-action-aware portfolio valuation.
- Portfolio equity tracking.
- Realized and unrealized profit and loss.
- Trade logs.
- Sharpe ratio, annualized return, maximum drawdown, and additional performance metrics.
- Buy-and-hold benchmark comparisons.
- Simple momentum and mean-reversion baseline strategies.

Include deterministic tests for order processing, cash accounting, trade execution, execution timing, portfolio valuation, and prevention of look-ahead bias.

The first end-to-end demonstration should:

1. Load historical market data using the existing Milestone 1 infrastructure.
2. Run a baseline trading strategy.
3. Simulate trades and transaction costs.
4. Calculate portfolio performance.
5. Compare performance with a benchmark.
6. Export a trade log, equity curve, and performance report.

Make the backtesting engine extensible to intraday futures without prematurely implementing futures functionality.

Do not introduce ML training into Milestone 2.

## 7. Completion Requirements

Before considering Milestone 2 complete:

- Run all relevant tests and report their results.
- Verify portfolio accounting with hand-calculated examples.
- Confirm signals cannot execute using unavailable future information.
- Verify that all baseline strategies work end-to-end.
- Document how to execute the demonstration.
- Update the project's roadmap and progress tracking.
- List outstanding limitations and assumptions.

Once Milestone 2 is complete, provide a summary of the implementation and verification results.

**Do not automatically begin Milestone 3.** Wait for my instruction to continue so that I can review each milestone before proceeding.

## Final Objective

The platform should eventually operate as a rigorous, AI-driven quantitative research environment that can search across markets and trading strategies, discover potentially useful statistical patterns, and evaluate whether they remain profitable after realistic transaction costs and risk constraints.

Prioritize correctness, reproducibility, robust statistical validation, and long-term extensibility over quickly implementing a large number of features.

Begin by auditing the current repository and then implementing Milestone 2.