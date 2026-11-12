# Milestone 9 verification

The [architecture](dashboard-architecture.md), [operator guide](dashboard.md) and
[actual browser screenshot](dashboard-overview.png) document the implementation.
The UI reads eleven curated real research/model/dataset/replay artifacts. It uses
no fictitious profitable strategies, current prices or broker balances.

**287 Python tests passed**, preserving prior functionality; five optional external
network tests skipped. **Five frontend tests** and **five real Chromium browser
tests passed**. TypeScript/Vite production build, Python source/wheel build, lint
and formatting passed. Browser tests exercised real API/artifact data, measured
charts, model inspection, rejection display, unauthorized paper controls,
SSE/error handling and mobile navigation. No research job was launched through
HTTP during this dashboard verification; the underlying bounded workflows were
verified in earlier milestones and the launcher authorization is tested.

The installed 0.9 wheel's API reconstructed the actual replay account at
$98,882.77, verified holdout ledger states SEALED and reported zero eligible
strategies with live execution disabled. The dashboard neither deserializes models
nor accesses protected holdout bars. Research and live readiness remain separate.

Paper state is read from consistent journal-checked SQLite snapshots. Corrupt
materialized state is unavailable, not healthy. Writes require separate operator
or researcher roles, explicit confirmation and schema validation. Rejected
strategies cannot be promoted. Queued paper actions are not reported as applied.
Uncertain research work after restart blocks new launches pending reconciliation.

External streaming, LLM integration, broker connectivity, deployment TLS/identity
infrastructure and live trading are not verified by these UI tests. The agent and
live-readiness pages are extension points for the separately requested M10/M11.
