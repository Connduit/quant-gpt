import copy
from pathlib import Path

import pytest
import yaml

from quantlab.discovery.common import fingerprint
from quantlab.discovery.config import Resources, distribution, load_study, suggest
from quantlab.discovery.data import prepare
from quantlab.discovery.study import FixedParameters, definition_for_number


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "float", "low": 0, "high": float("inf")},
        {"type": "float", "low": 0, "high": 10, "log": True},
        {"type": "int", "low": 10, "high": 1},
        {"type": "int", "low": 0.1, "high": 1},
        {"type": "categorical", "choices": []},
        {"type": "categorical", "choices": ["x", "x"]},
        {"type": "eval", "expression": "arbitrary code"},
    ],
)
def test_invalid_or_unbounded_distributions(spec):
    with pytest.raises(ValueError):
        distribution(spec)


def test_indexed_trial_proposals_are_reproducible(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "registry")
    first = [definition_for_number(config, base, n) for n in range(3)]
    resumed = [definition_for_number(config, base, n) for n in (2, 0, 1)]
    assert first[2] == resumed[0] and first[0] == resumed[1] and first[1] == resumed[2]
    assert first[0]["model"]["parameters"] != first[1]["model"]["parameters"]
    assert fingerprint({"path": Path("/tmp"), "parameters": first[0]})


def test_incompatible_models_and_forbidden_execution_options(study_document, tmp_path):
    document = copy.deepcopy(study_document)
    document["search"]["targets"] = ["direction"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="compatible"):
        load_study(path)
    document = copy.deepcopy(study_document)
    document["search"]["models"]["ridge"]["random_state"] = {"type": "int", "low": 1, "high": 2}
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="controlled"):
        load_study(path)
    with pytest.raises(ValueError, match="GPU"):
        Resources(gpu_ids=(0,))
    with pytest.raises(ValueError):
        Resources(workers=0)


def test_fixed_parameters_cannot_escape_space(study_file, tmp_path):
    config = load_study(study_file)
    base = prepare(config, tmp_path / "registry")
    params = {
        "target": "excess_return",
        "model_for_excess_return": "ridge",
        "feature_set": "momentum",
        "horizon": 5,
        "model.ridge.alpha": 1000,
        "strategy.top_n": 1,
    }
    with pytest.raises(ValueError, match="Out-of-space"):
        suggest(FixedParameters(params), config, base)
