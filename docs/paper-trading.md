# Simulated execution and real-time data boundaries

The [full Milestone 8 request](milestone-8-instructions.md) is preserved. The
existing equity Portfolio and futures FuturesLedger remain the accounting
components. There is one funded master: the equity component receives the initial
capital and the futures component begins explicitly unfunded. Combined NAV/cash,
not either component's standalone buying power, govern all decisions. Any cash
transfer is zero-sum and included in both component accounting identities.

## Events and transports

MarketEvent carries instrument, provider, aware UTC observation/receive timestamps,
explicit replay/realtime/delayed mode, quote/trade/heartbeat type, sequence,
bid/ask and sizes, price/volume, session and liquidity basis. Unknown instruments,
invalid timestamps, crossed quotes, invalid volume and future observations fail
validation. Receive time cannot precede observation time. Duplicate market
identity excludes transport receive time. Sequence collisions and session gaps
suspend execution. Out-of-order observations are recorded without updating the
observable price history. Replay uses an explicit historical clock.

Alpaca official REST latest/historical quote endpoints and quote WebSockets support
US stocks/ETFs. `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` stay in the environment.
IEX is limited-venue data; SIP requires the appropriate subscription; delayed SIP
is labeled delayed. Alpaca quote sizes are round lots, normalized to shares.
Actual entitlements, rate limits and permitted use depend on the account/provider
agreement. 429 responses honor a bounded Retry-After delay. Reconnect failures
suspend, never change provider/mode or automatically resume a strategy. Historical
quote recovery is bounded and returned as replay data; it cannot generate
retrospective live fills. An authorized licensed-client boundary supports actual
ES/MES/NQ/MNQ contract quotes. External futures streaming transport deployment is
not verified; no implicit direct-TCP network workaround is attempted.

**No external streaming connectivity is verified in this environment.** No feed
credentials/subscriptions are configured and the runtime allowlist excludes
Alpaca. The actual historical LEAN snapshots are not real-time feeds. Inherited
proxy configuration and TLS certificate verification remain enabled.

## Orders and observable fills

States are CREATED, PENDING, ACCEPTED, PARTIALLY_FILLED, FILLED, CANCELLED,
REJECTED and EXPIRED with explicit transition validation. Market, limit, stop and
stop-limit intents use stable client IDs; changed intent with an existing ID is
rejected. Replacement is cancel/new and explicitly loses priority. Day orders
expire on session change; GTC persists. No real brokerage submission exists.

Only a later quote, strictly beyond configured latency, can fill an order. Market
buys use ask plus adverse ticks; sells use bid minus adverse ticks. Limits must
still hold after slippage. Stop trigger and fill require separate observations,
so gaps can execute beyond the trigger. Displayed liquidity is capped by a
participation fraction and shared across pending orders in insertion order.
Displayed quotes are not guaranteed executable. Trade-only events update marks
but do not fabricate a spread or fills. With historical minute-closing quotes,
the replay uses the completed minute's availability timestamp and explicitly
modeled 1% traded-volume depth followed by 10% participation. This is a bar-volume
liquidity proxy, not measured quote depth or an intrabar execution claim.

## Risk and deployment

Shared Milestone 6 bound checking enforces maximum gross/net/leverage, position,
correlated exposure, per-strategy exposure/drawdown, daily loss, portfolio
 drawdown, order units/notional/rate and futures contract count/margin. Unknown
correlations conservatively put every instrument in one group. Pending buys,
sells, fees and margin reserve worst-case exposure/cash; opposite pending intents
do not create buying power. Risk runs before acceptance and before execution.
Equity shorts and cash borrowing are unavailable. Futures use signed whole
contracts and actual multipliers/ticks, notional is not debited from cash.

Kill stops new orders and cancels pending orders; positions remain. There is no
automatic emergency liquidation. Pauses, disconnects and restarts suspend
execution. Restart requires accounting reconstruction, a new valid observation,
connection acknowledgement and explicit strategy resume. Resume does not clear a
kill switch. Unknown state or database errors fail closed.

Research strategies remain RESEARCH and are permitted only in historical replay.
Trusted operator registration of a deployment requires VALIDATED evidence,
explicit approval and a reason. YAML and discovery results cannot self-promote a
strategy. Deployment/model versions and hashes are persisted. Current candidates
are rejected; **zero strategies qualify for validated paper deployment**.

## Persistence, inference and monitoring

SQLite WAL, synchronous FULL and a single-writer lock protect the local account.
Each command/event atomically commits the journal and materialized state. Startup
verifies SQLite integrity, contiguous hash chaining, last-state checksum and
rebuilds the financial ledgers from fills. Failed transactions restore in-memory
state. Checksums detect accidental corruption, not a malicious administrator with
write access to the database. Back up the database using SQLite's backup API,
not an uncoordinated copy of its main file while WAL writes are active.

Multiple strategies share the master account; per-strategy cashflow/marked-PnL
attribution is separate from master funding. QuoteMomentum provides bounded
past-only quote-event return/spread features. Its schema is deliberately distinct
from historical OHLCV features. Trusted ResearchModel artifacts preserve
train-time preprocessing and dependency versions, and require a deployment-pinned
SHA256. No automatic retraining, artifact replacement or production rollback
occurs. The demonstration explicitly trains a new experimental quote model on
October 7–9 and evaluates October 10–11; it is not a validated deployment.

Prediction logs include latency, training-reference feature z-scores and only
matured prespecified quote-event directional outcomes. Serial dependence and two
OOS days prevent significance claims. Report Sharpe stays null below 30 daily
observations. Closed-fill win rate is descriptive, not a complete round-trip or
independent-trade statistic. Reports compare supplied backtest/replay measurements
and flag configuration/granularity differences; numerical discrepancy alone does
not prove a causal explanation. Alerts remain local; no external messages sent.

## Operation

```bash
uv run --frozen --all-extras python examples/paper_demo.py --output data/paper/NEW_RUN
uv run --frozen --all-extras quantlab paper positions --database data/paper/NEW_RUN/account.sqlite
uv run --frozen --all-extras quantlab paper report --database data/paper/NEW_RUN/account.sqlite
uv run --frozen --all-extras quantlab paper kill --database data/paper/NEW_RUN/account.sqlite --reason 'operator stop'
```

Controls are durable queued requests; a running service applies them and journals
the result. A queued request is not reported as already executed. A stopped service
retains the queue for its next run. Long-running polling uses the reviewed
[systemd example](../deploy/quantlab-paper.service). Configuration is simulated-only;
operator-approved deployments must already be provisioned. No service is enabled
or started automatically. Market calendars schedule eligible execution; quote-event
strategies evaluate on each new observation, rather than arbitrary wall-clock
cron signals. Scheduled rebalancing/inference requires a reviewed strategy policy.
