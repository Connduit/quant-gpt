from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from quantlab.discovery.config import Eligibility, ScoreWeights, load_study
from quantlab.discovery.data import prepare
from quantlab.discovery.evaluation import summarize
from quantlab.discovery.registry import Registry
from quantlab.discovery.reports import comparison
from quantlab.discovery.robustness import variants
from quantlab.discovery.study import definition_for_number


def windows():
    return [
        {
            "performance": {
                "total_return": 0.02,
                "gross_turnover": 1,
                "maximum_drawdown": -0.02,
                "sharpe_ratio": 1,
                "fill_count": 12,
                "exit_fill_count": 6,
            },
            "benchmark": {"total_return": 0.01},
            "baselines": {"random": {"total_return": 0.015}},
            "cost_stress": {"2": {"total_return": 0.018}},
            "cost_rate": 0.001,
            "predictive_skill": 0.2,
            "exit_profits": [1, 1, 1, 1],
        }
        for _ in range(2)
    ]


def test_transparent_score_and_zero_survivors_are_supported():
    result = summarize(windows(), Eligibility(), ScoreWeights())
    assert result["eligible"]
    assert result["score"] == pytest.approx(sum(result["score_terms"].values()))
    rejected = summarize(windows(), replace(Eligibility(), minimum_fills=1000), ScoreWeights())
    assert not rejected["eligible"] and "too_few_fills" in rejected["rejection_reasons"]
    assert rejected["objective"] == pytest.approx(rejected["score"] - 1)


@pytest.mark.parametrize(
    "policy,reason",
    [
        ({"maximum_drawdown": 0.01}, "excessive_drawdown"),
        ({"minimum_exit_fills": 100}, "too_few_exit_fills"),
        ({"maximum_turnover": 0.5}, "excessive_turnover"),
        ({"maximum_cost_degradation": 0.001}, "cost_sensitive"),
        ({"minimum_mean_baseline_excess": 0.1}, "weaker_than_simple_baselines"),
        ({"maximum_top_trade_profit_share": 0.01}, "profit_concentrated"),
    ],
)
def test_rejection_criteria_are_explained(policy, reason):
    summary = summarize(windows(), replace(Eligibility(), **policy), ScoreWeights())
    assert reason in summary["rejection_reasons"]


def test_transactional_duplicate_detection_and_recovery(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "inputs")
    definition = definition_for_number(config, base, 0)
    registry = Registry(tmp_path / "state")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: registry.claim(definition), range(2)))
    assert sum(outcome[2] for outcome in outcomes) == 1
    row = registry.rows()[0]
    with registry.connect() as c:
        c.execute("UPDATE attempts SET owner_pid=987654321 WHERE id=?", (row["id"],))
    assert registry.recover() == [row["id"]]
    assert registry.attempt(row["id"])["status"] == "INTERRUPTED"
    _, new, claimed = registry.claim(definition)
    assert claimed and new["number"] == 2
    assert new["id"] != row["id"]
    assert comparison(tmp_path / "state")["eligible"] == []


def test_robustness_variants_are_bounded_and_do_not_mutate_original(study_file, tmp_path):
    import copy

    config = load_study(study_file)
    base = prepare(config, tmp_path / "registry")
    original = definition_for_number(config, base, 0)
    before = copy.deepcopy(original)
    scenarios = variants(original, config)
    assert original == before and 1 <= len(scenarios) <= 6
    assert all(d["holdout_start"] == original["holdout_start"] for _, d in scenarios)
    assert any("training_window" in name for name, _ in scenarios)
    for _, definition in scenarios:
        alpha = definition["model"]["parameters"]["alpha"]
        assert 0.1 <= alpha <= 10
