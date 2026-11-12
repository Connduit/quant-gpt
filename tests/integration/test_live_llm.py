"""Optional explicitly budgeted LLM-only plan request, never research execution."""

import os
from pathlib import Path

import pytest

from quantlab.agent.policy import ResearchTools
from quantlab.agent.runner import provider_from_policy


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("QUANTLAB_LIVE_LLM") != "1", reason="opt-in configured priced LLM request"
)
def test_configured_llm_returns_a_valid_bounded_plan():
    configuration = os.getenv("QUANTLAB_LLM_POLICY")
    if not configuration or not os.getenv("QUANTLAB_LLM_API_KEY"):
        pytest.skip("Reviewed positive-budget LLM policy and credentials unavailable")
    tools = ResearchTools(Path(configuration))
    provider = provider_from_policy(tools)
    context = "Propose one plan for this approved policy: " + str(tools.context([]))
    reserve = provider.reserve_cost(len(context.encode()), tools.budgets.max_output_tokens)
    if reserve > tools.budgets.max_api_spend:
        pytest.skip("Request exceeds reviewed spend budget")
    answer = provider.propose(context, max_output_tokens=tools.budgets.max_output_tokens)
    tools.validate(answer.plan)
