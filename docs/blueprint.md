# Quant Research Lab — AI-Powered Quantitative Trading Platform

## 1. Project Overview

Build a professional-grade, AI-powered quantitative trading research and execution platform.

The long-term goal is to discover, validate, and automate profitable quantitative trading strategies that could eventually generate sufficient income to replace a full-time software engineering job.

The platform should function similarly to a small quantitative hedge fund's research infrastructure.

Rather than relying on a single hard-coded trading strategy, the system should use machine learning, statistical analysis, and automated experimentation to discover potentially profitable trading opportunities across multiple financial markets.

**Primary objective:** Maximize sustainable, risk-adjusted returns after transaction costs, with a long-term objective of generating income through automated trading.

**Important:** The platform must not assume that machine learning guarantees profitable trading. Its purpose is to rigorously test hypotheses, reject weak strategies, identify statistically credible advantages, and manage risk.

### Core Capabilities

1. Download, store, and process historical and live market data.
2. Generate hundreds of quantitative features from market data.
3. Train ML models to predict returns, volatility, and market conditions.
4. Automatically generate and evaluate trading hypotheses.
5. Optimize strategy parameters without introducing look-ahead bias or excessive overfitting.
6. Backtest strategies with realistic transaction costs and execution conditions.
7. Compare strategies using statistical and risk-adjusted performance metrics.
8. Allocate capital across multiple independently validated strategies.
9. Paper trade strategies using live market data.
10. Eventually support automated live execution with strict risk management.
11. Continuously monitor strategy performance and model degradation.
12. Provide a dashboard for analyzing strategies, experiments, trades, and portfolio performance.

The project is designed for an individual quantitative researcher, not a high-frequency trading firm.

---

## 2. Target Markets

The platform should eventually support multiple asset classes.

### Phase 1: US Stocks and ETFs

Initial priority.

Research strategies involving:

- Cross-sectional momentum
- Short-term mean reversion
- Relative strength
- Sector rotation
- Volatility-adjusted momentum
- Machine-learning-based stock ranking
- Market regime filtering

Holding periods should range from approximately one day to several weeks.

### Phase 2: Equity Index Futures

Primary instruments:

- ES — E-mini S&P 500 futures
- MES — Micro E-mini S&P 500 futures
- NQ — E-mini Nasdaq-100 futures
- MNQ — Micro E-mini Nasdaq-100 futures

Research strategies involving:

- Intraday mean reversion
- VWAP reversion
- Opening-range breakouts
- Momentum continuation
- Volatility-regime detection
- Order flow and volume analysis

Holding periods should range from minutes to hours, with the option to research multi-day futures strategies.

### Phase 3: Additional Markets

Potential future additions:

- Cryptocurrency
- Options and volatility strategies
- Foreign exchange
- Commodity futures
- Statistical arbitrage and pairs trading

These markets are out of scope for the initial implementation.

---

## 3. Technical Stack

### Primary Languages

**Python:** Data engineering, machine learning, quantitative research, backtesting, portfolio construction, and experimentation.

**C++:** Potential future performance-critical components such as event processing, low-latency execution, order management, and market data processing.

Do not prematurely rewrite Python components in C++. Profile performance first.

### Data Processing

- NumPy
- Polars
- Pandas where required for library interoperability
- PyArrow
- DuckDB
- Parquet

### Machine Learning

- scikit-learn
- LightGBM
- XGBoost
- PyTorch

### Experimentation

- Optuna for hyperparameter optimization
- MLflow for experiment tracking
- Joblib or another appropriate parallel processing framework
- pytest for automated testing

### Visualization

- React
- TypeScript
- Vite
- Plotly
- FastAPI backend

The dashboard should remain independent of the research engine.

### Hardware

Development environment includes an NVIDIA RTX 4090 with 24 GB VRAM.

Use CUDA acceleration when beneficial, especially for PyTorch training and large experiments.

The system must also support CPU-only operation.

