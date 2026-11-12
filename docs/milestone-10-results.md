# Milestone 10 actual verification

[Architecture and operator guide](research-agent.md), [machine-readable results](milestone-10-results.json)
and the complete original request are saved.

Release session **54f1b7c8cab841f1a751c98f5d762c75** used the existing real ESZ13
snapshot `3fac02494948aacdc5db5afb23a70118d82715b40d4072c4de0f5deba7ddbd1f`.
The planner was explicitly **scripted engineering, not an external LLM**. No API
spending or real-money orders occurred. It ran two bounded investigations, each
with one model trial and five conventional controls: **12 recorded attempts**.
All candidates were rejected. The ridge five-minute model returned 0%; the random
forest fifteen-minute model averaged -1.21939% per OOS session fold. Positive
contract-control returns do not qualify that control with only two OOS sessions.

Both investigations reused the canonical futures holdout ledger, which remains
SEALED. The reserved futures period was never downloaded/evaluated and the equity
2019 holdout remained untouched. Costs, historical margin assumptions, archive
scope, repeated validation and correlated observations remain explicit limitations.
A prior development run was retained and included in history accounting; repeated
controls/runs are not independent new trading strategies. The final family contains
all retained registered hypotheses; exact counts are in the JSON report.

**303 Python tests passed**, with six optional external tests skipped. Tests cover
plan/tool validation, dataset/model scope, budget reservation, controls, actual
memory, deduplication, credential filtering, quarantined code, cancellation into
the futures supervisor, canonical holdout-ledger reuse and dashboard authorization.
**Five frontend tests and six real Chromium browser tests passed**, including
the agent session view and unauthorized control rejection. The independently
installed 0.10 wheel matched the executed policy/source identity. Lint, formatting,
TypeScript/Vite and Python package builds passed. No external
LLM integration was verified because no configured/priced provider credentials
are available. Generated-code execution remains disabled pending a verified OS
sandbox. No strategy qualifies for validated paper or live deployment.
