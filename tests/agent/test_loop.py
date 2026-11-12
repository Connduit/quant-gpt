import pytest

from quantlab.agent.memory import Memory
from quantlab.agent.providers import ScriptedPlanner
from quantlab.agent.runner import Agent, scripted_plans
from quantlab.agent.schema import Budgets, Plan


class Tools:
    identity = "fixed-approved-policy"
    wall = 1
    experiments_per_study = 6
    budgets = Budgets(max_runtime_seconds=10, max_iterations=2, max_experiments=12)
    runs = 0

    def context(self, history):
        return {"actual_prior_iterations": history, "holdout_access": "FORBIDDEN"}

    def validate(self, p):
        plan = Plan.model_validate(p)
        if plan.dataset_id != "approved":
            raise ValueError("unauthorized dataset")
        return plan

    def executable(self, p):
        return p.model_dump(exclude={"hypothesis", "interpretation"})

    def run(self, p, output, *, stop_event, history_roots):
        self.runs += 1
        return {
            "counts": {"unique_hypotheses": 6},
            "recorded_history": {"unique_hypotheses": 6},
            "holdout": {"state": "SEALED"},
            "paper_trading_shortlist": [],
            "results": [
                {
                    "experiment_id": "actual-fixture-result",
                    "status": "REJECTED",
                    "summary": {"eligible": False},
                    "statistics": {"status": "insufficient_observations"},
                }
            ],
            "failed": [],
            "limitations": ["Deterministic mocked pipeline, not empirical research evidence"],
        }


def run(tmp_path, tools, plans):
    memory = Memory(tmp_path / "memory.sqlite")
    identity = memory.create("Test bounded research objective", tools.identity)
    agent = Agent(tools, memory, tmp_path, ScriptedPlanner(plans))
    return agent, memory, identity


def test_bounded_loop_records_rejections_and_next_hypothesis(tmp_path):
    tools = Tools()
    agent, memory, identity = run(tmp_path, tools, list(scripted_plans("approved")))
    result = agent.run(identity)
    assert result["session"]["iterations"] == 2 and tools.runs == 2
    assert result["session"]["experiments"] == 12
    assert all(r["status"] == "REJECTED" for r in result["iterations"])
    assert not result["live_enabled"] and not result["holdout_accessed"]
    assert result["provider"] == "scripted_engineering_not_llm"


def test_invalid_tool_scope_never_executes_and_duplicates_do_not_retest(tmp_path):
    tools = Tools()
    p = next(scripted_plans("approved"))
    agent, memory, identity = run(tmp_path, tools, [p, p])
    result = agent.run(identity)
    assert tools.runs == 1 and result["iterations"][-1]["status"] == "DUPLICATE"
    tools = Tools()
    agent, memory, identity = run(tmp_path / "bad", tools, [next(scripted_plans("holdout"))])
    result = agent.run(identity)
    assert tools.runs == 0 and result["iterations"][0]["status"] == "FAILED"


def test_budget_reservation_includes_baselines_and_pause_cancel(tmp_path):
    tools = Tools()
    tools.budgets = Budgets(max_runtime_seconds=10, max_experiments=5)
    agent, memory, identity = run(tmp_path, tools, list(scripted_plans("approved")))
    assert agent.run(identity)["session"]["experiments"] == 0
    tools = Tools()
    agent, memory, identity = run(tmp_path / "paused", tools, list(scripted_plans("approved")))
    memory.control(identity, "pause", "operator request")
    assert agent.run(identity)["session"]["status"] == "PAUSED" and tools.runs == 0
    memory.control(identity, "resume", "reviewed continuation")
    memory.control(identity, "cancel", "operator cancellation")
    assert agent.run(identity)["session"]["status"] == "CANCELLED" and tools.runs == 0


def test_uncertain_or_policy_changed_session_cannot_blindly_resume(tmp_path):
    tools = Tools()
    agent, memory, identity = run(tmp_path, tools, [])
    memory.update(identity, status="RUNNING")
    with pytest.raises(ValueError):
        agent.run(identity)
    memory.update(identity, status="PAUSED")
    tools.identity = "changed"
    with pytest.raises(ValueError, match="Policy/code changed"):
        agent.run(identity)


def test_api_spend_reservation_stops_before_provider_call(tmp_path):
    tools = Tools()
    tools.budgets = Budgets(max_runtime_seconds=10, max_api_spend=0.01)
    agent, memory, identity = run(tmp_path, tools, [])
    agent.provider.reserve_cost = lambda c, o: 1.0
    result = agent.run(identity)
    assert result["session"]["iterations"] == 0 and result["session"]["spent"] == 0


def test_cross_session_memory_is_grounded_in_stored_experiments(tmp_path):
    tools = Tools()
    agent, memory, identity = run(tmp_path, tools, [next(scripted_plans("approved"))])
    agent.run(identity)
    other = memory.create("Second bounded research objective", tools.identity)
    actual = memory.relevant_history(tools.identity, other)
    assert actual[0]["session"] == identity
    result = next(row for row in actual if "observations" in row["result"])
    assert result["result"]["observations"][0]["experiment_id"] == "actual-fixture-result"