GPU acceleration is not required for the initial baseline models.

### Market Data

Evaluate data providers such as:

- Alpaca for US equities
- Databento for futures
- Other appropriate historical data providers when needed

Implement interchangeable data-provider interfaces.

Do not tightly couple the system to one vendor.

---

## 4. High-Level System Architecture

```text
                     QUANT RESEARCH LAB
                             |
                +------------+------------+
                |                         |
        HISTORICAL DATA              LIVE MARKET DATA
                |                         |
                +------------+------------+
                             |
                    DATA INGESTION
                             |
                    DATA VALIDATION
                             |
                     DATA STORAGE
                  (Parquet / DuckDB)
                             |
                    FEATURE ENGINE
                             |
                 MACHINE LEARNING ENGINE
                             |
               AUTOMATED STRATEGY RESEARCH
                             |
                    BACKTESTING ENGINE
                             |
                  STATISTICAL VALIDATION
                             |
                  PORTFOLIO OPTIMIZATION
                             |
                     RISK MANAGEMENT
                             |
                +------------+------------+
                |                         |
           PAPER TRADING             LIVE TRADING
                |                         |
                +------------+------------+
                             |
                   MONITORING / DASHBOARD
```

The research, backtesting, and live trading components must share consistent strategy interfaces.

However, they must remain independently testable.

---

## 5. Data Infrastructure

Build a reliable market data pipeline before developing sophisticated trading models.

### Required Data

For equities:

- Open, high, low, close, and volume
- Historical dividends
- Stock splits
- Delisting information
- Historical tradable universe membership
- Trading calendars
- Sector and industry classifications
- Bid/ask data when available

For futures:

- Historical OHLCV
- Contract expiration dates
- Trading session definitions
- Contract multipliers
- Tick sizes and values
- Roll schedules
- Real contract prices for execution simulation
- Bid/ask and order-book data when available

### Data Engineering Requirements

- Normalize timestamps to UTC internally.
- Preserve exchange-local trading session information.
- Handle missing or duplicate market data.
- Track corporate actions accurately.
- Distinguish adjusted prices used for research from executable market prices.
- Avoid survivorship bias.
- Avoid look-ahead bias.
- Support incremental downloads.
- Cache downloaded datasets.
- Track data provenance and vendor revisions.
- Provide automated data quality checks.
- Store immutable or versioned research snapshots.

Use Parquet for historical time-series storage and DuckDB for querying.

The system should support expanding from daily data to minute data without a major architectural rewrite.

---

## 6. Feature Engineering Engine

Create a modular system capable of generating predictive features from historical data.

### Price Features

- Returns over multiple horizons
- Log returns
- Momentum
- Relative strength
- Moving average relationships
- Price acceleration
- Distance from recent highs and lows

### Volatility Features

- Historical realized volatility
- Average True Range
- Volatility changes
- Volatility ratios
- Volatility clustering
- Downside volatility

### Volume Features

- Relative volume
- Volume moving averages
- Volume spikes
- Dollar volume
- Price-volume relationships
- VWAP distance for intraday data

### Technical Indicators

- RSI
- MACD
- Bollinger Bands
- Stochastic indicators
- Moving averages

Technical indicators are candidate features, not assumed profitable signals.

### Market Context

- SPY returns
- Sector ETF returns
- Market volatility
- Broad market trend
- Cross-sectional market breadth
- Correlation to market indexes
- Market regime indicators

### Feature Engine Requirements

Every feature must:

- Have a defined calculation method.
- Declare the data it requires.
- Preserve the timestamp when it becomes available.
- Avoid using future information.
- Support configurable lookback periods.
- Handle missing and insufficient history.
- Be independently unit tested.

Feature values should be cached and versioned when practical.

---

## 7. Machine Learning Engine

The machine learning system will investigate whether historical features can predict financially useful outcomes.

### Primary Prediction Objectives

Research models that predict:

