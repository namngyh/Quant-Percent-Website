"""Random Forest multiclass forecaster."""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from raemf_mc.models.base import align_proba


class RandomForestForecaster:
    def __init__(self, random_state: int = 42, **params: object) -> None:
        self.model = RandomForestClassifier(
            n_estimators=int(params.get("n_estimators", 240)),
            max_depth=int(params.get("max_depth", 6)),
            class_weight="balanced_subsample",
            min_samples_leaf=5,
            n_jobs=1,
            random_state=random_state,
        )

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "RandomForestForecaster":
        self.model.fit(x, y.astype(str))
        return self

    def predict_proba(self, x: pd.DataFrame):
        return align_proba(self.model.classes_, self.model.predict_proba(x))

    def importance(self) -> pd.DataFrame:
        return pd.DataFrame({"feature": self.model.feature_names_in_, "importance": self.model.feature_importances_}).sort_values("importance", ascending=False)
