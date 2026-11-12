"""The LLM can propose research data, never executable instructions or permissions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Hypothesis(Strict):
    market: Literal["futures"]
    instruments: list[Literal["ES", "MES", "NQ", "MNQ"]] = Field(min_length=1, max_length=4)
    relationship: str = Field(min_length=15, max_length=1200)
    biases: list[str] = Field(min_length=1, max_length=10)
    rejection_criteria: str = Field(min_length=15, max_length=1200)
    evaluation: Literal["purged_walk_forward"]


class Plan(Strict):
    hypothesis: Hypothesis
    dataset_id: str = Field(min_length=5, max_length=100)
    feature_set: str = Field(min_length=1, max_length=50)
    model: Literal["ridge", "logistic", "random_forest", "lightgbm", "xgboost"]
    target: Literal["forward_return", "direction", "volatility_adjusted", "breakout_continuation"]
    horizon_minutes: Literal[5, 15, 60]
    decision_minutes: Literal[1, 5, 15]
    interpretation: str = Field(min_length=10, max_length=1800)


class Budgets(Strict):
    max_iterations: int = Field(2, ge=1, le=20)
    max_experiments: int = Field(12, ge=1, le=120)
    max_runtime_seconds: int = Field(900, ge=10, le=7200)
    max_api_spend: float = Field(0.0, ge=0, le=100)
    max_context_bytes: int = Field(24000, ge=1000, le=100000)
    max_output_tokens: int = Field(1500, ge=100, le=4000)
    max_concurrent_jobs: Literal[1] = 1
