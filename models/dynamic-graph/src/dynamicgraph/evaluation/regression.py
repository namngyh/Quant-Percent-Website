"""Regression evaluation helpers (thin wrappers used by the node-level and
ranking tasks)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.evaluation.classification import regression_metrics

__all__ = ["regression_metrics", "regression_metrics_by_period", "residual_diagnostics"]


def regression_metrics_by_period(
    y_true: pd.Series, y_pred: pd.Series, freq: str = "YE"
) -> pd.DataFrame:
    """Metrics recomputed per calendar period - a stability check over time."""
    frame = pd.DataFrame({"y": y_true, "p": y_pred}).dropna()
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for period, group in frame.groupby(pd.Grouper(freq=freq)):
        if len(group) < 20:
            continue
        metrics = regression_metrics(group["y"].to_numpy(), group["p"].to_numpy())
        metrics["period"] = str(period.date())
        rows.append(metrics)
    return pd.DataFrame(rows)


def residual_diagnostics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Residual mean/std/skew/kurtosis and a Ljung-Box autocorrelation check."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    residuals = y[mask] - p[mask]
    if residuals.size < 20:
        return {"n": int(residuals.size)}

    from scipy.stats import kurtosis, skew

    out: dict[str, Any] = {
        "n": int(residuals.size),
        "residual_mean": float(residuals.mean()),
        "residual_std": float(residuals.std(ddof=1)),
        "residual_skew": float(skew(residuals)),
        "residual_excess_kurtosis": float(kurtosis(residuals, fisher=True)),
    }
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox

        test = acorr_ljungbox(residuals, lags=[10], return_df=True)
        out["ljung_box_p_lag10"] = float(test["lb_pvalue"].iloc[0])
        out["residual_autocorrelation_flag"] = bool(out["ljung_box_p_lag10"] < 0.05)
    except Exception:
        out["ljung_box_p_lag10"] = np.nan
    return out
