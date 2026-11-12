import copy

import pytest

from quantlab.statistical.config import ValidationPolicy
from quantlab.statistical.pipeline import (
    aligned_family,
    assign_status,
    history,
    robustness_definitions,
)


def passing():
    result = {
        "summary": {
            "rejection_reasons": [],
            "mean_validation_return": 0.1,
            "mean_baseline_excess": 0.02,
        },
        "windows": [{}, {}, {}],
        "action_coverage": {"SPY": {"complete": True}},
    }
    diagnostics = {
        "sessions": 500,
        "effective_sessions": 200,
        "fdr_by_q": 0.01,
        "familywise_p": 0.02,
        "deflated_sharpe": {"probability": 0.99},
        "all_excess_intervals_positive": True,
        "robustness_passed": True,
    }
    return result, diagnostics


def test_all_four_statuses_and_coverage_gate():
    result, d = passing()
    p = ValidationPolicy()
    assert assign_status(result, d, p)[0] == "REQUIRES_FURTHER_TESTING"
    evidence = {"historical_universe_certified": True, "independent_selection_period": True}
    assert assign_status(result, d, p, evidence=evidence)[0] == "VALIDATED_FOR_PAPER_TRADING"
    result["action_coverage"]["SPY"]["complete"] = False
    assert assign_status(result, d, p, evidence=evidence)[0] == "REQUIRES_FURTHER_TESTING"
    d["sessions"] = 20
    assert assign_status(result, d, p)[0] == "INSUFFICIENT_EVIDENCE"
    result["summary"]["mean_validation_return"] = -0.01
    assert assign_status(result, d, p)[0] == "REJECTED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("fdr_by_q", 0.9),
        ("familywise_p", 0.9),
        ("robustness_passed", False),
        ("all_excess_intervals_positive", False),
    ],
)
def test_statistical_failure_never_promotes(field, value):
    result, d = passing()
    d[field] = value
    assert assign_status(result, d, ValidationPolicy())[0] == "INSUFFICIENT_EVIDENCE"


def test_false_yaml_certification_rejected():
    with pytest.raises(ValueError, match="certification"):
        ValidationPolicy(historical_universe_certified=True)
    with pytest.raises(ValueError):
        ValidationPolicy(replications=1)


def test_family_intersection_preserves_dates():
    candidates = [
        {"fold_returns": [{"dates": ["a", "b", "c"], "excess": [1, 2, 3]}]},
        {"fold_returns": [{"dates": ["b", "c", "d"], "excess": [4, 5, 6]}]},
    ]
    matrices, dates = aligned_family(candidates)
    assert dates == ["b", "c"]
    assert matrices[0].tolist() == [[2, 4], [3, 5]]


def test_separate_robustness_variants_preserve_original():
    d = {
        "execution": {"commission_per_share": ".005", "slippage_bps": 5},
        "expanding": True,
        "validation_sessions": 30,
        "model": {"parameters": {"n_estimators": 10}},
        "strategy": {"position_sizing": "equal", "regime_filter": False},
    }
    before = copy.deepcopy(d)
    variants = robustness_definitions(d, 8)
    assert len(variants) == 8
    assert d == before
    assert dict(variants)["one_session_execution_delay"]["execution_delay_sessions"] == 1
    assert dict(variants)["double_slippage_bps"]["execution"]["slippage_bps"] == "10.0"


def test_history_empty_is_explicit(tmp_path):
    report = history([tmp_path])
    assert report["unique_hypotheses"] == 0
    assert "unknown" in report["scope"]


def test_integer_neighbor_is_distinct_even_with_small_parameter():
    d = {
        "execution": {},
        "expanding": True,
        "validation_sessions": 10,
        "model": {"parameters": {"max_depth": 2}},
        "strategy": {"position_sizing": "equal", "regime_filter": False},
    }
    variants = dict(robustness_definitions(d, 8))
    assert variants["nearby_max_depth"]["model"]["parameters"]["max_depth"] != 2
