"""Proper scores and interval calibration for distribution forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import ndtr


def evaluate_point_forecast(realized: np.ndarray, forecast: np.ndarray) -> dict[str, float]:
    """MAE, RMSE and directional accuracy for chronological return forecasts."""
    actual = np.asarray(realized, dtype=float)
    predicted = np.asarray(forecast, dtype=float)
    if actual.shape != predicted.shape or actual.ndim != 1:
        raise ValueError("realized and forecast must be one-dimensional arrays with the same shape")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Point forecast inputs must be finite")
    error = predicted - actual
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "directional_accuracy": float(np.mean(np.sign(predicted) == np.sign(actual))),
    }


def _crps_ensemble(observation: float, ensemble: np.ndarray) -> float:
    values = np.sort(np.asarray(ensemble, dtype=float))
    n = len(values)
    first = float(np.mean(np.abs(values - observation)))
    coefficients = 2 * np.arange(1, n + 1) - n - 1
    pairwise_half = float(np.sum(coefficients * values) / (n * n))
    return first - pairwise_half


def evaluate_distribution_forecast(
    realized: np.ndarray,
    predictive_samples: np.ndarray,
    levels: tuple[float, ...] = (0.50, 0.80, 0.90, 0.95),
) -> tuple[dict[str, float], pd.DataFrame]:
    """Evaluate one sample distribution per realized chronological outcome."""
    actual = np.asarray(realized, dtype=float)
    samples = np.asarray(predictive_samples, dtype=float)
    if samples.ndim != 2 or samples.shape[0] != len(actual):
        raise ValueError("predictive_samples must have shape (n_forecasts, n_draws)")
    if samples.shape[1] < 2 or not np.isfinite(samples).all() or not np.isfinite(actual).all():
        raise ValueError("Distribution forecast inputs must be finite and contain at least two draws")
    rows: list[dict[str, float]] = []
    for index, observation in enumerate(actual):
        ensemble = samples[index]
        scale = float(np.std(ensemble, ddof=1))
        bandwidth = max(1.06 * scale * len(ensemble) ** (-0.2), 1e-8)
        density = float(np.mean(np.exp(-0.5 * ((observation - ensemble) / bandwidth) ** 2)) / (bandwidth * np.sqrt(2 * np.pi)))
        row = {
            "realized": float(observation),
            "nlpd": -float(np.log(max(density, 1e-300))),
            "crps": _crps_ensemble(float(observation), ensemble),
            "pit": float(np.mean(ensemble <= observation)),
        }
        for level in levels:
            alpha = 1.0 - level
            lower, upper = np.quantile(ensemble, [alpha / 2, 1 - alpha / 2])
            covered = float(lower <= observation <= upper)
            interval_score = (upper - lower) + (2 / alpha) * (lower - observation) * (observation < lower) + (2 / alpha) * (observation - upper) * (observation > upper)
            key = int(round(level * 100))
            row[f"coverage_{key}"] = covered
            row[f"width_{key}"] = float(upper - lower)
            row[f"interval_score_{key}"] = float(interval_score)
        rows.append(row)
    frame = pd.DataFrame(rows)
    summary = {column: float(frame[column].mean()) for column in frame.columns if column != "realized"}
    return summary, frame


def randomized_pit_normal_approximation(
    realized: np.ndarray,
    mean: np.ndarray,
    standard_deviation: np.ndarray,
) -> np.ndarray:
    """PIT helper for Gaussian approximation; useful as a deterministic baseline."""
    actual = np.asarray(realized, dtype=float)
    location = np.asarray(mean, dtype=float)
    scale = np.asarray(standard_deviation, dtype=float)
    if actual.shape != location.shape or actual.shape != scale.shape or np.any(scale <= 0):
        raise ValueError("realized, mean and positive standard_deviation must have the same shape")
    return ndtr((actual - location) / scale)
