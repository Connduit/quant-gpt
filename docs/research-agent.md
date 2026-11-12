# Bounded research agent

The [full request](milestone-10-instructions.md) is preserved. One orchestrating
agent uses modular planning, policy validation, fixed experiment tools, durable
memory and reporting. It has no broker, paper-promotion, holdout-evaluation,
arbitrary filesystem, shell or generated-code execution tools.

## Planning and independent authorization

`Plan` requires an explicit market/instrument scope, testable relationship,
potential biases, rejection criteria, chronological evaluation, approved dataset,
features, CPU model, target, holding horizon, decision cadence and interpretation.
Unknown fields/targets/timeframes fail schema validation. `ResearchTools` then
independently verifies exact data/model/feature scope and model-target compatibility.
No model-generated rationale can change dataset paths, validation, risk, costs,
resource caps, eligibility or holdout policy. Data supplied to the model are
untrusted context, never instructions granting tool authority.

The initial execution adapter is verified archival ES futures. Other research
artifacts remain inspectable through the existing system; new market execution
adapters require their own reviewed policy. The five CPU model families are
available within approved spaces. One proposed model trial and five conventional
controls are registered per investigation. Controls, repeated variants, failures
and prunes count in experiment/history accounting; they are not independent newly
discovered strategies. Every proposed plan and interpretation is distinguished
from actual recorded experiment observations.

The adapter reuses M4 resource supervision, Optuna, MLflow, M7 causal features,
execution accounting, purged walk-forward validation and cost stress. It passes a
canonical shared futures holdout ledger rather than creating an authorization
history per run directory. Agent tools cannot authorize/consume/release it.
Statistical diagnostics count all supplied retained discovery/statistical/futures/
agent registries. Unknown external searches remain a limitation. Two OOS days
cannot support significance: PSR/DSR stay unavailable and no candidate qualifies.

## LLM providers and cost controls

The OpenAI-compatible adapter supports HTTPS providers and explicitly local HTTP
LLM endpoints. Model, endpoint, pricing and structured-output/tool capability are
operator configuration. Remote calls require a credential, positive reviewed
pricing and a positive spend budget. `QUANTLAB_LLM_API_KEY` stays in environment
settings. It is never included in planning context, report exports or URLs.

JSON-schema outputs and the single `propose_research_plan` tool are supported.
Unknown/multiple tool calls fail closed. Unsupported capability responses update
the capability state and stop, rather than silently granting a different tool.
Transport failures, rate limits, timeouts, missing usage and uncertain responses
are explicit failures. There is no blind automatic retry after uncertain billing.
A reviewed new attempt must reserve its own budget.

Input bytes plus full schema/prompt overhead conservatively bound token costs;
output tokens are capped. Reservations remain charged even after failures or
unused capacity. Reported provider tokens/cost are logged separately, so `spent`
is a conservative reserved/charged budget counter, not an invoice. Invalid/unknown
costs stop the loop. A response exceeding its reservation stops further requests.
Provider prices/entitlements remain the operator's responsibility.

The deterministic `--scripted-engineering` planner is explicitly **not an LLM**.
It tests the same real execution/validation/memory loop with fixed proposals.
No external LLM connection is verified in the recorded demonstration. Live LLM
integration is opt-in and requires a reviewed priced policy/credential.

## Budgets, memory and stopping

SQLite WAL/FULL persists sessions, iterations, actual results, deduplication keys,
usage reservations, controls and event history. Deduplication fingerprints the
executable configuration/policy rather than hypothesis wording. Relevant memory
comes from stored records, including failures, never invented prior results.
Context size is bounded; older result context is trimmed without expanding data
permissions. Reports retain the underlying records and provenance.

Limits cover iterations, registered experiments including controls, wall time,
API spending, context/output and one concurrent agent/experiment worker. Each
study reserves its worst-case wall allocation before launch. Worker CPU/address
space limits and the existing trial resource supervisor remain active. Policy/code
changes invalidate resume. Uncertain/completed sessions are never blindly rerun.
Pause/cancel/emergency-stop are persistent controls; the watcher propagates them
into the existing experiment supervisor. Resuming a paused session retains all
budgets and records; it starts a reviewed worker rather than refreshing limits.

The CLI supervisor starts a fixed worker with a minimal environment: required
proxy/CA settings and the dedicated LLM key, excluding broker credentials and API
operator tokens. Dashboard research jobs apply the same restriction. Generated
code proposals are stored as `.proposal.txt` in quarantine, never imported,
executed, applied or allowed to modify production code. An independently verified
OS sandbox for generated code is **not implemented/enabled**; no adversarial
sandbox claim is made. The absence of a code executor is an enforced capability
boundary. Broker execution will run separately with its own credentials.

## Commands and dashboard

```bash
uv run --frozen --all-extras quantlab agent run --agent-config configs/agent.example.yaml \
  --root data/agent --scripted-engineering
uv run --frozen --all-extras quantlab agent list --root data/agent
uv run --frozen --all-extras quantlab agent report --root data/agent --session SESSION_ID
uv run --frozen --all-extras quantlab agent pause --root data/agent --session SESSION_ID --reason 'operator review'
uv run --frozen --all-extras quantlab agent cancel --root data/agent --session SESSION_ID --reason 'stop research'
```

`resume` records the reviewed control; run the same policy with `--session` to start
the paused worker again. For actual LLM planning omit the scripted flag only after
configuring reviewed pricing/spend/credentials. Example defaults intentionally
block paid calls. No service or loop starts automatically.

The dashboard shows objectives, hypotheses, plans, jobs, actual results, errors,
iterations and conservative budget usage. Researcher-authenticated start/control
requests require confirmation; objective text is an argument value, never a shell
command. The initial approved dashboard workflow is named scripted engineering,
not real LLM research. Session reports export observed evidence separately from
model interpretations. Live controls and final holdout access are absent.
