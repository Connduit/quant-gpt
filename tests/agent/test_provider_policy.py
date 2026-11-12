import json
from pathlib import Path

import httpx
import pytest

from quantlab.agent.cli import worker_environment
from quantlab.agent.policy import ResearchTools
from quantlab.agent.providers import LLMUnavailable, OpenAICompatible
from quantlab.agent.runner import scripted_plans
from quantlab.agent.schema import Plan


def proposal():
    return next(scripted_plans("verified-es-2013-development"))


def test_strict_schema_rejects_hidden_permissions_and_invalid_features():
    p = proposal()
    p["shell"] = "dangerous generated command"
    with pytest.raises(ValueError):
        Plan.model_validate(p)
    p = proposal()
    p["horizon_minutes"] = 1
    with pytest.raises(ValueError):
        Plan.model_validate(p)


def test_actual_policy_scope_and_model_target_compatibility():
    root = Path(__file__).resolve().parents[2]
    if not (root / "data/futures/real-inputs/dataset.json").is_file():
        pytest.skip("Optional verified local futures archive unavailable")
    tools = ResearchTools(root / "configs/agent.example.yaml")
    p = proposal()
    tools.validate(p)
    p["dataset_id"] = "../../reserved-holdout"
    with pytest.raises(ValueError, match="unauthorized"):
        tools.validate(p)
    p = proposal()
    p["target"] = "direction"
    with pytest.raises(ValueError, match="incompatible"):
        tools.validate(p)
    assert tools.experiments_per_study == 6
    d = tools.executable(tools.validate(proposal()))
    assert d["study"]["max_trials"] == 1 and d["data"] == tools.template["data"]
    assert d["risk"] == tools.template["risk"] and d["validation"] == tools.template["validation"]


def test_compatible_structured_response_usage_and_no_broker_credentials():
    def reply(request):
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert "broker" not in request.headers
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(proposal())}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 200},
            },
        )

    provider = OpenAICompatible(
        model="test-model",
        input_per_million=1,
        output_per_million=2,
        api_key="test",
        client=httpx.Client(transport=httpx.MockTransport(reply)),
    )
    answer = provider.propose("untrusted research context", max_output_tokens=300)
    assert answer.cost == pytest.approx(0.0005)
    assert provider.reserve_cost(100, 300) > answer.cost
    env = worker_environment(
        {
            "ALPACA_LIVE_SECRET": "never",
            "QUANTLAB_OPERATOR_TOKEN": "never",
            "AWS_SECRET_ACCESS_KEY": "never",
            "QUANTLAB_LLM_API_KEY": "allowed",
            "HTTPS_PROXY": "proxy",
        }
    )
    assert set(env).isdisjoint(
        {"ALPACA_LIVE_SECRET", "QUANTLAB_OPERATOR_TOKEN", "AWS_SECRET_ACCESS_KEY"}
    )
    assert env["QUANTLAB_LLM_API_KEY"] == "allowed" and env["HTTPS_PROXY"] == "proxy"


def test_unknown_tools_and_ambiguous_provider_fail_closed():
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "submit_live_order", "arguments": "{}"}}
                        ]
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    ]
    provider = OpenAICompatible(
        model="test",
        input_per_million=1,
        output_per_million=1,
        tools=True,
        api_key="test",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=responses[0]))
        ),
    )
    with pytest.raises(ValueError, match="Unexpected"):
        provider.propose("context", max_output_tokens=100)
    provider = OpenAICompatible(
        model="test",
        input_per_million=1,
        output_per_million=1,
        api_key="test",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))),
    )
    with pytest.raises(LLMUnavailable, match="not automatically retried"):
        provider.propose("context", max_output_tokens=100)


def test_generated_code_is_quarantined_text_not_executed(tmp_path):
    result = ResearchTools.generated_code_proposal(
        "open('/tmp/must-not-run','w').write('unsafe')", tmp_path
    )
    assert not result["executed"] and result["review_required"]
    assert (tmp_path / result["proposal"]).suffix == ".txt"
    assert not (tmp_path / "production.py").exists()


def test_remote_pricing_and_transport_require_reviewed_configuration():
    with pytest.raises(ValueError):
        OpenAICompatible(
            model="test",
            endpoint="http://external.example",
            input_per_million=1,
            output_per_million=1,
        )
    with pytest.raises(ValueError):
        OpenAICompatible(model="test", input_per_million=0, output_per_million=0, api_key="test")


def test_cancellation_reaches_existing_futures_supervisor_before_trials(tmp_path):
    import threading

    import yaml

    from quantlab.agent.policy import ResearchTools
    from quantlab.futures.research import run_futures_research

    root = Path(__file__).resolve().parents[2]
    if not (root / "data/futures/real-inputs/dataset.json").is_file():
        pytest.skip("Optional verified local futures archive unavailable")
    tools = ResearchTools(root / "configs/agent.example.yaml")
    config = tmp_path / "research.yaml"
    config.write_text(yaml.safe_dump(tools.template))
    stop = threading.Event()
    stop.set()
    result = run_futures_research(config, tmp_path / "cancelled", stop_event=stop)
    assert result["counts"]["attempts"] == 0
    assert result["holdout"]["state"] == "SEALED"


def test_agent_runs_share_canonical_holdout_ledger(tmp_path, monkeypatch):
    import threading

    import quantlab.agent.policy as module

    root = Path(__file__).resolve().parents[2]
    if not (root / "data/futures/real-inputs/dataset.json").is_file():
        pytest.skip("Optional verified local archive unavailable")
    tools = ResearchTools(root / "configs/agent.example.yaml")
    captured = {}

    def execute(*args, **kwargs):
        captured.update(kwargs)
        return {"verified": "stub"}

    monkeypatch.setattr(module, "run_futures_research", execute)
    tools.run(
        tools.validate(proposal()), tmp_path / "run", stop_event=threading.Event(), history_roots=()
    )
    assert captured["holdout_vault_path"] == root / "data/futures/holdout-vault.sqlite"