1. Expected future returns.
2. Probability of a positive future return.
3. Expected volatility.
4. Relative performance versus a benchmark.
5. Market regime.
6. Probability of favorable risk-adjusted trading outcomes.

### Initial Models

Implement the following in order:

**Baseline models**
- Linear regression
- Ridge regression
- Logistic regression

**Tree-based models**
- Random Forest
- LightGBM
- XGBoost

**Advanced models, later**
- Hidden Markov Models
- LSTM
- Temporal convolutional neural networks
- Transformers
- Reinforcement learning

Do not introduce advanced architectures until simpler models have established meaningful out-of-sample benchmarks.

### Initial ML Research Problem

Predict the five-trading-day forward excess return of liquid US stocks relative to an appropriate benchmark.

Example target:

```text
forward_excess_return =
    forward_stock_return - forward_benchmark_return
```

The first model should rank stocks based on predicted forward excess return.

Then evaluate whether constructing portfolios from the highest-ranked stocks generates attractive net risk-adjusted returns.

### Evaluation Metrics

For predictions:

- Mean squared error
- Mean absolute error
- Directional accuracy
- Rank information coefficient
- Rank stability
- Calibration when predicting probabilities

For trading performance:

- Annualized return
- Sharpe ratio
- Sortino ratio
- Maximum drawdown
- Profit factor
- Win rate
- Average profit and loss per trade
- Turnover
- Exposure
- Transaction costs
- Performance by market regime

Predictive accuracy alone is not sufficient.

The ultimate evaluation must use a realistic executable trading strategy.

---

## 8. Automated Strategy Discovery

Build an experiment engine that systematically evaluates trading hypotheses.

Examples:

- Does five-day momentum predict future returns?
- Is mean reversion stronger following unusually high volume?
- Does volatility filtering improve momentum strategies?
- Do different strategies perform better in different market regimes?
- Can ML-based stock rankings outperform conventional technical indicators?
- Does combining multiple weak signals produce a useful predictive model?

### Experiment Engine Responsibilities

1. Define research hypotheses.
2. Select features.
3. Select prediction targets.
4. Configure ML models.
5. Train models on historical data.
6. Perform chronological validation.
7. Construct executable trading signals.
8. Backtest strategies.
9. Calculate trading performance.
10. Record experiment configurations and results.
11. Compare results against established baselines.
12. Reject strategies that fail validation.
13. Rank promising candidates for further research.

Use Optuna for bounded hyperparameter exploration.

Use MLflow to record:

- Experiment ID
- Dataset version
- Feature set
- Model type
- Hyperparameters
- Training period
- Validation period
- Test period
- Random seed
- Trading strategy configuration
- Performance metrics
- Artifacts and model versions

### AI Research Agent

Eventually introduce an LLM-based research agent capable of:

- Proposing trading hypotheses.
- Generating candidate features.
- Creating experiment configurations.
- Writing research code.
- Running permitted experiments.
- Analyzing results.
- Suggesting follow-up tests.
- Summarizing findings.

The agent must operate within controlled computational and financial limits.

It must not have unrestricted access to live trading.

Do not let the agent repeatedly inspect reserved final test data to optimize a strategy.

Track every hypothesis tested to account for the multiple-testing problem.

The agent is an optional research assistant, not a replacement for statistical validation.

---

## 9. Backtesting Engine

Create a modular, event-driven backtesting engine.

A vectorized research layer can be used for rapid exploratory testing.

However, finalized strategies must undergo event-driven simulation.

### Required Capabilities

- Historical market event replay
- Signal generation
- Order generation
- Position tracking
- Portfolio accounting
- Cash management
- Commission modeling
- Bid/ask spread
- Slippage modeling
- Order latency assumptions
- Market and limit orders
- Partial fills where appropriate
- Position sizing
- Trading calendars
- Portfolio constraints
- Margin and leverage rules
- Borrowing costs when relevant
- Futures contract expiration and rolling
- Unrealized and realized P&L
- Portfolio equity tracking

### Critical Requirement

