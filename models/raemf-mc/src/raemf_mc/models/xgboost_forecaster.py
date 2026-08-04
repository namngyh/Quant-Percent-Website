"""XGBoost multiclass forecaster."""

from __future__ import annotations

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from raemf_mc import CLASS_ORDER
from raemf_mc.models.base import align_proba, class_weights


class XGBoostForecaster:
    def __init__(self, random_state: int = 42, **params: object) -> None:
        self.random_state = random_state
        self.params = params
        self.model: XGBClassifier | None = None
        self.classes_: list[str] = CLASS_ORDER

    def fit(self, x: pd.DataFrame, y: pd.Series, x_val: pd.DataFrame | None = None, y_val: pd.Series | None = None) -> "XGBoostForecaster":
        y_codes = y.astype(str).map({c: i for i, c in enumerate(CLASS_ORDER)}).to_numpy()
        sw = class_weights(y)
        self.model = XGBClassifier(
            objective="multi:softprob",
            num_class=len(CLASS_ORDER),
            eval_metric="mlogloss",
            tree_method="hist",
            n_estimators=int(self.params.get("n_estimators", 160)),
            max_depth=int(self.params.get("max_depth", 3)),
            learning_rate=float(self.params.get("learning_rate", 0.04)),
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=1,
            random_state=self.random_state,
        )
        self.model.fit(x, y_codes, sample_weight=sw, verbose=False)
        return self

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        assert self.model is not None
        return align_proba(CLASS_ORDER, self.model.predict_proba(x))

    def importance(self) -> pd.DataFrame:
        assert self.model is not None
        return pd.DataFrame({"feature": self.model.feature_names_in_, "importance": self.model.feature_importances_}).sort_values("importance", ascending=False)
