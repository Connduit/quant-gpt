# Execution incident response

1. Stop new sandbox submissions with the controller's kill operation or enqueue
   `quantlab execution kill --database PATH --reason REASON`. A queued response is
   not an applied response: verify the journal/service status. New submissions are
   locally blocked when the controller applies the kill. Requests already in flight
   can still have been accepted by the broker.
2. If explicitly required, add `--cancel-open`. Cancellation requests are separate
   from a new-order block; reconcile broker status before declaring cancellation.
3. Positions are retained. No automatic liquidation policy is defined or enabled.
   Do not describe stopping/cancelling as closing positions. Any future emergency
   liquidation policy requires separate review, sizing, execution and failure tests.
4. On timeout, outage, unexpected fill/order/position or cash discrepancy, keep
   execution suspended. Preserve database, logs, stable client IDs and timestamps.
   Retrieve the actual broker order/execution history; never blindly retry.
5. Back up consistently with the SQLite backup command. Restore only into a new
   location, verify the checksum and independently reconcile the broker. Unknown
   fees/actions or late executions require reviewed ledger reconstruction.
6. A kill reset is a separate signed operator action, possible only after safe
   reconciliation. It leaves strategies paused. Fresh data and a current approval
   are still required for explicit arming; known breached limits are not bypassed.
7. For model anomalies, pause the strategy, retain the model/feature versions,
   inspect drift/latency and recorded execution discrepancies. Rollback needs a
   separate exact-model authorization, clears deployment approval and never
   automatically replaces/restarts a live model.
8. Record the incident, evidence, cause hypotheses versus confirmed causes,
   remediation, independent reviewer and resume reason. No LLM rationale, process
   uptime or short-term P&L overrides missing scientific or operational evidence.

The current build has no LIVE submission path. Do not attempt to work around
network restrictions, TLS validation, missing permissions or unavailable credentials.
