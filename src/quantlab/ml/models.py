"""Seeded CPU estimators with train-only preprocessing and verified local artifacts."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ModelSpec:
    type: str = "ridge"
    objective: str = "regression"
    seed: int = 42
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be a nonnegative 32-bit integer")
        if self.type not in ("ridge", "logistic", "random_forest", "lightgbm", "xgboost"):
            raise ValueError("Unknown model type")
        if self.objective not in ("regression", "classification"):
            raise ValueError("Objective must be regression or classification")
        if self.type == "ridge" and self.objective != "regression":
            raise ValueError("Ridge requires regression")
        if self.type == "logistic" and self.objective != "classification":
            raise ValueError("Logistic regression requires classification")
        forbidden = {
            "random_state",
            "n_jobs",
            "device",
            "tree_method",
            "objective",
            "num_threads",
            "deterministic",
            "force_col_wise",
            "device_type",
            "seed",
            "nthread",
            "predictor",
            "updater",
        }
        if forbidden & set(self.parameters):
            raise ValueError("Seed, task and CPU execution options are controlled by ModelSpec")


class ResearchModel:
    def __init__(self, spec: ModelSpec):
        self.spec = spec
        classification = spec.objective == "classification"
        params = spec.parameters.copy()
        if spec.type == "ridge":
            estimator = Ridge(**params)
        elif spec.type == "logistic":
            estimator = LogisticRegression(random_state=spec.seed, **{"max_iter": 1000, **params})
        elif spec.type == "random_forest":
            cls = RandomForestClassifier if classification else RandomForestRegressor
            estimator = cls(random_state=spec.seed, n_jobs=1, **{"n_estimators": 100, **params})
        elif spec.type == "lightgbm":
            from lightgbm import LGBMClassifier, LGBMRegressor

            cls = LGBMClassifier if classification else LGBMRegressor
            estimator = cls(
                random_state=spec.seed,
                n_jobs=1,
                deterministic=True,
                force_col_wise=True,
                verbosity=-1,
                **params,
            )
        else:
            from xgboost import XGBClassifier, XGBRegressor

            cls = XGBClassifier if classification else XGBRegressor
            estimator = cls(
                random_state=spec.seed, n_jobs=1, tree_method="hist", device="cpu", **params
            )
        steps = [("scale", StandardScaler())] if spec.type in ("ridge", "logistic") else []
        self.pipeline = Pipeline([*steps, ("model", estimator)])
        self.feature_names: tuple[str, ...] = ()

    def fit(self, frame, feature_names: tuple[str, ...]):
        x = frame.select(feature_names).to_numpy()
        target = "target_class" if self.spec.objective == "classification" else "target"
        y = frame[target].to_numpy()
        if x.shape[0] < 2 or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Training requires finite features/targets and at least two samples")
        if self.spec.objective == "classification" and len(np.unique(y)) != 2:
            raise ValueError("Classification training requires both target classes")
        self.pipeline.fit(x, y)
        self.feature_names = feature_names
        return self

    def predict(self, frame):
        if not self.feature_names:
            raise ValueError("Model has not been fitted")
        x = frame.select(self.feature_names).to_numpy()
        if not np.isfinite(x).all():
            raise ValueError("Prediction features must be finite")
        if self.spec.objective == "classification":
            return self.pipeline.predict_proba(x)[:, 1]
        return self.pipeline.predict(x)

    def importance(self):
        estimator = self.pipeline.named_steps["model"]
        if hasattr(estimator, "feature_importances_"):
            values = estimator.feature_importances_
        elif hasattr(estimator, "coef_"):
            values = np.asarray(estimator.coef_).reshape(-1)
        else:
            return None
        return dict(zip(self.feature_names, map(float, values), strict=True))

    def evaluate(self, frame):
        from quantlab.ml.evaluation import evaluate

        return evaluate(frame, self.predict(frame), self.spec.objective)

    def save(self, path: Path):
        if not self.feature_names:
            raise ValueError("Cannot save an unfitted model")
        path.mkdir(parents=True, exist_ok=False)
        joblib.dump(self, path / "model.joblib")
        manifest = {
            "spec": asdict(self.spec),
            "features": self.feature_names,
            "sha256": hashlib.sha256((path / "model.joblib").read_bytes()).hexdigest(),
            "versions": {
                n: version(n)
                for n in (
                    "quant-research-lab",
                    "scikit-learn",
                    "lightgbm",
                    "xgboost-cpu",
                    "numpy",
                    "joblib",
                )
            },
        }
        (path / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))

    @classmethod
    def load(cls, path: Path):
        """Load only trusted local joblib files; checksums are integrity checks, not a sandbox."""
        manifest = json.loads((path / "manifest.json").read_text())
        if hashlib.sha256((path / "model.joblib").read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("Model checksum mismatch")
        if any(version(name) != value for name, value in manifest["versions"].items()):
            raise ValueError("Model dependency versions differ from the training environment")
        model = joblib.load(path / "model.joblib")
        if not isinstance(model, cls) or tuple(manifest["features"]) != model.feature_names:
            raise ValueError("Model schema mismatch")
        return model
