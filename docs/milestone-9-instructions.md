# Quant Research Lab — Milestone 9: Dashboard & Visualization

Milestones 1–8 have been implemented. Continue developing the existing Quant Research Lab repository according to the original blueprint and updated development roadmap.

Do not restart the project, unnecessarily rewrite existing components, or break previously completed functionality.

## Primary Objective

Build a professional, comprehensive web dashboard for Quant Research Lab.

The dashboard should provide a centralized interface for quantitative strategy research, machine learning experiments, automated strategy discovery, backtesting, portfolio analytics, paper trading, and system monitoring.

The application should resemble a modern quantitative research and trading terminal, emphasizing information density, clarity, and usability.

Use React, TypeScript, Vite, and FastAPI unless the existing codebase already contains a compatible technology stack that should be preserved.

## 1. Audit Existing Infrastructure

Before implementation:

1. Inspect the entire repository.
2. Review all completed milestones.
3. Run the existing test suite.
4. Identify existing APIs, data models, experiment stores, strategy interfaces, and account databases.
5. Review existing MLflow and Optuna integrations.
6. Inspect backtesting, portfolio, and paper-trading functionality.
7. Determine which operations can be exposed safely through an API.
8. Preserve existing CLI workflows.

Document the proposed frontend and backend architecture before implementation.

## 2. Frontend Architecture

Create a modular React application using:

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- Plotly or another suitable charting library
- A consistent component library
- Responsive layouts
- Dark mode by default

Follow the existing repository conventions.

Use reusable components and strong TypeScript types.

Create a clear separation between API clients, application state, reusable components, and individual pages.

## 3. Backend API

Extend the existing FastAPI infrastructure.

Implement REST endpoints for:

- Dataset snapshots.
- Research experiments.
- ML models.
- Strategy discovery studies.
- Statistical validation reports.
- Backtesting results.
- Portfolio configurations.
- Portfolio performance.
- Paper-trading accounts.
- Orders and fills.
- Risk status.
- System health.

Use WebSockets or server-sent events for appropriate live updates.

Requirements:

- Typed request and response schemas.
- Input validation.
- Pagination.
- Filtering.
- Sorting.
- Structured error responses.
- API versioning.
- Secure configuration handling.
- Read-only access by default.

Long-running research jobs must execute outside HTTP request handlers through a controlled job system.

Do not expose arbitrary shell execution, unrestricted code execution, or direct live trading through dashboard endpoints.

## 4. Main Dashboard

Create an overview page showing:

- Total portfolio equity.
- Daily and cumulative P&L.
- Current drawdown.
- Portfolio exposure.
- Active strategies.
- Paper-trading account status.
- ML model status.
- Recent research experiments.
- Latest strategy validation results.
- Risk warnings.
- Data provider connectivity.

Clearly distinguish paper trading, backtesting, and live trading data.

Never combine simulated and actual returns into one unlabeled performance metric.

## 5. Strategy Research Dashboard

Create a research interface supporting:

- Experiment browsing.
- Search and filtering.
- Strategy comparison.
- Feature inspection.
- Research hypothesis details.
- Dataset versions.
- Experiment parameters.
- Model configurations.
- Backtesting results.
- Statistical validation results.
- Research status.

Display both successful and failed experiments.

Provide side-by-side strategy comparisons.

Include clear warnings when strategies fail validation.

## 6. Machine Learning Dashboard

Implement model analytics showing:

- Available models.
- Model versions.
- Training history.
- Prediction targets.
- Feature importance.
- Prediction accuracy.
- Rank information coefficient.
- Walk-forward performance.
- Training and validation windows.
- Prediction distribution.
- Feature drift.
- Model degradation indicators.

Make it possible to compare multiple models against simpler statistical baselines.

Do not present model accuracy alone as proof of trading profitability.

## 7. Automated Strategy Discovery

Create an interface for inspecting Optuna and MLflow research experiments.

Display:

- Study configurations.
- Trial histories.
- Hyperparameter comparisons.
- Search-space definitions.
- Optimization progress.
- Candidate strategy rankings.
- Rejected strategies.
- Rejection reasons.
- Robustness analysis.
- Multiple-testing warnings.
- Research reports.

Support launching approved, bounded research jobs through validated configurations.

Do not permit research jobs to bypass holdout data protections.

## 8. Backtesting Dashboard

Create a backtesting analytics page.

