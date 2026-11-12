# Quant Research Lab — Milestone 11: Controlled Live Trading & Production Deployment

Milestones 1–10 have been implemented. Continue developing the existing Quant Research Lab repository according to the original blueprint and updated roadmap.

Do not restart the project or unnecessarily rewrite existing functionality.

## Primary Objective

Build secure, reliable, production-oriented trading infrastructure capable of supporting controlled real-money execution after independent verification and explicit human authorization.

The system should integrate with supported broker APIs, execute approved strategies, enforce portfolio-wide risk limits, reconcile account state, recover from failures, and provide comprehensive operational monitoring.

**Live trading must remain disabled throughout implementation and testing.**

Completing this milestone does not automatically authorize real-money trading.

## 1. Audit Existing Infrastructure

Review all previous milestones, including:

- Data ingestion.
- Feature engineering.
- ML models.
- Automated strategy discovery.
- Statistical validation.
- Portfolio optimization.
- Futures infrastructure.
- Paper trading.
- Dashboard.
- AI research agent.
- Security controls.

Run existing tests and document relevant limitations.

Identify dependencies required for reliable brokerage integration.

## 2. Broker Integration Architecture

Implement a broker-independent execution interface.

Potential adapters include:

- Alpaca for equities.
- Interactive Brokers for supported instruments.
- An appropriate futures broker API.

Use official, documented interfaces.

Broker adapters should support:

- Authentication.
- Account information.
- Positions.
- Orders.
- Order status.
- Order cancellation.
- Execution reports.
- Buying power.
- Margin information.
- Market-data references where available.

Implement one broker adapter completely before expanding to additional brokers.

Use the broker's sandbox or paper environment during development.

## 3. Execution Modes

Support explicitly separated modes:

- BACKTEST
- PAPER
- BROKER_SANDBOX
- LIVE

Requirements:

- LIVE must be disabled by default.
- LIVE requires separate configuration and authorization.
- Paper and live credentials must be isolated.
- Configuration must not silently fall back from paper to live.
- An API failure must never change execution modes automatically.
- The AI research agent must not be permitted to enable LIVE.

Use explicit capability checks before allowing any broker operation.

## 4. Order Management System

Implement a reliable order management system supporting:

- Market orders.
- Limit orders.
- Stop orders.
- Stop-limit orders where supported.
- Order cancellation.
- Order replacement.
- Partial fills.
- Rejected orders.
- Expired orders.
- Time-in-force rules.
- Order status reconciliation.
- Duplicate submission prevention.

Maintain an authoritative order state machine.

Use persistent client order identifiers and idempotency protections where supported.

Do not blindly retry an order after an uncertain broker response.

## 5. Pre-Trade Risk Management

Every proposed order must pass through the existing portfolio risk engine.

Checks should include:

- Allowed strategy.
- Allowed instrument.
- Available cash.
- Buying power.
- Margin requirements.
- Maximum position size.
- Maximum contract count.
- Maximum order notional value.
- Maximum leverage.
- Maximum daily loss.
- Maximum portfolio drawdown.
- Maximum correlated exposure.
- Market session eligibility.
- Data freshness.
- Order price validity.

The broker's own limits are additional constraints, not substitutes for application-level risk controls.

## 6. Broker Reconciliation

Implement recurring reconciliation of:

- Account balances.
- Positions.
- Open orders.
- Executions.
- Fees.
- Buying power.
- Margin utilization.

Reconcile broker state against internal state.

If material discrepancies are detected:

- Suspend new trading.
- Record the discrepancy.
- Alert the operator.
- Require safe reconciliation before resuming.

Never assume a missing API response means an order was rejected.

## 7. Failure Recovery

Implement safeguards for:

- Network disconnections.
- Broker API outages.
- Duplicate callbacks.
- Partial fills.
- Stale market data.
- Process crashes.
- Application restarts.
- Order status uncertainty.
- Unexpected position changes.
- Database failures.

On restart, reconcile actual broker state before enabling new orders.

Fail closed when essential risk or account state is uncertain.

## 8. Production Risk Controls

Implement:

- Global kill switch.
- Strategy-specific suspension.
- Maximum daily loss.
- Maximum drawdown.
- Maximum account exposure.
- Maximum leverage.
- Maximum contract exposure.
- Order rate limits.
- Maximum single-order value.
- Maximum position concentration.
- Data freshness restrictions.
- Emergency stop procedures.

A kill switch must stop new order submission immediately.

Clearly distinguish stopping new orders from cancelling open orders or liquidating positions.

Do not automatically liquidate all positions without a separately defined and tested emergency liquidation policy.

## 9. Security

Protect brokerage credentials and trading infrastructure.

Requirements:

- Environment-based secret configuration.
- Secret encryption or a managed secret store where appropriate.
- No credentials committed to Git.
- No secrets exposed to frontend clients.
- Credential rotation support.
- Restricted network permissions.
- Authentication.
- Role-based authorization where appropriate.
- Audit logging.
- Safe deployment configuration.

AI research tools and generated code must not access live broker credentials.

## 10. Strategy Deployment

