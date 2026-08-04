"""Regime diagnostics."""

from __future__ import annotations

import pandas as pd


def state_diagnostics(probabilities: pd.DataFrame) -> pd.DataFrame:
    """Summarize filtered HMM state occupancy."""
    cols = [c for c in probabilities.columns if c.startswith("hmm_prob_state_")]
    return pd.DataFrame({"state": cols, "mean_probability": probabilities[cols].mean().to_numpy()})
