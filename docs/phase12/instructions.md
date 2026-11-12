# Quant Research Lab — Phase 12: Autonomous Quantitative Research & Strategy Discovery

The original 11 development milestones have been completed.

Quant Research Lab now has infrastructure for historical market data, quantitative features, machine learning, automated strategy discovery, statistical validation, portfolio construction, futures research, paper trading, a dashboard, an AI research agent, and controlled broker integration.

We are now transitioning from building the platform to using it for actual quantitative research.

## Primary Mission

Use the existing Quant Research Lab platform to systematically research, discover, evaluate, and refine quantitative trading strategies with the long-term objective of building a portfolio capable of generating sustainable income.

The eventual financial objective is to develop a trading operation that could replace a full-time software engineering salary.

However, do not assume any strategy will be profitable or that the system can reliably generate employment-replacement income.

**Your objective is to discover statistically credible, economically meaningful trading advantages that survive realistic execution assumptions, independent testing, and rigorous risk management.**

Do not prioritize attractive historical returns over research integrity.

---

## 1. Audit the Completed Platform

Before conducting research:

1. Inspect the entire repository.
2. Review all 11 completed milestones.
3. Run the existing test suite.
4. Verify historical data ingestion.
5. Verify market-data quality and coverage.
6. Verify feature calculations.
7. Verify ML training and inference.
8. Verify automated strategy discovery.
9. Verify statistical validation and holdout isolation.
10. Verify portfolio accounting and risk management.
11. Inspect paper-trading and broker integrations.
12. Review the AI research agent's capabilities and restrictions.

Identify components that are incomplete, unverified, or dependent on synthetic demonstrations.

Distinguish software implementation from actual empirical validation.

Do not assume a milestone's completion means its functionality has been verified using real market data.

Fix critical correctness issues before beginning large-scale research.

## 2. Establish the Research Baseline

Create a reproducible baseline research environment.

Record:

- Historical data providers.
- Dataset snapshot IDs.
- Data coverage.
- Available instruments.
- Corporate-action coverage.
- Futures contract histories.
- Known survivorship biases.
- Transaction cost assumptions.
- Available compute resources.
- Existing model configurations.
- Existing strategies.
- Historical experiment results.
- Validation status of each strategy.

Identify which datasets are sufficiently reliable for meaningful research.

Use only verified historical market observations for empirical strategy evaluation.

Synthetic datasets may be used for engineering tests, but not as evidence of profitability.

## 3. Define the Research Universe

Initially prioritize:

### US Equities

Research:

- Cross-sectional momentum.
- Short-term mean reversion.
- Sector-relative strength.
- Volatility-adjusted momentum.
- ML stock ranking.
- Regime-dependent stock selection.

### Equity Index Futures

Research:

- ES and MES.
- NQ and MNQ.
- Intraday mean reversion.
- Opening-range breakouts.
- Intraday trend following.
- Volume-based momentum.
- Volatility-regime strategies.

Treat each strategy family as a separate research program.

Do not automatically assume that futures offer better opportunities than equities or vice versa.

Evaluate opportunities based on net expected returns, scalability, drawdowns, execution constraints, and statistical robustness.

## 4. Autonomous Hypothesis Generation

Use the existing AI research agent to propose testable quantitative hypotheses.

Each hypothesis must contain:

- A unique hypothesis ID.
- Economic or behavioral rationale.
- Target market.
- Target instruments.
- Prediction horizon.
- Proposed features.
- Prediction target.
- Candidate models.
- Trading rules.
- Validation methodology.
- Transaction cost assumptions.
- Rejection criteria.
- Anticipated failure modes.

Prioritize hypotheses that have plausible economic explanations and can be tested using available data.

Do not generate arbitrary indicator combinations without a research rationale.

Avoid duplicating previously rejected hypotheses unless new evidence justifies reconsideration.

## 5. Machine Learning Research

Use the existing ML infrastructure to compare:

### Baseline Models

- Ridge regression.
- Logistic regression.
- Random Forest.

### Gradient Boosting

- LightGBM.
- XGBoost.