Display:

- Equity curves.
- Benchmark comparisons.
- Drawdown charts.
- Monthly returns.
- Trade distributions.
- Performance by market regime.
- Long versus short performance.
- Transaction cost breakdown.
- Turnover.
- Exposure.
- Strategy configuration.

Allow comparisons between different backtest runs.

Clearly label:

- In-sample results.
- Validation results.
- Final holdout results.
- Synthetic demonstrations.

## 9. Portfolio Dashboard

Display:

- Portfolio allocations.
- Strategy weights.
- Individual strategy performance.
- Portfolio performance.
- Correlation matrices.
- Risk contributions.
- Gross and net exposure.
- Sector exposure.
- Margin utilization.
- Drawdown.
- Portfolio volatility.
- Rebalancing history.
- Risk-limit breaches.

Support inspecting historical portfolio states.

Do not permit portfolio configuration changes that bypass risk validation.

## 10. Paper Trading Dashboard

Create a dedicated paper-trading interface.

Display:

- Virtual account equity.
- Available buying power.
- Open positions.
- Open orders.
- Recent fills.
- Realized P&L.
- Unrealized P&L.
- Strategy allocations.
- Paper execution costs.
- Market-data status.
- Model prediction logs.
- Trading activity history.

Support authenticated, authorized paper-only actions:

- Start approved paper strategies.
- Pause paper strategies.
- Stop paper strategies.
- Activate the paper-trading kill switch.

Require confirmation for actions that materially change simulated account state.

Do not implement live brokerage trading controls in this milestone.

## 11. System Monitoring

Create a system health page displaying:

- Market-data provider status.
- Data freshness.
- Active research jobs.
- Paper execution status.
- Strategy health.
- Model inference latency.
- Error logs.
- Recovery events.
- Storage health.
- Risk alerts.

Show when data is delayed, stale, replayed, or unavailable.

Do not display a healthy system status based solely on a running process.

## 12. User Experience

Requirements:

- Professional dark theme.
- Responsive navigation.
- Reusable chart components.
- Consistent typography.
- Searchable data tables.
- Loading and error states.
- Empty-state handling.
- Clear simulated-versus-live labels.
- Exportable research reports.
- CSV export where appropriate.
- Accessible keyboard navigation.

Prioritize functionality and clarity over decorative visual effects.

## 13. Security

Implement appropriate protections for local and potentially remote deployment:

- Authentication for nonlocal access.
- Authorization for state-changing operations.
- CORS restrictions.
- Secret management.
- API input validation.
- Protection against command injection.
- Protection against path traversal.
- Audit logging.
- Safe handling of uploaded configuration files.

Never expose broker credentials or API keys to the frontend.

Do not expose the development API publicly without authentication.

## 14. Testing

Add tests for:

- API schemas.
- Data serialization.
- Pagination and filtering.
- Permission checks.
- Research job submission.
- Experiment retrieval.
- Paper strategy controls.
- Portfolio data correctness.
- Dashboard rendering.
- Error handling.
- Live update behavior.
- Security boundaries.

Use mocked API responses for frontend unit tests.

Use actual application databases and research artifacts for integration tests when available.

## 15. End-to-End Demonstration

Create a working demonstration that:

1. Starts the FastAPI backend.
2. Starts the React frontend.
3. Loads existing research experiments.
4. Displays ML model performance.
5. Displays strategy rankings.
6. Displays backtest results.
7. Displays portfolio analytics.
8. Displays paper-trading account state.
9. Demonstrates monitoring and error reporting.

Clearly label demo fixtures if real artifacts are unavailable.

Provide commands to start the frontend and backend.

## 16. Documentation

Document:

- Frontend architecture.
- Backend API.
- Authentication.
- Configuration.
- Development setup.
- Production build.
- Local deployment.
- Data models.
- Known limitations.

Update the main roadmap.

## 17. Completion Criteria

Milestone 9 is complete when:

- The web application runs.
- The API exposes existing research data.
- Experiments and models can be inspected.
- Backtesting and portfolio visualizations work.
- Paper-trading activity can be monitored.
- Authorized paper controls function.
- System health is visible.
- Tests pass.
- A complete demonstration runs successfully.

After completion, summarize the implementation, test results, startup commands, and limitations.

Do not automatically begin Milestone 10.

Begin implementing Milestone 9 using the existing repository.