The simulation must never execute orders using information that was unavailable when the orders would actually have been placed.

For example, a trading signal calculated from a daily closing price cannot assume execution at that same closing price unless the signal was actually available in time to place an eligible closing auction order.

### Outputs

Each backtest should generate:

- Equity curve
- Drawdown curve
- Trade history
- Daily portfolio returns
- Performance summary
- Position history
- Transaction cost breakdown
- Exposure statistics
- Benchmark comparison
- Experiment metadata

---

## 10. Statistical Validation and Overfitting Protection

This is one of the most important components.

Financial markets contain substantial noise.

A complex ML model can learn patterns that do not generalize.

The platform must distinguish genuine predictive value from historical coincidence.

### Required Validation Methods

- Chronological training and validation
- Walk-forward testing
- Purged validation where labels overlap
- Embargo periods where appropriate
- Final untouched holdout periods
- Multiple-testing-aware performance assessment
- Parameter sensitivity testing
- Monte Carlo and bootstrap analysis
- Transaction cost stress testing
- Performance across different market regimes

### Strict Rules

1. Never randomly shuffle time-series observations when that would leak future information.
2. Fit feature scaling and preprocessing only on training data.
3. Prevent future market information from entering current features.
4. Avoid choosing the best strategy solely by historical Sharpe ratio.
5. Track all tested variants, including failures.
6. Do not repeatedly optimize against the reserved holdout period.
7. Avoid survivorship bias.
8. Verify strategies under increased trading costs.
9. Check whether performance depends on a small number of lucky trades.
10. Do not treat backtested returns as guaranteed future returns.

A strategy should only advance when it satisfies predetermined validation criteria.

The system must be capable of concluding that no viable strategy has been found.

---

## 11. Portfolio Construction and Risk Management

Eventually support multiple independent strategies running simultaneously.

### Portfolio Responsibilities

- Allocate capital across strategies.
- Control exposure to correlated assets.
- Limit excessive concentration.
- Adjust positions for volatility.
- Track portfolio-wide risk.
- Compare individual and combined strategy performance.
- Evaluate changing correlations.
- Support cash allocations when no attractive opportunities exist.

### Risk Controls

Implement configurable limits for:

- Maximum position size
- Maximum risk per trade
- Maximum daily loss
- Maximum portfolio drawdown
- Maximum leverage
- Maximum sector concentration
- Maximum correlated exposure
- Maximum open positions
- Maximum order size

### Execution Safety

The system must include:

- Emergency kill switch
- Order validation
- Duplicate order prevention
- Broker position reconciliation
- Connection monitoring
- Stale data detection
- Trading suspension after major errors
- Audit logs

No strategy or AI agent may bypass the risk management layer.

Paper trading should be the default mode.

Live trading must require an explicit configuration change and separate authorization.

---

## 12. Trading Execution System

Implement a broker-agnostic execution interface.

Initially support paper execution.

Potential future integrations include:

- Alpaca for equities
- Interactive Brokers for multiple asset classes
- A suitable futures broker for CME futures

Broker support should be implemented through adapters.

### Execution Responsibilities

- Receive trading signals.
- Determine allowable order sizes.
- Check risk constraints.
- Submit orders.
- Monitor order status.
- Reconcile fills.
- Track positions.
- Handle order rejections.
- Recover safely from connectivity failures.
- Produce detailed execution logs.

Research and execution should use the same strategy signal definitions while keeping broker-specific logic isolated.

---

## 13. Dashboard

Build a web dashboard using React, TypeScript, and a FastAPI backend.

### Main Views

**Overview**
- Portfolio equity
- Current drawdown
- Recent returns
- Active strategies
- Risk exposure

**Strategy Research**
- List of experiments
- Model comparisons
- Feature importance
- Strategy rankings
- Walk-forward results

**Backtesting**
- Equity curves
- Trade statistics
- Drawdown charts
- Benchmark comparisons
- Cost analysis