Implement a controlled deployment workflow:

1. Strategy passes research validation.
2. Strategy is explicitly approved for paper trading.
3. Strategy demonstrates acceptable paper performance and operational stability.
4. Strategy undergoes independent review.
5. Live eligibility is explicitly approved.
6. Trading configuration and risk limits are reviewed.
7. Deployment receives separate human authorization.
8. Broker state and connectivity are verified.
9. Trading may begin only after all gates pass.

No automated strategy discovery process may directly deploy a newly discovered strategy into live trading.

## 11. Model Monitoring

Track deployed ML models.

Monitor:

- Feature drift.
- Prediction drift.
- Model version.
- Prediction latency.
- Live versus expected performance.
- Strategy return degradation.
- Execution slippage.
- Data quality.

Support controlled model rollback.

Do not automatically replace a live model based solely on short-term performance.

## 12. Operational Monitoring

Implement monitoring and alerts for:

- Broker connectivity.
- Open orders.
- Positions.
- Account balances.
- Risk breaches.
- Failed orders.
- Unexpected fills.
- Data-feed failures.
- Application crashes.
- Database health.
- Model failures.
- Strategy suspension.

Ensure critical alerts are visible through the dashboard and logs.

## 13. Dashboard Integration

Extend the dashboard with a clearly separated live-trading monitoring view.

Display:

- Broker account status.
- Execution mode.
- Current positions.
- Open orders.
- Recent fills.
- Account equity.
- Risk utilization.
- Active strategies.
- Model versions.
- System alerts.

During this milestone, keep live-trading controls disabled.

Read-only live-account monitoring may be implemented where supported and explicitly authorized.

Do not expose an unrestricted order-entry interface.

## 14. Production Deployment

Create a production-oriented deployment configuration.

Support:

- Docker Compose or another suitable deployment system.
- Service restart policies.
- Persistent storage.
- Structured logs.
- Health checks.
- Environment separation.
- Configuration validation.
- Backup and recovery.
- Dependency version pinning.
- Safe shutdown.
- Monitoring.

Do not require expensive cloud infrastructure for the initial deployment.

The platform should be capable of running on a single reliable machine.

## 15. Testing

Implement comprehensive tests covering:

- Broker API adapters.
- Authentication failures.
- Order validation.
- Order state transitions.
- Duplicate order prevention.
- Partial fills.
- Order cancellation.
- Reconciliation.
- Risk-limit enforcement.
- Kill-switch behavior.
- Connection failures.
- Broker outages.
- Crash recovery.
- Persistent state restoration.
- Unauthorized execution attempts.
- AI agent isolation.
- Configuration safety.

Use mocked brokers and official sandbox environments.

Do not place real-money orders during testing.

## 16. End-to-End Demonstration

Demonstrate the complete execution pipeline using a broker sandbox or paper account.

The demonstration should:

1. Load an explicitly approved test strategy.
2. Connect to a sandbox broker.
3. Retrieve account state.
4. Receive market observations.
5. Generate trading signals.
6. Apply risk controls.
7. Submit sandbox orders.
8. Process execution reports.
9. Update positions and account balances.
10. Reconcile broker and internal state.
11. Simulate a connection failure.
12. Recover safely.
13. Trigger and verify a kill switch.
14. Produce an execution audit report.

If sandbox credentials or network access are unavailable, use a mock broker and clearly document that external broker integration is unverified.

Do not submit real-money orders.

## 17. Independent Go-Live Checklist

Create a formal checklist covering:

- Statistical validation.
- Final holdout evaluation authorization and results.
- Historical data quality.
- Paper trading evidence.
- Broker integration.
- Risk limits.
- Order sizing.
- Account reconciliation.
- Crash recovery.
- Operational monitoring.
- Strategy eligibility.
- Capital allocation.
- Regulatory and tax considerations.
- Operator readiness.

A completed checklist does not guarantee profitability.

The platform must remain in paper or sandbox mode until a separate future authorization process is explicitly completed.

## 18. Documentation

Update:

- Broker architecture.
- Order management.
- Reconciliation.
- Risk management.
- Security.
- Deployment.
- Monitoring.
- Incident response.
- Model rollback.
- Go-live procedures.
- Known limitations.

## 19. Completion Criteria

Milestone 11 is complete when:

- At least one broker adapter works in sandbox or paper mode.
- Order processing is reliable.
- Risk checks are enforced.
- Broker reconciliation works.
- Failure recovery is tested.
- Security protections are implemented.
- Monitoring and alerting function.
- Live execution remains disabled.
- Automated tests pass.
- End-to-end sandbox demonstrations succeed where external access permits.
- A formal go-live checklist exists.

After completion:

1. Summarize the implemented system.
2. Report all test results.
3. Report broker connectivity and sandbox verification.
4. Identify unresolved production risks.
5. Identify which strategies, if any, meet research and paper-trading eligibility requirements.
6. Confirm that real-money execution remains disabled.
7. Provide the operator with a detailed go-live readiness report.

**Do not enable live trading or execute real-money orders.**

Begin implementing Milestone 11 using the existing repository.