"""Risk diagnostics."""

from __future__ import annotations

import pandas as pd


def volatility_summary(features: pd.DataFrame) -> dict[str, float]:
    """Summarize conditional volatility features."""
    sigma = features["egarch_sigma"].dropna()
    return {"mean_sigma": float(sigma.mean()), "p95_sigma": float(sigma.quantile(0.95))}