**Machine Learning**
- Training history
- Feature importance
- Prediction performance
- Model versions
- Model drift

**Trading**
- Paper/live mode
- Current positions
- Orders
- Fills
- Realized and unrealized P&L

**System Monitoring**
- Data provider health
- Strategy status
- Broker connectivity
- Errors and alerts

The dashboard should initially be read-only for trading operations.

---

## 14. Proposed Repository Structure

```text
quant-research-lab/
|
├── README.md
├── pyproject.toml
├── .env.example
├── configs/
│   ├── data.yaml
│   ├── research.yaml
│   ├── risk.yaml
│   └── strategies/
|
├── src/
│   └── quantlab/
│       ├── data/
│       │   ├── providers/
│       │   ├── ingestion/
│       │   ├── validation/
│       │   └── storage/
│       │
│       ├── features/
│       │   ├── price.py
│       │   ├── momentum.py
│       │   ├── volatility.py
│       │   ├── volume.py
│       │   └── technical.py
│       │
│       ├── ml/
│       │   ├── datasets.py
│       │   ├── training.py
│       │   ├── prediction.py
│       │   ├── evaluation.py
│       │   └── models/
│       │
│       ├── research/
│       │   ├── hypotheses.py
│       │   ├── experiments.py
│       │   ├── optimization.py
│       │   └── validation.py
│       │
│       ├── strategies/
│       │   ├── base.py
│       │   ├── momentum.py
│       │   ├── mean_reversion.py
│       │   └── ml_ranking.py
│       │
│       ├── backtesting/
│       │   ├── engine.py
│       │   ├── events.py
│       │   ├── orders.py
│       │   ├── fills.py
│       │   ├── portfolio.py
│       │   └── metrics.py
│       │
│       ├── risk/
│       │   ├── limits.py
│       │   ├── sizing.py
│       │   └── monitoring.py
│       │
│       ├── execution/
│       │   ├── broker.py
│       │   ├── paper.py
│       │   └── adapters/
│       │
│       └── api/
│           └── main.py
|
├── frontend/
│   ├── package.json
│   └── src/
|
├── experiments/
├── notebooks/
├── tests/
├── scripts/
├── data/
│   ├── raw/
│   ├── processed/
│   └── features/
|
└── docs/
    ├── architecture.md
    ├── data-design.md
    ├── ml-design.md
    ├── backtesting.md
    └── roadmap.md
```

---

## 15. Development Roadmap

### Milestone 1 — Project Foundation

Create:

- Python project with package management
- Standard repository structure
- Configuration management
- Logging
- Automated testing
- Historical data ingestion
- DuckDB/Parquet storage

Deliverable: Historical stock data can be downloaded, validated, stored, and queried reliably.

### Milestone 2 — Baseline Backtesting

Implement:

- Event-driven backtesting
- Orders and simulated fills
- Position and portfolio accounting
- Transaction costs
- Strategy interface
- Benchmark comparisons

Create simple momentum and mean-reversion strategies as initial examples.

Deliverable: Reproducible backtests with correct portfolio accounting and realistic execution timing.

### Milestone 3 — ML Research Engine

Implement:

- Feature generation
- Forward return labels
- Chronological dataset splitting
- Baseline regression models
- LightGBM and XGBoost
- Model evaluation
- ML-based stock ranking strategies

Deliverable: Compare ML-based stock selection against non-ML strategies on unseen historical periods.

### Milestone 4 — Automated Experimentation

Implement:

- Experiment configuration
- Optuna optimization
- MLflow tracking
- Walk-forward testing
- Parameter sensitivity analysis
- Automated performance reports

Deliverable: The platform can run and compare controlled strategy research experiments.

### Milestone 5 — Portfolio Optimization

Implement:

- Multi-strategy support
- Portfolio allocation
- Exposure constraints
- Volatility targeting
- Risk limits

Deliverable: Evaluate whether combining independently validated strategies improves risk-adjusted performance.

### Milestone 6 — Futures Research

Add:

