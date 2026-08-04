"""Calibration diagnostics.

A stress probability that is well ranked but badly calibrated is dangerous on a
public dashboard: "35% chance of a 5% drawdown" must actually mean 35%. Hence
ECE, MCE, calibration slope/intercept and the Murphy decomposition of the Brier
score are all reported, not just AUROC.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def reliability_table(
    y_true: np.ndarray, probabilities: np.ndarray, n_bins: int = 10, strategy: str = "quantile"
) -> pd.DataFrame:
    """Binned observed frequency vs mean predicted probability."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], p[mask]
    if y.size < n_bins:
        return pd.DataFrame(columns=["bin", "n", "mean_predicted", "observed_frequency", "gap"])

    if strategy == "quantile":
        edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
        if edges.size < 3:
            edges = np.linspace(0, 1, n_bins + 1)
    else:
        edges = np.linspace(0, 1, n_bins + 1)

    bins = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        selected = bins == b
        if selected.sum() == 0:
            continue
        mean_predicted = float(p[selected].mean())
        observed = float(y[selected].mean())
        rows.append(
            {
                "bin": b,
                "bin_lower": float(edges[b]),
                "bin_upper": float(edges[b + 1]),
                "n": int(selected.sum()),
                "mean_predicted": mean_predicted,
                "observed_frequency": observed,
                "gap": observed - mean_predicted,
            }
        )
    return pd.DataFrame(rows)


def calibration_metrics(
    y_true: np.ndarray, probabilities: np.ndarray, n_bins: int = 10
) -> dict[str, Any]:
    """ECE, MCE, calibration slope/intercept and the Brier decomposition."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], np.clip(p[mask], 1e-7, 1 - 1e-7)

    if y.size < 20 or len(set(y)) < 2:
        return {"n": int(y.size), "note": "insufficient data for calibration metrics"}

    table = reliability_table(y, p, n_bins=n_bins)
    weights = table["n"] / table["n"].sum() if not table.empty else pd.Series(dtype=float)
    ece = float((weights * table["gap"].abs()).sum()) if not table.empty else np.nan
    mce = float(table["gap"].abs().max()) if not table.empty else np.nan

    # Calibration slope/intercept: logistic regression of y on the logit of p.
    # Slope 1 / intercept 0 is perfect; slope < 1 means over-confident.
    slope = intercept = np.nan
    try:
        from sklearn.linear_model import LogisticRegression

        logit = np.log(p / (1 - p)).reshape(-1, 1)
        model = LogisticRegression(solver="lbfgs", max_iter=1000)
        model.fit(logit, y)
        slope = float(model.coef_[0][0])
        intercept = float(model.intercept_[0])
    except Exception as exc:
        logger.debug("Calibration slope fit failed: %s", exc)

    decomposition = brier_decomposition(y, p, n_bins=n_bins)

    return {
        "n": int(y.size),
        "expected_calibration_error": ece,
        "maximum_calibration_error": mce,
        "calibration_slope": slope,
        "calibration_intercept": intercept,
        "mean_predicted": float(p.mean()),
        "observed_base_rate": float(y.mean()),
        "calibration_bias": float(p.mean() - y.mean()),
        **decomposition,
    }


def brier_decomposition(
    y_true: np.ndarray, probabilities: np.ndarray, n_bins: int = 10
) -> dict[str, float]:
    r"""Murphy decomposition: Brier = reliability - resolution + uncertainty.

    * reliability: how far bin frequencies sit from bin predictions (lower better)
    * resolution:  how much bins differ from the base rate (higher better)
    * uncertainty: base_rate * (1 - base_rate), a property of the problem
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], p[mask]
    if y.size < n_bins:
        return {"brier_reliability": np.nan, "brier_resolution": np.nan, "brier_uncertainty": np.nan}

    base_rate = y.mean()
    edges = np.linspace(0, 1, n_bins + 1)
    bins = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)

    reliability = resolution = 0.0
    for b in range(n_bins):
        selected = bins == b
        n = int(selected.sum())
        if n == 0:
            continue
        mean_predicted = p[selected].mean()
        observed = y[selected].mean()
        reliability += n * (mean_predicted - observed) ** 2
        resolution += n * (observed - base_rate) ** 2

    total = y.size
    return {
        "brier_reliability": float(reliability / total),
        "brier_resolution": float(resolution / total),
        "brier_uncertainty": float(base_rate * (1 - base_rate)),
    }


def probability_histogram(probabilities: np.ndarray, n_bins: int = 20) -> pd.DataFrame:
    p = np.asarray(probabilities, dtype=float)
    p = p[~np.isnan(p)]
    counts, edges = np.histogram(p, bins=n_bins, range=(0.0, 1.0))
    return pd.DataFrame(
        {"bin_lower": edges[:-1], "bin_upper": edges[1:], "count": counts}
    )
