# Controlled broker sandbox architecture

The [full Milestone 11 request](milestone-11-instructions.md) is saved. This
milestone implements execution engineering, not permission to trade real money.
**LIVE is disabled in this build. No environment variable or checklist enables it.**

## Modes and broker interface

BACKTEST uses the existing research/backtesting engines; PAPER uses the isolated
local virtual account; BROKER_SANDBOX uses an explicitly selected test broker.
LIVE is an enum value that the broker authority always rejects. Failures never
change modes. The only external execution adapter is **Alpaca PAPER**, using its
official v2 REST API at `https://paper-api.alpaca.markets`:

- `GET /v2/account`, `/v2/positions`, `/v2/orders?status=open`.
- `GET /v2/orders:by_client_order_id` for uncertain submissions.
- `GET /v2/account/activities`, with bounded pagination.
- `POST /v2/orders`, `DELETE /v2/orders/{id}`, `PATCH /v2/orders/{id}`.

Reference: [Alpaca Trading API](https://docs.alpaca.markets/reference/getaccount-1).
No live broker hostname, redirect following, paper-to-live fallback or unrestricted
order-entry API exists. Futures execution is unavailable; ES/MES/NQ/MNQ contracts
are rejected by this equity broker adapter. Futures research/accounting remains
supported separately. External Alpaca account/routing behavior remains unverified
in this environment; injected HTTP contracts and the explicit mock broker are tested.

## Authority and deployment

Broker operations require an HMAC capability bound to operation, exact payload,
account, mode and expiry. The controller creates it only after a durable intent
and risk checks. The private authorization key belongs only to the broker process.
Sandbox strategy approval is signed and bound to exact strategy definition/version,
model pin, package source SHA, risk settings, account, allowed instruments and expiry.
Human approvals require an operator identity/reason; CLI expiry is limited to 1–60
minutes. A simulated fixture approval is accepted only by the mock broker.

SANDBOX_TEST approval is deliberately separate from statistical VALIDATED status,
approved real-time paper deployment and live eligibility. It permits engineering
tests, never promotion of a rejected strategy. The platform currently has **zero
research/paper/live-qualified strategies**. No live approval/deployment was created.
A future production strategy needs research qualification, explicit paper approval,
credible paper operational evidence, independent review, live-eligibility review,
risk/capital review, separate human deployment authorization and broker verification.
The AI agent cannot grant any of these permissions.

## OMS, risk and reconciliation

The authoritative M8 order state machine is reused. Market, limit, stop, stop-limit,
DAY/GTC, partial fills, rejection, expiry and cancellation are represented. Client
IDs persist before any network submission. Reusing an ID with a changed intent is
rejected. Missing/malformed acknowledgements or uncertain responses leave a durable
pending intent and suspend new submissions. An uncertain order is **never blindly
retried**. Reconciliation queries the stable client ID. Missing responses do not
mean rejected orders. Broker replacement is supported by the adapter; the controller
uses confirmed cancel/reconcile/new intent, explicitly losing priority.

All proposals pass shared M6/M8 portfolio checks: allowed strategy/instrument,
cash and outstanding-order reservations, broker buying power, position/order size,
gross/net/leverage/correlated exposure, per-strategy drawdown, daily loss, portfolio
drawdown, order rate, tick validity, market session, quote freshness and recent
broker reconciliation. Cash-only whole-share equities are the initial scope;
futures margin/contract accounting remains in M7/M8 rather than being misrouted.
Unknown correlations conservatively share one risk group. Broker limits are
additional constraints. Market/stop gaps can exceed estimated execution prices;
these checks do not guarantee a fill price or real profitability.

Reconciliation compares exact positions, cash to a cent, open orders, known order
states and deduplicated execution activities. Broker NAV uses a disclosed mark-time
tolerance of max($5, 0.01% baseline capital), separate from cash reconciliation.
Unexpected orders/fills/positions, missing executions, mismatched order intent,
unknown activities, incomplete pagination or balance differences suspend trading
and emit local structured alerts. Known executions are processed once. Late unseen
fills require reviewed reconstruction rather than silently rewriting history.

The journal is SQLite WAL/FULL with atomic materialized state/checksums and a
single-writer lock. Existing equity accounting reconstructs cash, realized/unrealized
P&L, fees and positions. Startup always suspends; broker state and a new observation
must reconcile before explicit arming. Restoring state never re-funds the account
or resubmits old signals. A clean positive-cash sandbox account is required for the
initial baseline; existing unexplained holdings/orders are not silently imported.

Fee coverage is not certified: explicit broker activity fees are recorded where
present; absent fee fields are labeled unverified. Cash discrepancies halt.
Non-fill fees, deposits, dividends and corporate actions currently require reviewed
processors/reconciliation rather than fabricated records. Open orders are bounded
at 500 provider rows (100 application pending orders); activities at 100 pages of
100. Coverage exhaustion halts. Long-running external paging/fee behavior is not
empirically verified. This is not a fully certified production account ledger.

## Kill, recovery and models

Kill immediately persists a local new-order block. Optional cancellation is a
separate explicit request and is not confirmed until broker reconciliation.
**Positions are retained; no emergency liquidation policy is enabled.** Queued
CLI controls report queued, not applied; the service must journal acknowledgement.
A separate signed operator reset requires reconciled state and leaves strategies
paused. Strategy-specific suspension, model pinning, feature-drift/latency hooks and
separately authorized rollback are implemented. Rollback clears deployment approval
and never auto-restarts/replaces a model. No real deployed ML model or live drift
record currently exists; monitoring hooks are engineering-tested only.

[Incident response](incident-response.md) distinguishes a new-order block,
cancellation and liquidation. [Production operation](production.md) covers
credentials, startup and backups. The [go-live checklist](go-live-readiness.md)
remains blocked and cannot activate LIVE.

## Commands

```bash
# No external account: explicitly MOCK broker and synthetic engineering quotes.
uv run --frozen --all-extras quantlab execution sandbox-demo --output data/execution/NEW_RUN
uv run --frozen --all-extras quantlab execution readiness --output docs/go-live-readiness.json
uv run --frozen --all-extras quantlab execution inspect --database data/execution/NEW_RUN/oms.sqlite
uv run --frozen --all-extras quantlab execution backup --database data/execution/NEW_RUN/oms.sqlite --output data/execution/NEW_BACKUP.sqlite
```

The real PAPER service uses `configs/execution.sandbox.example.yaml` only after
operator review, separate PAPER/data credentials, exact account ID and a current
signed sandbox approval. Default service behavior is monitoring. The explicit
`--arm-approved-sandbox-test` flag permits one bounded test submission on a newly
initialized account. A restarted account needs an additional explicit
`--resume-reconciled-sandbox-test --resume-reason ...`; never put that resume flag
in a restart policy. The Compose sandbox profile starts unarmed.
