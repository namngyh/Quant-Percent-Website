"""Optional CPU-friendly binary Risk-off heads and validation calibration."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from interpret.glassbox import ExplainableBoostingClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler


def aggregate_multiclass_risk_off(multiclass_probability: np.ndarray) -> np.ndarray:
    """Return P(Bear) + P(Stress) from CLASS_ORDER-aligned probabilities."""
    probability = np.asarray(multiclass_probability, dtype=float)
    if probability.ndim != 2 or probability.shape[1] != 4:
        raise ValueError("multiclass_probability must have shape (n, 4)")
    if not np.isfinite(probability).all() or not np.allclose(probability.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("multiclass_probability must be finite and sum to one")
    return np.clip(probability[:, 2] + probability[:, 3], 0.0, 1.0)


def downside_sample_weights(
    target: pd.Series | np.ndarray,
    future_mae: pd.Series | np.ndarray,
    sigma: pd.Series | np.ndarray,
    horizon: int,
    config: dict[str, Any],
) -> np.ndarray:
    """frequency × cost × severity weights, clipped by registered config."""
    y = np.asarray(target, dtype=int)
    mae = np.asarray(future_mae, dtype=float)
    volatility = np.asarray(sigma, dtype=float)
    if not (len(y) == len(mae) == len(volatility)):
        raise ValueError("target, future_mae and sigma must have equal length")
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    counts = np.bincount(y, minlength=2).astype(float)
    present = max(int((counts > 0).sum()), 1)
    frequency = np.ones(len(y), dtype=float)
    for label in (0, 1):
        if counts[label] > 0:
            frequency[y == label] = len(y) / (present * counts[label])
    cost = np.where(
        y == 1,
        float(config.get("positive_cost", 1.0)),
        float(config.get("negative_cost", 1.0)),
    )
    severity_lambda = float(config.get("severity_lambda", 1.0))
    severity_cap = float(config.get("severity_cap", 4.0))
    denominator = np.maximum(np.abs(volatility) * np.sqrt(horizon), 1e-8)
    severity_ratio = np.minimum(np.abs(np.minimum(mae, 0.0)) / denominator, severity_cap)
    severity = 1.0 + severity_lambda * severity_ratio
    total = frequency * cost * severity
    minimum = float(config.get("min_weight", 0.25))
    maximum = float(config.get("max_weight", 12.0))
    if minimum <= 0 or maximum < minimum:
        raise ValueError("sample-weight clipping bounds are invalid")
    total = np.clip(total, minimum, maximum)
    return total / max(float(total.mean()), 1e-12)


class BinaryTemperatureCalibrator:
    """One-parameter probability calibration fitted on validation only."""

    def __init__(self) -> None:
        self.temperature = 1.0
        self.used = False
        self.base_log_loss = float("nan")
        self.calibrated_log_loss = float("nan")

    @staticmethod
    def apply(probability: np.ndarray, temperature: float) -> np.ndarray:
        p = np.clip(np.asarray(probability, dtype=float), 1e-8, 1 - 1e-8)
        logits = np.log(p / (1 - p)) / max(float(temperature), 1e-6)
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -40, 40)))

    def fit(self, probability: np.ndarray, target: pd.Series | np.ndarray) -> "BinaryTemperatureCalibrator":
        y = np.asarray(target, dtype=int)
        p = np.asarray(probability, dtype=float)
        self.base_log_loss = float(log_loss(y, p, labels=[0, 1]))
        candidates = np.linspace(0.5, 3.0, 26)
        losses = np.asarray([log_loss(y, self.apply(p, value), labels=[0, 1]) for value in candidates])
        best = int(np.argmin(losses))
        self.calibrated_log_loss = float(losses[best])
        if self.calibrated_log_loss + 1e-12 < self.base_log_loss:
            self.temperature = float(candidates[best])
            self.used = True
        return self

    def transform(self, probability: np.ndarray) -> np.ndarray:
        return self.apply(probability, self.temperature) if self.used else np.asarray(probability, dtype=float)


class RiskOffHead:
    """Uniform wrapper around logistic, histogram boosting and binary EBM."""

    VALID_KINDS = {"logistic", "hist_gradient_boosting", "ebm"}

    def __init__(self, kind: str, *, random_state: int = 42, params: dict[str, Any] | None = None) -> None:
        if kind not in self.VALID_KINDS:
            raise ValueError(f"Risk-off kind must be one of {sorted(self.VALID_KINDS)}")
        self.kind = kind
        self.random_state = int(random_state)
        self.params = dict(params or {})
        self.model: Any | None = None
        self.feature_names: list[str] = []
        self.feature_importance_: pd.DataFrame = pd.DataFrame(columns=["feature", "importance"])
        self.warning: str | None = None
        self.constant_probability: float | None = None
        self.scaler: StandardScaler | None = None

    def _make_model(self) -> Any:
        if self.kind == "logistic":
            return LogisticRegression(
                C=float(self.params.get("C", 1.0)),
                solver="lbfgs",
                max_iter=int(self.params.get("max_iter", 500)),
                random_state=self.random_state,
                l1_ratio=0.0,
            )
        if self.kind == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(
                learning_rate=float(self.params.get("learning_rate", 0.05)),
                max_iter=int(self.params.get("max_iter", 100)),
                max_depth=int(self.params.get("max_depth", 3)),
                min_samples_leaf=int(self.params.get("min_samples_leaf", 20)),
                l2_regularization=float(self.params.get("l2_regularization", 1.0)),
                random_state=self.random_state,
            )
        return ExplainableBoostingClassifier(
            random_state=self.random_state,
            interactions=int(self.params.get("interactions", 0)),
            max_bins=int(self.params.get("max_bins", 64)),
            max_rounds=int(self.params.get("max_rounds", 60)),
            learning_rate=float(self.params.get("learning_rate", 0.03)),
            outer_bags=int(self.params.get("outer_bags", 1)),
            min_samples_leaf=int(self.params.get("min_samples_leaf", 5)),
            n_jobs=1,
        )

    def fit(
        self,
        features: pd.DataFrame,
        target: pd.Series | np.ndarray,
        *,
        sample_weight: np.ndarray | None = None,
        compute_importance: bool = True,
    ) -> "RiskOffHead":
        self.feature_names = list(features.columns)
        y = np.asarray(target, dtype=int)
        unique = np.unique(y)
        if len(unique) < 2:
            self.constant_probability = float(np.clip(y.mean() if len(y) else 0.0, 1e-6, 1 - 1e-6))
            self.warning = f"Training fold contains one class ({unique.tolist()}); constant-probability fallback used"
            warnings.warn(self.warning, RuntimeWarning, stacklevel=2)
            self.feature_importance_ = pd.DataFrame({"feature": self.feature_names, "importance": 0.0})
            return self
        self.model = self._make_model()
        model_features: pd.DataFrame | np.ndarray = features
        if self.kind == "logistic":
            self.scaler = StandardScaler()
            model_features = self.scaler.fit_transform(features)
        self.model.fit(model_features, y, sample_weight=sample_weight)
        if compute_importance:
            self._set_importance(features, y)
        else:
            self.feature_importance_ = pd.DataFrame(
                columns=["feature", "importance"]
            )
        return self

    def _set_importance(self, features: pd.DataFrame, target: np.ndarray) -> None:
        if self.kind == "logistic" and hasattr(self.model, "coef_"):
            values = np.abs(np.asarray(self.model.coef_)[0])
            names = self.feature_names
        elif self.kind == "ebm" and hasattr(self.model, "term_importances"):
            values = np.asarray(self.model.term_importances(), dtype=float)
            names = list(getattr(self.model, "term_names_", self.feature_names[: len(values)]))
        else:
            limit = min(
                len(features),
                int(self.params.get("importance_sample_size", 200)),
            )
            importance = permutation_importance(
                self.model,
                features.iloc[:limit],
                target[:limit],
                n_repeats=1,
                random_state=self.random_state,
                scoring="neg_log_loss",
                n_jobs=1,
            )
            values = np.asarray(importance.importances_mean, dtype=float)
            names = self.feature_names
        self.feature_importance_ = (
            pd.DataFrame({"feature": names, "importance": values})
            .sort_values("importance", ascending=False)
            .reset_index(drop=True)
        )

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        if self.constant_probability is not None:
            return np.full(len(features), self.constant_probability, dtype=float)
        if self.model is None:
            raise RuntimeError("RiskOffHead must be fitted before prediction")
        model_features: pd.DataFrame | np.ndarray = features
        if self.scaler is not None:
            model_features = self.scaler.transform(features)
        probability = np.asarray(self.model.predict_proba(model_features), dtype=float)
        classes = list(getattr(self.model, "classes_", [0, 1]))
        if 1 not in classes:
            return np.zeros(len(features), dtype=float)
        return np.clip(probability[:, classes.index(1)], 1e-8, 1 - 1e-8)

    def importance(self) -> pd.DataFrame:
        return self.feature_importance_.copy()

    def save(self, path: str | Path) -> Path:
        import joblib

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, destination)
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "RiskOffHead":
        import joblib

        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError("Serialized object is not a RiskOffHead")
        return loaded
