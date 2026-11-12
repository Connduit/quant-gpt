"""Strict bounds and declared heuristic policies, never executable search expressions."""

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from quantlab.ml.models import ModelSpec
from quantlab.research.config import strict

TARGETS = ("excess_return", "stock_return", "direction", "volatility")
GROUPS = (
    "momentum",
    "mean_reversion",
    "volatility",
    "volume",
    "market_regime",
    "technical",
    "relative_strength",
)


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")


def distribution(spec):
    if not isinstance(spec, dict):
        raise ValueError("Distributions must be mappings")
    kind = spec.get("type")
    if kind == "categorical":
        strict(spec, ("type", "choices"), "categorical distribution")
        choices = spec.get("choices")
        if not isinstance(choices, list) or not 1 <= len(choices) <= 100:
            raise ValueError("Categorical choices must contain 1-100 values")
        if any(
            not isinstance(x, (str, int, float, bool))
            or isinstance(x, float)
            and not math.isfinite(x)
            for x in choices
        ):
            raise ValueError("Categorical choices must be finite scalar values")
        if len({(type(x).__name__, str(x)) for x in choices}) != len(choices):
            raise ValueError("Duplicate categorical choices")
    elif kind in ("int", "float"):
        strict(spec, ("type", "low", "high", "step", "log"), "numeric distribution")
        low, high = spec.get("low"), spec.get("high")
        if (
            isinstance(low, bool)
            or isinstance(high, bool)
            or not isinstance(low, (int, float))
            or not isinstance(high, (int, float))
            or not math.isfinite(low)
            or not math.isfinite(high)
            or low > high
        ):
            raise ValueError("Numeric distributions need finite, ordered low/high bounds")
        if kind == "int" and (type(low) is not int or type(high) is not int):
            raise ValueError("Integer distributions need integer bounds")
        if type(spec.get("log", False)) is not bool:
            raise ValueError("log must be boolean")
        if spec.get("log") and (low <= 0 or "step" in spec):
            raise ValueError("Log distributions need positive bounds and no step")
        if "step" in spec and (
            spec["step"] <= 0 or kind == "int" and type(spec["step"]) is not int
        ):
            raise ValueError("step must be positive and match the distribution type")
    else:
        raise ValueError("Only bounded int, float and categorical distributions are supported")
    return spec


@dataclass(frozen=True)
class Resources:
    workers: int = 1
    cpu_threads: int = 1
    memory_mb: int = 4096
    trial_wall_seconds: int = 180
    trial_cpu_seconds: int = 120
    max_attempts: int = 2
    gpu_ids: tuple = ()

    def __post_init__(self):
        for name, low, high in (
            ("workers", 1, 8),
            ("cpu_threads", 1, 8),
            ("memory_mb", 128, 65536),
            ("trial_wall_seconds", 1, 86400),
            ("trial_cpu_seconds", 1, 86400),
            ("max_attempts", 1, 5),
        ):
            integer(getattr(self, name), low, high, name)
        if self.gpu_ids:
            raise ValueError("Current models are CPU-only; GPU assignment is unsupported")


