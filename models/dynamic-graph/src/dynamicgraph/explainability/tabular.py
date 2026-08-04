"""Explainability for the tabular models.

Permutation importance is computed on OOS data (that is the only place where
"importance" means anything predictive). SHAP is optional and degrades to a
warning when the package is absent.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def permutation_importance_frame(
    model: Any,
    X: pd.DataFrame,
    y: pd.Series,
    n_repeats: int = 10,
    scoring: str = "neg_brier_score",
    seed: int = 42,
    max_features: int = 40,
) -> pd.DataFrame:
    """Permutation importance on held-out data.

    Interpretation: "permuting this column degrades OOS prediction by X".
    That is predictive importance, not a causal effect.
    """
    from sklearn.inspection import permutation_importance

    mask = y.notna() & X.notna().any(axis=1)
    X_used, y_used = X[mask], y[mask]
    if len(X_used) < 50:
        return pd.DataFrame(columns=["feature", "importance_mean", "importance_std"])

    estimator = getattr(model, "estimator", model)
    try:
        result = permutation_importance(
            estimator, X_used, y_used, n_repeats=n_repeats, random_state=seed, scoring=scoring, n_jobs=1
        )
    except Exception as exc:
        logger.warning("Permutation importance failed: %s", exc)
        return pd.DataFrame(columns=["feature", "importance_mean", "importance_std"])

    frame = pd.DataFrame(
        {
            "feature": X_used.columns,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        }
    )
    frame["claim_level"] = "predictive_importance"
    return frame.sort_values("importance_mean", ascending=False).head(max_features).reset_index(drop=True)


def logistic_coefficients(model: Any, feature_names: list[str]) -> pd.DataFrame:
    """Standardised logistic coefficients, when the estimator exposes them."""
    estimator = getattr(model, "estimator", model)
    inner = estimator.named_steps.get("model") if hasattr(estimator, "named_steps") else estimator
    if not hasattr(inner, "coef_"):
        return pd.DataFrame(columns=["feature", "coefficient"])

    coefficients = np.asarray(inner.coef_).ravel()
    if coefficients.size != len(feature_names):
        return pd.DataFrame(columns=["feature", "coefficient"])

    frame = pd.DataFrame({"feature": feature_names, "coefficient": coefficients})
    frame["abs_coefficient"] = frame["coefficient"].abs()
    frame["odds_ratio"] = np.exp(frame["coefficient"])
    frame["claim_level"] = "association"
    frame["note"] = "Coefficients are conditional associations within the fitted model, not effects."
    return frame.sort_values("abs_coefficient", ascending=False).reset_index(drop=True)


def shap_values_frame(
    model: Any, X: pd.DataFrame, max_samples: int = 300, seed: int = 42
) -> pd.DataFrame:
    """Mean |SHAP| per feature. Returns an empty frame when SHAP is unavailable."""
    try:
        import shap
    except ImportError:
        logger.info("SHAP not installed; skipping SHAP explanations (optional extra `explain`).")
        return pd.DataFrame(columns=["feature", "mean_abs_shap"])

    estimator = getattr(model, "estimator", model)
    sample = X.dropna(how="all")
    if len(sample) > max_samples:
        sample = sample.sample(max_samples, random_state=seed).sort_index()
    if sample.empty:
        return pd.DataFrame(columns=["feature", "mean_abs_shap"])

    try:
        inner = estimator.named_steps["model"] if hasattr(estimator, "named_steps") else estimator
        transformed = sample
        if hasattr(estimator, "named_steps"):
            for name, step in estimator.named_steps.items():
                if name == "model":
                    break
                transformed = step.transform(transformed)
            transformed = pd.DataFrame(transformed, index=sample.index, columns=sample.columns)

        explainer = shap.Explainer(inner, transformed)
        values = explainer(transformed)
        matrix = values.values
        if matrix.ndim == 3:
            matrix = matrix[:, :, -1]
        frame = pd.DataFrame(
            {"feature": sample.columns, "mean_abs_shap": np.abs(matrix).mean(axis=0)}
        )
        frame["claim_level"] = "predictive_importance"
        return frame.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    except Exception as exc:
        logger.warning("SHAP computation failed: %s", exc)
        return pd.DataFrame(columns=["feature", "mean_abs_shap"])


def partial_dependence_frame(
    model: Any, X: pd.DataFrame, features: list[str], grid_resolution: int = 20
) -> pd.DataFrame:
    """One-way partial dependence for a handful of features."""
    from sklearn.inspection import partial_dependence

    estimator = getattr(model, "estimator", model)
    clean = X.dropna(how="all")
    if clean.empty:
        return pd.DataFrame()

    rows = []
    for feature in features:
        if feature not in clean.columns:
            continue
        try:
            result = partial_dependence(
                estimator, clean, [list(clean.columns).index(feature)],
                grid_resolution=grid_resolution, kind="average",
            )
            for value, average in zip(result["grid_values"][0], result["average"][0]):
                rows.append({"feature": feature, "value": float(value), "partial_dependence": float(average)})
        except Exception as exc:
            logger.debug("Partial dependence failed for %s: %s", feature, exc)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["claim_level"] = "association"
    return frame


def per_prediction_contributions(
    model: Any, X_row: pd.Series, feature_names: list[str]
) -> pd.DataFrame:
    """Linear-model contribution decomposition for a single prediction."""
    estimator = getattr(model, "estimator", model)
    inner = estimator.named_steps.get("model") if hasattr(estimator, "named_steps") else estimator
    if not hasattr(inner, "coef_"):
        return pd.DataFrame(columns=["feature", "contribution"])

    values = X_row.reindex(feature_names)
    if hasattr(estimator, "named_steps") and "scale" in estimator.named_steps:
        scaler = estimator.named_steps["scale"]
        values = pd.Series(
            (values.to_numpy(dtype=float) - scaler.mean_) / np.sqrt(scaler.var_ + 1e-12),
            index=feature_names,
        )
    coefficients = np.asarray(inner.coef_).ravel()
    contributions = coefficients * values.fillna(0.0).to_numpy()

    frame = pd.DataFrame({"feature": feature_names, "contribution": contributions})
    frame["abs_contribution"] = frame["contribution"].abs()
    return frame.sort_values("abs_contribution", ascending=False).reset_index(drop=True)