### Advanced Models

Consider:

- Neural networks.
- Temporal models.
- Transformers.
- Reinforcement learning.

Only investigate advanced models when simpler baselines provide evidence that additional modeling complexity may be useful.

Research prediction targets including:

- Forward returns.
- Benchmark-relative returns.
- Return rankings.
- Volatility.
- Market regimes.
- Breakout continuation probabilities.
- Mean-reversion probabilities.

Measure whether model predictions translate into economically meaningful trades after costs.

Do not optimize solely for prediction accuracy.

## 6. Automated Research Campaigns

Organize research into bounded campaigns.

Each campaign should specify:

- Research objective.
- Strategy family.
- Market.
- Dataset.
- Search space.
- Compute budget.
- Maximum experiments.
- Evaluation methodology.
- Validation windows.
- Statistical acceptance criteria.
- Required benchmark comparisons.

Use Optuna and MLflow for optimization and experiment tracking.

Record all tested configurations, including failures.

Apply multiple-testing controls.

Do not repeatedly optimize against previously reserved final holdout data.

The AI research agent may propose and execute experiments within authorized budgets.

It must not modify protected datasets, bypass validation, or access live brokerage credentials.

## 7. Strategy Evaluation

Evaluate every candidate using:

- Out-of-sample performance.
- Annualized return.
- Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Profit factor.
- Turnover.
- Trading frequency.
- Cost sensitivity.
- Statistical uncertainty.
- Parameter robustness.
- Performance stability.
- Benchmark-relative performance.
- Capacity and liquidity constraints.

Reject strategies that depend on:

- Look-ahead bias.
- Survivorship bias.
- Incomplete corporate-action handling.
- Unrealistic fills.
- Excessive leverage.
- Unreasonably low transaction costs.
- Unstable parameters.
- A handful of unusually profitable trades.
- Repeated tuning against the same validation data.

Do not approve a strategy based solely on a high Sharpe ratio or attractive equity curve.

## 8. Independent Statistical Validation

Use the existing statistical validation framework.

Require:

- Chronological testing.
- Purged validation where needed.
- Multiple walk-forward windows.
- Multiple-testing adjustments.
- Appropriate bootstrap uncertainty estimates.
- Transaction cost stress tests.
- Parameter sensitivity analysis.
- Market regime analysis.

Preserve an untouched final test period until a candidate is frozen and independently authorized for evaluation.

Do not allow the AI research agent to inspect final holdout results during iterative strategy development.

If all candidates fail, report that no statistically credible strategy has been found.

Do not weaken acceptance criteria simply to produce a winning strategy.

## 9. Strategy Selection

Create a candidate registry with statuses:

- RESEARCH
- REJECTED
- INSUFFICIENT_EVIDENCE
- FURTHER_VALIDATION_REQUIRED
- APPROVED_FOR_PAPER
- PAPER_RUNNING
- PAPER_FAILED
- LIVE_REVIEW_REQUIRED

Only promote strategies according to the existing eligibility framework.

Promotion must be justified by reproducible evidence.

No research agent may authorize live trading.

## 10. Portfolio Construction

For candidates that pass independent validation:

1. Analyze strategy return correlations.
2. Evaluate overlapping market exposures.
3. Construct equal-weight and risk-weighted portfolios.
4. Compare standalone and combined performance.
5. Apply portfolio-wide exposure limits.
6. Evaluate drawdown behavior.
7. Stress-test simultaneous strategy losses.
8. Analyze turnover and transaction costs.
9. Evaluate liquidity and capital requirements.

Allow capital to remain unallocated when opportunities are insufficient.

Do not force portfolio diversification using strategies that failed validation.

## 11. Paper Trading Campaign

Deploy eligible strategies to the existing paper-trading infrastructure only after explicit approval.

Track:

- Real market-data reception.
- Signal generation.
- ML inference.
- Simulated execution.
- Portfolio accounting.
- Transaction costs.
- Prediction drift.
- Risk breaches.
- System reliability.
- Differences between backtest and paper results.

