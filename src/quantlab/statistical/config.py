"""Bounded reproducible validation configuration; no final-evaluation option."""

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from quantlab.discovery.config import Resources
from quantlab.research.config import strict


@dataclass(frozen=True)
class ValidationPolicy:
    seed: int = 42
    replications: int = 500
    block_lengths: tuple = (5, 10, 20)
    confidence_level: float = 0.95
    alpha: float = 0.05
    minimum_sessions: int = 252
    minimum_effective_sessions: int = 100
    minimum_folds: int = 3
    training_sessions: int = 504
    validation_sessions: int = 126
    test_sessions: int = 126
    retraining_sessions: int = 126
    gap_sessions: int = 2
    embargo_sessions: int = 5
    expanding: bool = False
    max_candidates: int = 4
    max_robustness_variants: int = 9
    max_wall_seconds: int = 1200
    historical_universe_certified: bool = False
    independent_selection_period: bool = False

    def __post_init__(self):
        bounds = {
            "seed": (0, 2**32 - 1),
            "replications": (100, 10000),
            "minimum_sessions": (20, 100000),
            "minimum_effective_sessions": (10, 100000),
            "minimum_folds": (2, 1000),
            "training_sessions": (10, 10000),
            "validation_sessions": (3, 10000),
            "test_sessions": (3, 10000),
            "retraining_sessions": (1, 10000),
            "gap_sessions": (0, 1000),
            "embargo_sessions": (0, 1000),
            "max_candidates": (1, 100),
            "max_robustness_variants": (0, 30),
            "max_wall_seconds": (10, 86400),
        }
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} outside supported bounds")
        if not 0 < self.alpha < 0.5 or not 0.5 < self.confidence_level < 1:
            raise ValueError("Invalid probability thresholds")
        if not self.block_lengths or any(
            type(b) is not int or not 2 <= b <= 252 for b in self.block_lengths
        ):
            raise ValueError("Block lengths are trading sessions in [2,252]")
        for name in ("expanding", "historical_universe_certified", "independent_selection_period"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        # Certification cannot be supplied by a user toggle in a research YAML.
        if self.historical_universe_certified or self.independent_selection_period:
            raise ValueError(
                "This adapter has no independent-period/membership certification interface"
            )


def load_config(path):
    path = Path(path).resolve()
    doc = yaml.safe_load(path.read_text())
    strict(
        doc,
        (
            "discovery_root",
            "verified_inputs",
            "research_config",
            "history_roots",
            "holdout",
            "policy",
            "resources",
        ),
        "statistical validation",
    )

    def resolve(v):
        return (path.parent / v).resolve()

    policy = ValidationPolicy(**doc.get("policy", {}))
    resources = Resources(**doc.get("resources", {}))
    holdout = doc["holdout"]
    from datetime import date

    for key in ("start", "end"):
        holdout[key] = str(holdout[key])
        date.fromisoformat(holdout[key])
    strict(holdout, ("sources", "start", "end", "purpose"), "holdout manifest")
    return {
        "discovery_root": resolve(doc["discovery_root"]),
        "verified_inputs": resolve(doc["verified_inputs"]),
        "research_config": resolve(doc["research_config"]),
        "history_roots": [resolve(v) for v in doc.get("history_roots", [doc["discovery_root"]])],
        "holdout": holdout,
        "policy": policy,
        "resources": resources,
        "configuration": {**doc, "policy": asdict(policy)},
    }
