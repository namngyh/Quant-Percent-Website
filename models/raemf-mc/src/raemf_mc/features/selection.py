"""Leakage-safe feature selection."""

from __future__ import annotations

import numpy as np
import pandas as pd


def select_features(
    features: pd.DataFrame,
    train_index: pd.Index | list[int],
    missing_threshold: float = 0.4,
    corr_threshold: float = 0.98,
) -> tuple[list[str], pd.DataFrame]:
    """Select features using train rows only."""
    train = features.loc[train_index]
    removed: list[dict[str, str]] = []
    selected = list(features.columns)
    miss = train[selected].isna().mean()
    for col, rate in miss.items():
        if rate > missing_threshold:
            removed.append({"feature": col, "reason": f"missing_rate={rate:.3f}"})
    selected = [c for c in selected if c not in {r["feature"] for r in removed}]
    nunique = train[selected].nunique(dropna=True)
    for col, n in nunique.items():
        if n <= 1:
            removed.append({"feature": col, "reason": "near_constant"})
    selected = [c for c in selected if c not in {r["feature"] for r in removed}]
    if len(selected) > 1:
        corr = train[selected].corr(numeric_only=True).abs()
        upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
        drop = [column for column in upper.columns if any(upper[column] > corr_threshold)]
        for col in drop:
            removed.append({"feature": col, "reason": f"abs_corr_gt_{corr_threshold}"})
        selected = [c for c in selected if c not in set(drop)]
    return selected, pd.DataFrame(removed)