- CME futures data
- Contract handling
- Intraday feature generation
- ES/MES backtesting
- VWAP and momentum strategies
- Futures-specific transaction cost modeling

Deliverable: Research intraday futures strategies with realistic contract and execution assumptions.

### Milestone 7 — Paper Trading

Implement:

- Live market data integration
- Signal scheduling
- Paper broker
- Order tracking
- Portfolio state persistence
- Risk monitoring
- Execution comparison

Deliverable: Strategies operate autonomously in paper mode with full logging.

### Milestone 8 — Dashboard and Monitoring

Build:

- React frontend
- FastAPI backend
- Research dashboard
- Backtesting visualizations
- ML monitoring
- Trading dashboard

Deliverable: A usable research and monitoring interface.

### Milestone 9 — AI Research Agent

Introduce an optional autonomous research assistant.

It should:

- Propose hypotheses.
- Generate features.
- Configure experiments.
- Execute sandboxed research jobs.
- Analyze results.
- Recommend further experiments.

It must not access live trading credentials or modify protected test data.

Deliverable: A controlled AI-assisted strategy research workflow.

### Milestone 10 — Controlled Live Trading

Only after sufficient out-of-sample validation, paper trading, and execution testing:

- Integrate a live broker.
- Enforce strict risk controls.
- Start with minimal capital.
- Monitor execution quality.
- Compare actual results against simulations.

Live trading must not be automatically enabled.

---

## 16. Long-Term Business Objective

The eventual goal is to build a quantitative trading operation capable of generating sustainable profits.

Priorities:

1. Find genuine statistical trading advantages.
2. Develop a repeatable and automated research process.
3. Minimize strategy overfitting.
4. Preserve trading capital.
5. Diversify across independent sources of return.
6. Automate execution and monitoring.
7. Increase capital allocation only when supported by credible live evidence.
8. Eventually evaluate whether trading income can safely replace employment income.

The system should prioritize surviving losing periods over maximizing short-term profits.

A good strategy is one that performs acceptably across many market conditions, not simply the one with the highest historical return.

---

## 17. Instructions for Codex

You are the lead software architect and quantitative developer for this project.

Your task is to help implement the Quant Research Lab incrementally.

Follow these development principles:

1. Prioritize correctness, reproducibility, and maintainability.
2. Develop modular components with clear interfaces.
3. Use typed Python wherever practical.
4. Include unit tests and integration tests.
5. Avoid unnecessary abstractions and premature optimization.
6. Keep research logic separate from broker execution.
7. Prevent look-ahead bias and data leakage.
8. Make experiments reproducible with fixed seeds and recorded configurations.
9. Clearly distinguish hypothetical backtest results from live performance.
10. Do not fabricate market data or claim that a strategy is profitable without evidence.
11. Use mock or synthetic data only for tests and explicitly identify it as such.
12. Build CPU-compatible versions before introducing GPU requirements.
13. Use C++ only where measured performance benefits justify it.
14. Do not add complex AI models before establishing baseline models.
15. Never enable live trading automatically.
16. Maintain documentation as the architecture evolves.
17. Work toward the long-term architecture while keeping each milestone runnable and testable.

### Immediate Task

**Begin implementing Milestone 1: Project Foundation.**

Specifically:

1. Initialize the repository and Python project.
2. Create the package structure.
3. Configure dependencies.
4. Implement configuration loading.
5. Implement structured logging.
6. Define a market-data provider interface.
7. Implement an initial historical equities provider.
8. Implement data validation.
9. Implement Parquet storage.
10. Implement DuckDB querying.
11. Create a command-line interface for downloading and inspecting historical stock data.
12. Create automated tests.
13. Write installation and usage instructions.

Make the initial implementation runnable without paid data subscriptions, using a supported free-data option or explicit test fixtures.

Do not attempt to implement all ten milestones simultaneously.

After completing Milestone 1, explain the implemented architecture, demonstrate how to run it, and identify the next development steps.