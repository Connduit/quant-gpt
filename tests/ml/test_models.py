import numpy as np
import polars as pl
import pytest

from quantlab.ml.evaluation import evaluate
from quantlab.ml.models import ModelSpec, ResearchModel


@pytest.fixture
def supervised():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(100, 3))
    target = x[:, 0] * 0.1 - x[:, 1] * 0.03
    return pl.DataFrame(
        {
            "a": x[:, 0],
            "b": x[:, 1],
            "c": x[:, 2],
            "target": target,
            "target_class": (target > 0).astype(int),
        }
    )


@pytest.mark.parametrize(
    "kind,objective",
    [
        ("ridge", "regression"),
        ("logistic", "classification"),
        ("random_forest", "regression"),
        ("random_forest", "classification"),
        ("lightgbm", "regression"),
        ("lightgbm", "classification"),
        ("xgboost", "regression"),
        ("xgboost", "classification"),
    ],
)
def test_models_training_prediction_serialization_reproducibility(
    supervised, tmp_path, kind, objective
):
    params = {"n_estimators": 8} if kind not in ("ridge", "logistic") else {}
    spec = ModelSpec(kind, objective, 23, params)
    train, test = supervised.head(80), supervised.tail(20)
    first = ResearchModel(spec).fit(train, ("a", "b", "c"))
    predicted = first.predict(test)
    assert np.isfinite(predicted).all()
    if objective == "classification":
        assert ((predicted >= 0) & (predicted <= 1)).all()
    first.save(tmp_path / "model")
    loaded = ResearchModel.load(tmp_path / "model")
    np.testing.assert_array_equal(predicted, loaded.predict(test))
    second = ResearchModel(spec).fit(train, ("a", "b", "c"))
    np.testing.assert_array_equal(predicted, second.predict(test))
    assert set(first.importance()) == {"a", "b", "c"}
    artifact = tmp_path / "model" / "model.joblib"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        ResearchModel.load(tmp_path / "model")


def test_scaling_is_fitted_only_on_training_rows(supervised):
    train = supervised.head(60)
    model = ResearchModel(ModelSpec()).fit(train, ("a", "b", "c"))
    scaler = model.pipeline.named_steps["scale"]
    expected = train.select("a", "b", "c").to_numpy().mean(axis=0)
    np.testing.assert_allclose(scaler.mean_, expected)
    model.predict(supervised.tail(40).with_columns(pl.col("a") + 1e6))
    np.testing.assert_allclose(scaler.mean_, expected)


def test_probability_calibration_and_rank_information_coefficient():
    from datetime import date

    frame = pl.DataFrame(
        {
            "session_date": [date(2024, 1, 1)] * 11,
            "target": np.linspace(-0.05, 0.05, 11),
            "target_class": [0] * 6 + [1] * 5,
        }
    )
    predictions = np.linspace(0, 1, 11)
    result = evaluate(frame, predictions, "classification")
    assert result["rank_information_coefficient"] == pytest.approx(1)
    assert sum(bin["count"] for bin in result["calibration"]) == 11
    assert result["brier_score"] == pytest.approx(
        np.mean((predictions - frame["target_class"].to_numpy()) ** 2)
    )
    assert result["directional_accuracy"] == pytest.approx(10 / 11)


@pytest.mark.parametrize(
    "spec",
    [
        lambda: ModelSpec("ridge", "classification"),
        lambda: ModelSpec("logistic", "regression"),
        lambda: ModelSpec("xgboost", parameters={"device": "cuda"}),
        lambda: ModelSpec("random_forest", parameters={"random_state": 123}),
    ],
)
def test_incompatible_task_or_execution_override_is_rejected(spec):
    with pytest.raises(ValueError):
        spec()