@dataclass(frozen=True)
class Eligibility:
    minimum_windows: int = 2
    minimum_fills: int = 10
    minimum_exit_fills: int = 3
    maximum_drawdown: float = 0.25
    maximum_turnover: float = 20
    maximum_window_excess_std: float = 0.1
    minimum_positive_window_fraction: float = 0.5
    minimum_mean_excess: float = 0
    minimum_mean_baseline_excess: float = 0
    maximum_cost_degradation: float = 0.03
    maximum_top_trade_profit_share: float = 0.6

    def __post_init__(self):
        integer(self.minimum_windows, 2, 100, "minimum_windows")
        integer(self.minimum_fills, 0, 100000, "minimum_fills")
        integer(self.minimum_exit_fills, 0, 100000, "minimum_exit_fills")
        if any(not math.isfinite(v) for v in asdict(self).values()):
            raise ValueError("Eligibility thresholds must be finite")
        for name in (
            "maximum_drawdown",
            "minimum_positive_window_fraction",
            "maximum_top_trade_profit_share",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be a fraction")
        if (
            min(
                self.maximum_turnover, self.maximum_window_excess_std, self.maximum_cost_degradation
            )
            < 0
        ):
            raise ValueError("Maximum thresholds must be nonnegative")


@dataclass(frozen=True)
class ScoreWeights:
    excess_return: float = 1
    predictive_skill: float = 0.02
    sharpe: float = 0.01
    drawdown: float = 0.5
    turnover: float = 0.001
    costs: float = 1
    instability: float = 0.5
    rejection_penalty: float = 1

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("Score weights must be finite and nonnegative")
        if not self.predictive_skill or not self.drawdown or not self.turnover or not self.costs:
            raise ValueError(
                "Objectives must include predictive, drawdown, turnover and cost terms"
            )


@dataclass(frozen=True)
class StudyConfig:
    name: str
    hypothesis: str
    experiment: Path
    seed: int
    max_trials: int
    max_wall_seconds: int
    resources: Resources
    feature_sets: dict
    targets: tuple
    horizons: tuple
    models: dict
    strategy: dict
    eligibility: Eligibility = Eligibility()
    score: ScoreWeights = ScoreWeights()
    cost_multipliers: tuple = (2,)
    prune_below: float | None = None
    robustness: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.name.strip() or not self.hypothesis.strip():
            raise ValueError("Study name and research hypothesis are required")
        integer(self.seed, 0, 2**32 - 1, "seed")
        integer(self.max_trials, 1, 10000, "max_trials")
        integer(self.max_wall_seconds, 1, 604800, "max_wall_seconds")
        if not self.feature_sets or any(
            not groups or set(groups) - set(GROUPS) for groups in self.feature_sets.values()
        ):
            raise ValueError("Feature sets must name nonempty supported groups")
        if not self.targets or set(self.targets) - set(TARGETS):
            raise ValueError("Unsupported target")
        if not self.horizons or any(
            type(h) is not int or h not in (1, 5, 10) for h in self.horizons
        ):
            raise ValueError("Horizons must be 1, 5 or 10")
        if not self.models:
            raise ValueError("At least one model is required")
        for name, params in self.models.items():
            ModelSpec(
                name,
                "classification" if name == "logistic" else "regression",
                parameters={key: None for key in params},
            )
            for value in params.values():
                distribution(value)
        for target in self.targets:
            if not compatible_models(target, self.models):
                raise ValueError(f"No compatible model for {target}")
        allowed = (
            "top_n",
            "rebalance_sessions",
            "minimum_prediction",
            "volatility_adjusted",
            "position_sizing",
            "regime_filter",
            "maximum_position_weight",
            "cash_allocation",
        )
        strict(self.strategy, allowed, "strategy search")
        for name, spec in self.strategy.items():
            if name == "minimum_prediction":
                strict(spec, TARGETS, "target-specific prediction thresholds")
                for value in spec.values():
                    distribution(value)
            else:
                distribution(spec)
        if not self.cost_multipliers or any(
            not math.isfinite(v) or not 1 < v <= 10 for v in self.cost_multipliers
        ):
            raise ValueError("Cost stress multipliers must be in (1,10]")
        if self.prune_below is not None and not math.isfinite(self.prune_below):
            raise ValueError("Prune threshold must be finite")
        strict(
            self.robustness,
            (
                "top_k",
                "include_rejected_for_diagnostics",
                "max_variants",
                "parameter_fraction",
                "window_fraction",
                "universe_subsets",
            ),
            "robustness",
        )
        integer(self.robustness.get("top_k", 1), 0, 5, "robustness top_k")
        integer(self.robustness.get("max_variants", 6), 1, 20, "max_variants")
        for key in ("parameter_fraction", "window_fraction"):
            value = self.robustness.get(key, 0.2)
            if not 0 < value <= 0.5:
                raise ValueError("Robustness fractions must be in (0,0.5]")


def compatible_models(target, models):
    return [name for name in models if name != ("ridge" if target == "direction" else "logistic")]


def load_study(path: Path) -> StudyConfig:
    try:
        values = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError("Invalid discovery YAML") from exc
    strict(
        values,
        (
            "study",
            "search",
            "resources",
            "eligibility",
            "score",
            "cost_multipliers",
            "prune_below",
            "robustness",
        ),
        "discovery",
    )
    base, search = values["study"], values["search"]
    strict(
        base,
        ("name", "hypothesis", "experiment", "seed", "max_trials", "max_wall_seconds"),
        "study",
    )
    strict(search, ("feature_sets", "targets", "horizons", "models", "strategy"), "search")
    experiment = Path(base["experiment"])
    if not experiment.is_absolute():
        experiment = path.resolve().parent / experiment
    return StudyConfig(
        base["name"],
        base["hypothesis"],
        experiment.resolve(),
        base.get("seed", 42),
        base.get("max_trials", 10),
        base.get("max_wall_seconds", 1800),
        Resources(**values.get("resources", {})),
        search["feature_sets"],
        tuple(search.get("targets", ["excess_return"])),
        tuple(search.get("horizons", [5])),
        search["models"],
        search.get("strategy", {}),
        Eligibility(**values.get("eligibility", {})),
        ScoreWeights(**values.get("score", {})),
        tuple(values.get("cost_multipliers", [2])),
        values.get("prune_below"),
        values.get("robustness", {}),
    )


def suggest(trial, config: StudyConfig, base: dict) -> dict:
    import copy

    result = copy.deepcopy(base)
    target = trial.suggest_categorical("target", list(config.targets))
    model = trial.suggest_categorical(
        f"model_for_{target}", compatible_models(target, config.models)
    )
    group = trial.suggest_categorical("feature_set", list(config.feature_sets))
    horizon = trial.suggest_categorical("horizon", list(config.horizons))
    params = {
        name: sample(trial, f"model.{model}.{name}", spec)
        for name, spec in config.models[model].items()
    }
    strategy = dict(result["strategy"])
    for name, spec in config.strategy.items():
        if name == "minimum_prediction":
            if target in spec:
                strategy[name] = sample(trial, f"strategy.threshold.{target}", spec[target])
        else:
            strategy[name] = sample(trial, f"strategy.{name}", spec)
    result.update(
        target=target,
        horizon=horizon,
        groups=config.feature_sets[group],
        model={
            "type": model,
            "objective": "classification" if target == "direction" else "regression",
            "seed": config.seed,
            "parameters": params,
        },
        strategy=strategy,
    )
    return result


def sample(trial, name, spec):
    if spec["type"] == "categorical":
        return trial.suggest_categorical(name, spec["choices"])
    options = {key: value for key, value in spec.items() if key != "type"}
    return (trial.suggest_int if spec["type"] == "int" else trial.suggest_float)(name, **options)
