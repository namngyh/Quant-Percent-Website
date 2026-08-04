"""Explainable Boosting Machine forecaster."""

from __future__ import annotations

import numpy as np
import pandas as pd
from interpret.glassbox import ExplainableBoostingClassifier
from sklearn.ensemble import HistGradientBoostingClassifier

from raemf_mc.models.base import align_proba, class_weights


class EBMForecaster:
    """Multiclass EBM with a sklearn fallback if interpret fails."""

    def __init__(self, random_state: int = 42, **params: object) -> None:
        self.random_state = random_state
        self.params = params
        self.model: object | None = None
        self.warning: str | None = None
        self.feature_names: list[str] = []

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "EBMForecaster":
        self.feature_names = list(x.columns)
        sw = class_weights(y)
        try:
            self.model = ExplainableBoostingClassifier(
                random_state=self.random_state,
                max_bins=int(self.params.get("max_bins", 128)),
                interactions=int(self.params.get("interactions", 5)),
                learning_rate=float(self.params.get("learning_rate", 0.03)),
                max_rounds=int(self.params.get("max_rounds", 120)),
                outer_bags=int(self.params.get("outer_bags", 2)),
                min_samples_leaf=int(self.params.get("min_samples_leaf", 2)),
                n_jobs=1,
            )
            self.model.fit(x, y, sample_weight=sw)
        except Exception as exc:  # pragma: no cover - depends on interpret
            self.warning = f"EBM failed; HistGradientBoosting fallback used: {exc}"
            self.model = HistGradientBoostingClassifier(random_state=self.random_state, max_iter=150, learning_rate=0.05)
            self.model.fit(x, y, sample_weight=sw)
        return self

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        assert self.model is not None
        return align_proba(getattr(self.model, "classes_"), self.model.predict_proba(x))

    def importance(self) -> pd.DataFrame:
        if self.model is not None and hasattr(self.model, "term_importances"):
            try:
                vals = np.asarray(self.model.term_importances())
                names = getattr(self.model, "term_names_", self.feature_names[: len(vals)])
                return pd.DataFrame({"feature": names, "importance": vals}).sort_values("importance", ascending=False)
            except Exception:
                pass
        return pd.DataFrame({"feature": self.feature_names, "importance": np.nan})
