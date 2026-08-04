"""Forecast confidence and market filter."""

from __future__ import annotations

import numpy as np

from raemf_mc import CLASS_ORDER


def confidence_label(proba: np.ndarray, hmm_entropy: float, disagreement: float = 0.0) -> str:
    p = np.clip(proba, 1e-12, 1.0)
    ent = float(-(p * np.log(p)).sum())
    maxp = float(p.max())
    if ent > 1.30 or hmm_entropy > 1.30 or disagreement > 0.35:
        return "Uncertain"
    if maxp >= 0.58 and ent < 1.05:
        return "High"
    if maxp >= 0.45:
        return "Medium"
    return "Low"


def market_filter(proba: np.ndarray, confidence: str, cfg: dict[str, float]) -> str:
    bull = float(proba[CLASS_ORDER.index("Bull")])
    bear = float(proba[CLASS_ORDER.index("Bear")])
    stress = float(proba[CLASS_ORDER.index("Stress")])
    side = float(proba[CLASS_ORDER.index("Sideway")])
    if confidence in {"Low", "Uncertain"}:
        return "Uncertain"
    if stress >= cfg.get("stress_threshold", 0.25) or bear >= cfg.get("bear_threshold", 0.35):
        return "Risk-off"
    if bull >= cfg.get("bull_threshold", 0.42) and stress < cfg.get("stress_threshold", 0.25):
        return "Risk-on"
    if side >= max(bull, bear, stress):
        return "Neutral"
    return "Uncertain"
