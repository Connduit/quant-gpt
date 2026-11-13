import math
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from pathlib import Path

import yaml

from quantlab.features import FeatureConfig
from quantlab.ml.models import ModelSpec


def strict(values, allowed, label):
    if not isinstance(values, dict) or set(values) - set(allowed):
        raise ValueError(f"Unknown keys or invalid mapping in {label}")


@dataclass(frozen=True)
class RankingConfig:
    top_n: int = 2
    minimum_dollar_volume: float = 0
    rebalance_sessions: int = 5
    maximum_position_weight: float = 0.4
    cash_allocation: float = 0.2
    regime_filter: bool = False
    minimum_market_trend: float = 0
    minimum_prediction: float | None = None
    volatility_adjusted: bool = False
    position_sizing: str = "equal"
    lower_is_better: bool = False

    def __post_init__(self):
        if any(
            not math.isfinite(value)
            for value in (
                self.minimum_dollar_volume,
                self.maximum_position_weight,
                self.cash_allocation,
                self.minimum_market_trend,
            )
        ):
            raise ValueError("Ranking limits must be finite")
        if type(self.regime_filter) is not bool:
            raise ValueError("regime_filter must be boolean")
        if type(self.volatility_adjusted) is not bool or type(self.lower_is_better) is not bool:
            raise ValueError("Ranking switches must be booleans")
        if self.minimum_prediction is not None and not math.isfinite(self.minimum_prediction):
            raise ValueError("Prediction threshold must be finite")
        if self.position_sizing not in ("equal", "inverse_volatility"):
            raise ValueError("Unsupported position sizing")
        if (
            type(self.top_n) is not int
            or self.top_n < 1
            or type(self.rebalance_sessions) is not int
            or self.rebalance_sessions < 1
        ):
            raise ValueError("top_n and rebalance_sessions must be positive integers")
        if (
            not 0 < self.maximum_position_weight <= 1
            or not 0 <= self.cash_allocation < 1
            or self.minimum_dollar_volume < 0
        ):
            raise ValueError("Invalid position, cash or liquidity limits")


@dataclass(frozen=True)
class Experiment:
    name: str
    data_dir: Path
    snapshots: dict[str, str]
    universe: tuple[str, ...]
    holdout_start: date
    benchmark: str = "SPY"
    horizon: int = 5
    sectors: dict[str, str] = field(default_factory=dict)
    features: FeatureConfig = FeatureConfig()
    models: tuple[ModelSpec, ...] = (ModelSpec(),)
    primary_model: str = "ridge"
    training_sessions: int = 120
    validation_sessions: int = 30
    test_sessions: int = 30
    expanding: bool = True
    embargo_sessions: int = 0
    ranking: RankingConfig = RankingConfig()
    initial_cash: str = "100000"
    execution: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.name.strip() or self.primary_model not in [m.type for m in self.models]:
            raise ValueError("Name and primary_model from the configured candidates are required")
        if len({m.type for m in self.models}) != len(self.models):
            raise ValueError("Model types must be unique within an experiment")
        if self.benchmark != "SPY":
            raise ValueError("Milestone 3 market-context benchmark is SPY")


def load_experiment(path: Path) -> Experiment:
    try:
        values = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError("Invalid experiment YAML") from exc
    strict(
        values,
        ("experiment", "data", "features", "models", "strategy", "validation", "execution"),
        "root",
    )
    if not {"experiment", "data"} <= set(values):
        raise ValueError("Experiment YAML requires experiment and data sections")
    experiment, data = values["experiment"], values["data"]
    strict(experiment, ("name", "primary_model"), "experiment")
    strict(
        data,
        (
            "data_dir",
            "snapshots",
            "universe",
            "benchmark",
            "prediction_horizon",
            "holdout_start",
            "sectors",
        ),
        "data",
    )
    feature = values.get("features", {})
    if "name" not in experiment or not {"snapshots", "universe", "holdout_start"} <= set(data):
        raise ValueError("Missing experiment name, snapshots, universe or holdout_start")
    if not isinstance(data["snapshots"], dict) or not isinstance(data["universe"], list):
        raise ValueError("Snapshots must be a mapping and universe a list")
    strict(feature, asdict(FeatureConfig()), "features")
    if "return_windows" in feature:
        feature["return_windows"] = tuple(feature["return_windows"])
    strategy = values.get("strategy", {})
    strict(strategy, [f.name for f in fields(RankingConfig)], "strategy")
    validation = values.get("validation", {})
    strict(
        validation,
        (
            "method",
            "training_sessions",
            "validation_sessions",
            "test_sessions",
            "expanding",
            "embargo_sessions",
        ),
        "validation",
    )
    if validation.pop("method", "walk_forward") != "walk_forward":
        raise ValueError("Only purged walk_forward validation is supported")
    execution = values.get("execution", {}).copy()
    initial = str(execution.pop("initial_cash", "100000"))
    strict(
        execution,
        (
            "commission_per_share",
            "commission_fixed",
            "minimum_commission",
            "slippage_bps",
            "spread_bps",
            "market_impact_bps",
        ),
        "execution",
    )
    specs = []
    for model in values.get("models", [{"type": "ridge"}]):
        strict(model, ("type", "objective", "seed", "parameters"), "models")
        specs.append(ModelSpec(**model))
    directory = Path(data.get("data_dir", "../data"))
    if not directory.is_absolute():
        directory = path.resolve().parent / directory
    raw_snapshots = data["snapshots"]
    snapshots = {}
    for symbol, value in raw_snapshots.items():
        # An optional ledger path is resolved by the runner, never stored as a secret.
        snapshots[symbol] = value
    holdout = data["holdout_start"]
    return Experiment(
        experiment["name"],
        directory,
        snapshots,
        tuple(data["universe"]),
        holdout if isinstance(holdout, date) else date.fromisoformat(holdout),
        data.get("benchmark", "SPY"),
        data.get("prediction_horizon", 5),
        data.get("sectors", {}),
        FeatureConfig(**feature),
        tuple(specs),
        experiment.get("primary_model", specs[0].type),
        ranking=RankingConfig(**strategy),
        initial_cash=initial,
        execution=execution,
        **validation,
    )
