"""Probability calibration.

Calibrators are fitted on the fold's VALIDATION block only -- never on training
(the model is already over-confident there) and never on test (that would be
leakage). When a fold's validation block has too few positives for isotonic
regression to be stable, the code falls back to Platt scaling and records the
fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

MIN_POSITIVES_FOR_ISOTONIC = 25


@dataclass
class CalibratedModel:
    """A fitted estimator plus its fitted probability calibrator."""

    estimator: Any
    calibrator: Any | None = None
    method: str = "none"
    decision_threshold: float = 0.5
    feature_names: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, X: Any) -> np.ndarray:
        raw = _raw_probability(self.estimator, X)
        if self.calibrator is None:
            return raw
        return np.clip(self.calibrator.predict(raw.reshape(-1, 1)).ravel()
                       if hasattr(self.calibrator, "predict") and self.method == "isotonic"
                       else self.calibrator.predict_proba(raw.reshape(-1, 1))[:, 1], 1e-6, 1 - 1e-6)

    def predict(self, X: Any) -> np.ndarray:
        return (self.predict_proba(X) >= self.decision_threshold).astype(int)


def _raw_probability(estimator: Any, X: Any) -> np.ndarray:
    if hasattr(estimator, "predict_proba"):
        proba = estimator.predict_proba(X)
        return np.asarray(proba)[:, 1] if np.ndim(proba) > 1 else np.asarray(proba).ravel()
    if hasattr(estimator, "decision_function"):
        scores = np.asarray(estimator.decision_function(X)).ravel()
        return 1.0 / (1.0 + np.exp(-scores))
    return np.asarray(estimator.predict(X), dtype=float).ravel()


def calibrate(
    estimator: Any,
    X_validation: Any,
    y_validation: np.ndarray,
    method: str = "isotonic",
    feature_names: list[str] | None = None,
) -> CalibratedModel:
    """Fit a calibrator on the validation block."""
    y = np.asarray(y_validation, dtype=float)
    mask = ~np.isnan(y)
    y = y[mask]
    X = X_validation[mask] if hasattr(X_validation, "__getitem__") else X_validation
    if hasattr(X_validation, "iloc"):
        X = X_validation.iloc[mask]

    raw = _raw_probability(estimator, X)
    positives = int(np.nansum(y))
    chosen = str(method).lower()
    note = ""

    if chosen == "none" or y.size < 20 or positives < 3 or positives == y.size:
        if chosen != "none":
            note = (
                f"calibration skipped: {positives} positive(s) in {y.size} validation observation(s)"
            )
            logger.warning("%s; returning uncalibrated probabilities.", note)
        return CalibratedModel(
            estimator=estimator, calibrator=None, method="none",
            feature_names=feature_names or [], metadata={"note": note},
        )

    if chosen == "isotonic" and positives < MIN_POSITIVES_FOR_ISOTONIC:
        note = (
            f"isotonic needs >= {MIN_POSITIVES_FOR_ISOTONIC} positives, got {positives}; "
            "fell back to Platt scaling"
        )
        logger.info("%s.", note)
        chosen = "sigmoid"

    if chosen == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(raw, y)
    elif chosen in {"sigmoid", "platt"}:
        from sklearn.linear_model import LogisticRegression

        calibrator = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        calibrator.fit(raw.reshape(-1, 1), y)
        chosen = "sigmoid"
    elif chosen == "beta":
        calibrator = _BetaCalibrator().fit(raw, y)
    else:
        raise ValueError(f"Unknown calibration method `{method}`.")

    return CalibratedModel(
        estimator=estimator,
        calibrator=calibrator,
        method=chosen,
        feature_names=feature_names or [],
        metadata={"n_validation": int(y.size), "n_positives": positives, "note": note},
    )


class _BetaCalibrator:
    """Kull et al. beta calibration: logistic regression on (log p, log(1-p))."""

    def __init__(self) -> None:
        self.model: Any = None

    def fit(self, p: np.ndarray, y: np.ndarray) -> "_BetaCalibrator":
        from sklearn.linear_model import LogisticRegression

        p = np.clip(p, 1e-6, 1 - 1e-6)
        design = np.column_stack([np.log(p), -np.log(1 - p)])
        self.model = LogisticRegression(solver="lbfgs", max_iter=1000)
        self.model.fit(design, y)
        return self

    def predict_proba(self, p: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(p).ravel(), 1e-6, 1 - 1e-6)
        design = np.column_stack([np.log(p), -np.log(1 - p)])
        return self.model.predict_proba(design)


def optimize_threshold(
    probabilities: np.ndarray,
    y_true: np.ndarray,
    objective: str = "f1",
    fixed: float = 0.5,
    max_false_alarms_per_year: float | None = None,
    n_days: int | None = None,
) -> tuple[float, dict[str, float]]:
    """Pick a decision threshold on the VALIDATION block.

    `max_false_alarms_per_year` adds an operating constraint: among thresholds
    that keep the false-alarm rate acceptable, take the one maximising the
    objective. That is usually what a market-stress dashboard actually needs.
    """
    from sklearn.metrics import balanced_accuracy_score, f1_score, matthews_corrcoef

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], p[mask]

    if objective == "fixed" or y.size < 20 or y.sum() == 0:
        return float(fixed), {"objective": objective, "note": "insufficient data; used fixed threshold"}

    scorers = {
        "f1": lambda yt, yp: f1_score(yt, yp, zero_division=0),
        "mcc": lambda yt, yp: matthews_corrcoef(yt, yp) if len(set(yp)) > 1 else 0.0,
        "balanced_accuracy": balanced_accuracy_score,
    }
    scorer = scorers.get(objective, scorers["f1"])

    candidates = np.unique(np.quantile(p, np.linspace(0.02, 0.98, 97)))
    best_threshold, best_score = float(fixed), -np.inf
    for threshold in candidates:
        predicted = (p >= threshold).astype(int)
        if max_false_alarms_per_year is not None and n_days:
            false_positives = int(((predicted == 1) & (y == 0)).sum())
            per_year = false_positives * 252.0 / n_days
            if per_year > max_false_alarms_per_year:
                continue
        try:
            score = float(scorer(y, predicted))
        except Exception:
            continue
        if score > best_score:
            best_score, best_threshold = score, float(threshold)

    if not np.isfinite(best_score):
        return float(fixed), {"objective": objective, "note": "no feasible threshold; used fixed"}
    return best_threshold, {"objective": objective, "score": best_score}


def calibration_summary(probabilities: np.ndarray, y_true: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Reliability table: mean predicted vs observed frequency per bin."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(y_true, dtype=float)
    mask = ~np.isnan(p) & ~np.isnan(y)
    p, y = p[mask], y[mask]
    if p.size == 0:
        return pd.DataFrame(columns=["bin", "n", "mean_predicted", "observed_frequency"])

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        selected = bins == b
        if not selected.any():
            continue
        rows.append(
            {
                "bin": b,
                "bin_lower": float(edges[b]),
                "bin_upper": float(edges[b + 1]),
                "n": int(selected.sum()),
                "mean_predicted": float(p[selected].mean()),
                "observed_frequency": float(y[selected].mean()),
            }
        )
    return pd.DataFrame(rows)
