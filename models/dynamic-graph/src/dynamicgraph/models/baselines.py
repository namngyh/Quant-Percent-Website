"""Tabular baseline classifiers and regressors.

Optional dependencies (XGBoost, LightGBM, EBM) are probed at import time and
simply omitted when unavailable -- the zoo always contains at least the naive
baseline and logistic regression, so the pipeline never fails because an extra
package is missing.

Class imbalance is handled with class weights and validation-tuned decision
thresholds. Synthetic oversampling (SMOTE and friends) is deliberately absent:
interpolating between neighbouring observations across a time-series boundary
manufactures information that did not exist at prediction time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

_SKIPPED: list[str] = []


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        if module not in _SKIPPED:
            _SKIPPED.append(module)
        return False


def skipped_modules() -> list[str]:
    return list(_SKIPPED)


class NaiveFrequencyClassifier(BaseEstimator, ClassifierMixin):
    """Predicts the training-set base rate for every observation.

    This is the honest floor: any model that cannot beat it on Brier score or
    log loss has learned nothing, regardless of how good its AUROC looks.
    """

    def __init__(self) -> None:
        self.base_rate_: float = 0.5
        self.classes_ = np.array([0, 1])

    def fit(self, X: Any, y: Any, sample_weight: Any = None) -> "NaiveFrequencyClassifier":
        y = np.asarray(y, dtype=float)
        self.base_rate_ = float(np.nanmean(y)) if y.size else 0.5
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X: Any) -> np.ndarray:
        n = len(X)
        p = np.clip(self.base_rate_, 1e-6, 1 - 1e-6)
        return np.column_stack([np.full(n, 1 - p), np.full(n, p)])

    def predict(self, X: Any) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


@dataclass
class ModelSpec:
    """A named estimator factory plus its tuning search space."""

    name: str
    factory: Callable[[dict[str, Any]], Any]
    default_params: dict[str, Any] = field(default_factory=dict)
    search_space: dict[str, Any] = field(default_factory=dict)
    needs_scaling: bool = False
    supports_nan: bool = False

    def build(self, params: dict[str, Any] | None = None, seed: int = 42) -> Any:
        merged = {**self.default_params, **(params or {})}
        merged.setdefault("random_state", seed)
        estimator = self.factory(merged)
        steps: list[tuple[str, Any]] = []
        if not self.supports_nan:
            steps.append(("impute", SimpleImputer(strategy="median")))
        if self.needs_scaling:
            steps.append(("scale", StandardScaler()))
        steps.append(("model", estimator))
        return Pipeline(steps)


def _sklearn_deprecates_penalty() -> bool:
    """scikit-learn 1.8 deprecated `penalty=` in favour of `l1_ratio=`."""
    try:
        from sklearn import __version__ as version

        major, minor = (int(p) for p in version.split(".")[:2])
        return (major, minor) >= (1, 8)
    except Exception:
        return False


def _logistic(params: dict[str, Any]) -> Any:
    penalty = params.get("penalty", "elasticnet")
    kwargs: dict[str, Any] = {
        "C": params.get("C", 1.0),
        "max_iter": params.get("max_iter", 2000),
        "class_weight": params.get("class_weight", "balanced"),
        "random_state": params.get("random_state", 42),
    }
    l1_ratio = {"elasticnet": params.get("l1_ratio", 0.5), "l1": 1.0, "l2": 0.0}[penalty]

    if _sklearn_deprecates_penalty():
        # New API: the mixing parameter alone selects the penalty family.
        kwargs.update({"l1_ratio": l1_ratio, "solver": "saga" if l1_ratio > 0 else "lbfgs"})
    elif penalty == "elasticnet":
        kwargs.update({"penalty": "elasticnet", "solver": "saga", "l1_ratio": l1_ratio})
    elif penalty == "l1":
        kwargs.update({"penalty": "l1", "solver": "liblinear"})
    else:
        kwargs.update({"penalty": "l2", "solver": "lbfgs"})
    return LogisticRegression(**kwargs)


def build_model_zoo(config: Any, task: str = "classification") -> dict[str, ModelSpec]:
    """Assemble the enabled models for `task` ('classification' | 'regression')."""
    models_cfg = config.models
    seed = int(config.project.seed)
    class_weight = models_cfg.class_weight
    zoo: dict[str, ModelSpec] = {}

    if task == "classification":
        if models_cfg.run_naive:
            zoo["naive_frequency"] = ModelSpec(
                name="naive_frequency",
                factory=lambda p: NaiveFrequencyClassifier(),
                supports_nan=True,
            )
        if models_cfg.run_logistic:
            zoo["logistic_elasticnet"] = ModelSpec(
                name="logistic_elasticnet",
                factory=_logistic,
                default_params={"penalty": "elasticnet", "C": 0.1, "l1_ratio": 0.5,
                                "class_weight": class_weight},
                search_space={
                    "C": ("loguniform", 1e-3, 10.0),
                    "l1_ratio": ("uniform", 0.0, 1.0),
                },
                needs_scaling=True,
            )
            zoo["logistic_l2"] = ModelSpec(
                name="logistic_l2",
                factory=_logistic,
                default_params={"penalty": "l2", "C": 1.0, "class_weight": class_weight},
                search_space={"C": ("loguniform", 1e-3, 100.0)},
                needs_scaling=True,
            )
        if models_cfg.run_random_forest:
            zoo["random_forest"] = ModelSpec(
                name="random_forest",
                factory=lambda p: RandomForestClassifier(
                    n_estimators=p.get("n_estimators", 400),
                    max_depth=p.get("max_depth", 6),
                    min_samples_leaf=p.get("min_samples_leaf", 20),
                    max_features=p.get("max_features", "sqrt"),
                    class_weight=p.get("class_weight", class_weight),
                    n_jobs=1,
                    random_state=p.get("random_state", seed),
                ),
                search_space={
                    "max_depth": ("int", 2, 10),
                    "min_samples_leaf": ("int", 5, 60),
                },
            )
        if models_cfg.run_hist_gradient_boosting:
            zoo["hist_gradient_boosting"] = ModelSpec(
                name="hist_gradient_boosting",
                factory=lambda p: HistGradientBoostingClassifier(
                    max_iter=p.get("max_iter", 300),
                    learning_rate=p.get("learning_rate", 0.05),
                    max_depth=p.get("max_depth", 3),
                    min_samples_leaf=p.get("min_samples_leaf", 25),
                    l2_regularization=p.get("l2_regularization", 1.0),
                    early_stopping=False,
                    class_weight=p.get("class_weight", class_weight),
                    random_state=p.get("random_state", seed),
                ),
                search_space={
                    "learning_rate": ("loguniform", 0.01, 0.2),
                    "max_depth": ("int", 2, 6),
                    "min_samples_leaf": ("int", 10, 60),
                    "l2_regularization": ("loguniform", 1e-3, 10.0),
                },
                supports_nan=True,
            )
        if models_cfg.run_xgboost_if_available and _has("xgboost"):
            import xgboost as xgb

            zoo["xgboost"] = ModelSpec(
                name="xgboost",
                factory=lambda p: xgb.XGBClassifier(
                    n_estimators=p.get("n_estimators", 300),
                    learning_rate=p.get("learning_rate", 0.05),
                    max_depth=p.get("max_depth", 3),
                    subsample=p.get("subsample", 0.8),
                    colsample_bytree=p.get("colsample_bytree", 0.8),
                    reg_lambda=p.get("reg_lambda", 1.0),
                    scale_pos_weight=p.get("scale_pos_weight", 1.0),
                    eval_metric="logloss",
                    tree_method="hist",
                    n_jobs=1,
                    random_state=p.get("random_state", seed),
                ),
                search_space={
                    "learning_rate": ("loguniform", 0.01, 0.2),
                    "max_depth": ("int", 2, 6),
                    "subsample": ("uniform", 0.6, 1.0),
                    "reg_lambda": ("loguniform", 0.1, 20.0),
                },
                supports_nan=True,
            )
        if models_cfg.run_ebm_if_available and _has("interpret"):
            from interpret.glassbox import ExplainableBoostingClassifier

            zoo["explainable_boosting"] = ModelSpec(
                name="explainable_boosting",
                factory=lambda p: ExplainableBoostingClassifier(
                    interactions=p.get("interactions", 0),
                    random_state=p.get("random_state", seed),
                ),
                supports_nan=True,
            )
    else:
        zoo["ridge"] = ModelSpec(
            name="ridge",
            factory=lambda p: Ridge(alpha=p.get("alpha", 1.0), random_state=p.get("random_state", seed)),
            search_space={"alpha": ("loguniform", 1e-3, 100.0)},
            needs_scaling=True,
        )
        zoo["elastic_net"] = ModelSpec(
            name="elastic_net",
            factory=lambda p: ElasticNet(
                alpha=p.get("alpha", 0.01),
                l1_ratio=p.get("l1_ratio", 0.5),
                max_iter=5000,
                random_state=p.get("random_state", seed),
            ),
            search_space={"alpha": ("loguniform", 1e-4, 1.0), "l1_ratio": ("uniform", 0.0, 1.0)},
            needs_scaling=True,
        )
        if models_cfg.run_random_forest:
            zoo["random_forest_regressor"] = ModelSpec(
                name="random_forest_regressor",
                factory=lambda p: RandomForestRegressor(
                    n_estimators=p.get("n_estimators", 400),
                    max_depth=p.get("max_depth", 6),
                    min_samples_leaf=p.get("min_samples_leaf", 20),
                    n_jobs=1,
                    random_state=p.get("random_state", seed),
                ),
                search_space={"max_depth": ("int", 2, 12), "min_samples_leaf": ("int", 5, 60)},
            )
        if models_cfg.run_hist_gradient_boosting:
            zoo["hist_gradient_boosting_regressor"] = ModelSpec(
                name="hist_gradient_boosting_regressor",
                factory=lambda p: HistGradientBoostingRegressor(
                    max_iter=p.get("max_iter", 300),
                    learning_rate=p.get("learning_rate", 0.05),
                    max_depth=p.get("max_depth", 3),
                    min_samples_leaf=p.get("min_samples_leaf", 25),
                    early_stopping=False,
                    random_state=p.get("random_state", seed),
                ),
                search_space={"learning_rate": ("loguniform", 0.01, 0.2), "max_depth": ("int", 2, 6)},
                supports_nan=True,
            )

    if _SKIPPED:
        logger.info("Optional model backends unavailable, skipped: %s", sorted(set(_SKIPPED)))
    logger.info("Model zoo for %s: %s", task, list(zoo))
    return zoo


def available_models(config: Any) -> dict[str, list[str]]:
    return {
        "classification": list(build_model_zoo(config, "classification")),
        "regression": list(build_model_zoo(config, "regression")),
    }


def sample_weights_from_labels(y: np.ndarray, scheme: str | None = "balanced") -> np.ndarray | None:
    """Per-observation weights for estimators without a `class_weight` argument."""
    if scheme != "balanced":
        return None
    y = np.asarray(y, dtype=float)
    positives = np.nansum(y)
    negatives = y.size - positives
    if positives == 0 or negatives == 0:
        return None
    weight_positive = y.size / (2.0 * positives)
    weight_negative = y.size / (2.0 * negatives)
    return np.where(y > 0.5, weight_positive, weight_negative)