Paper trading must use clearly identified real-time or delayed market data.

Historical replay must not be presented as live paper-trading evidence.

Collect sufficient observations before drawing conclusions.

Do not assume a few profitable weeks establish a sustainable trading strategy.

## 12. Research Reporting

Generate comprehensive reports for every completed campaign.

Include:

- Research objective.
- Hypotheses tested.
- Number of experiments.
- Dataset versions.
- Model comparisons.
- Selected features.
- Out-of-sample results.
- Statistical validation.
- Trading costs.
- Drawdowns.
- Benchmark comparisons.
- Rejected strategies.
- Surviving candidates.
- Known limitations.
- Recommended future experiments.

Reports must distinguish observed results from AI-generated interpretations.

Never fabricate research outcomes.

## 13. Capital and Income Feasibility

Evaluate whether validated strategies could plausibly support a full-time trading operation.

Analyze:

- Risk-adjusted return.
- Historical drawdowns.
- Estimated return uncertainty.
- Required trading capital.
- Capacity constraints.
- Potential annual withdrawals.
- Tax considerations.
- Operating expenses.
- Data subscriptions.
- Brokerage fees.
- Infrastructure costs.
- Emergency reserves.

Use realistic and conservative assumptions.

Evaluate multiple capital scenarios.

Do not assume a stable monthly income or constant annual returns.

Do not recommend leaving full-time employment solely on the basis of historical backtests or short-term paper results.

## 14. Autonomous Research Operation

Configure the AI research agent to operate through bounded research cycles.

Each cycle should:

1. Review previous research.
2. Select a research objective.
3. Generate hypotheses.
4. Design experiments.
5. Run permitted experiments.
6. Analyze results.
7. Apply statistical validation.
8. Reject weak candidates.
9. Record findings.
10. Recommend the next research cycle.

Enforce:

- Experiment count limits.
- Runtime limits.
- Compute budgets.
- API cost limits.
- Memory limits.
- Dataset access controls.
- Holdout isolation.
- Human review checkpoints.

Do not implement unrestricted research loops.

Do not allow the agent to execute real-money trades.

## 15. Initial Research Campaign

Begin with a controlled comparison of ML-based US equity strategies.

Research question:

**Can machine learning identify liquid US stocks with higher expected five-day risk-adjusted returns than simple momentum, mean-reversion, or benchmark strategies after realistic transaction costs?**

Initial research approach:

1. Inspect available verified equity snapshots.
2. Select a sufficiently broad, point-in-time historical universe where supported.
3. Create multiple feature families.
4. Establish simple non-ML baselines.
5. Train Ridge, Random Forest, LightGBM, and XGBoost models.
6. Compare regression and ranking approaches.
7. Run chronological walk-forward evaluations.
8. Construct executable portfolios.
9. Apply realistic costs.
10. Evaluate statistical uncertainty.
11. Rank candidates using predefined criteria.
12. Generate a comprehensive research report.

Use a bounded initial experiment budget.

Do not consume the reserved final holdout.

If the existing datasets are insufficient, report the specific data requirements before claiming empirical results.

## 16. Immediate Deliverables

Produce:

1. A platform readiness report.
2. A data quality and coverage report.
3. An existing strategy inventory.
4. A prioritized research backlog.
5. A reproducible initial research campaign configuration.
6. Actual initial campaign results, if the available data supports meaningful research.
7. A statistical validation report.
8. A list of rejected and surviving candidates.
9. Recommendations for the next experiments.

Do not start live trading.

Do not automatically promote strategies to paper trading.

After completing the initial research campaign, summarize the results and wait for authorization before expanding the campaign or deploying candidates.

## Final Directive

We are no longer primarily building software features.

We are using Quant Research Lab to conduct rigorous quantitative research.

Your responsibility is to help discover and evaluate potential trading advantages using statistical methods, machine learning, and automated experimentation.

A successful research campaign may conclude that no profitable strategy has been found.

Prioritize scientific validity, reproducibility, realistic execution, and capital preservation.

**Begin by auditing the completed platform and running the initial equity ML research campaign.**