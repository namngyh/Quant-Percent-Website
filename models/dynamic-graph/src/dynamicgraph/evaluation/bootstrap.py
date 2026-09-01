r"""Block-bootstrap confidence intervals.

Daily financial series are autocorrelated and volatility-clustered, so an i.i.d.
bootstrap over rows understates uncertainty badly -- often by a factor of two or
more. Every interval here comes from a moving-block or stationary bootstrap that
preserves local dependence.

The paired version resamples the SAME blocks for two models, which is the right
way to test whether graph features beat a market-only baseline: it removes the
shared "was this a quiet year?" variation.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def _block_indices(
    n: int, block_length: int, rng: np.random.Generator, stationary: bool = False
) -> np.ndarray:
    if stationary:
        p = 1.0 / max(1.0, block_length)
        indices = np.empty(n, dtype=int)
        current = int(rng.integers(0, n))
        for t in range(n):
            indices[t] = current
            current = int(rng.integers(0, n)) if rng.random() < p else (current + 1) % n
        return indices

    block_length = max(1, min(block_length, n))
    n_blocks = int(np.ceil(n / block_length))
    starts = rng.integers(0, n - block_length + 1, size=n_blocks)
    return np.concatenate([np.arange(s, s + block_length) for s in starts])[:n]


def _grouped_block_indices(
    groups: np.ndarray,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Resample blocks inside groups so no synthetic block crosses a fold."""
    labels = np.asarray(groups)
    ordered_labels = pd.unique(labels)
    sampled: list[np.ndarray] = []
    for label in ordered_labels:
        positions = np.flatnonzero(labels == label)
        local = _block_indices(len(positions), block_length, rng)
        sampled.append(positions[local])
    return np.concatenate(sampled) if sampled else np.array([], dtype=int)


def block_bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    n_bootstrap: int = 500,
    block_length: int = 20,
    alpha: float = 0.05,
    seed: int = 42,
    stationary: bool = False,
) -> dict[str, float]:
    """Percentile CI for a metric under a block bootstrap."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(p)
    y, p = y[mask], p[mask]
    n = y.size
    if n < 30 or n_bootstrap <= 0:
        try:
            point = float(metric_fn(y, p))
        except Exception:
            point = np.nan
        return {"point": point, "lower": np.nan, "upper": np.nan, "n_bootstrap": 0, "n": int(n)}

    try:
        point = float(metric_fn(y, p))
    except Exception:
        point = np.nan

    rng = np.random.default_rng(seed)
    samples: list[float] = []
    for _ in range(n_bootstrap):
        indices = _block_indices(n, block_length, rng, stationary=stationary)
        try:
            value = float(metric_fn(y[indices], p[indices]))
        except Exception:
            continue
        if np.isfinite(value):
            samples.append(value)

    if len(samples) < 20:
        return {"point": point, "lower": np.nan, "upper": np.nan, "n_bootstrap": len(samples), "n": int(n)}

    values = np.asarray(samples)
    return {
        "point": point,
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)),
        "lower": float(np.quantile(values, alpha / 2)),
        "upper": float(np.quantile(values, 1 - alpha / 2)),
        "n_bootstrap": len(samples),
        "n": int(n),
        "block_length": int(block_length),
    }


def paired_bootstrap_difference(
    y_true: np.ndarray,
    pred_a: np.ndarray,
    pred_b: np.ndarray,
    metric_fn: Callable[[np.ndarray, np.ndarray], float],
    n_bootstrap: int = 500,
    block_length: int = 20,
    alpha: float = 0.05,
    seed: int = 42,
    higher_is_better: bool = True,
    groups: np.ndarray | None = None,
) -> dict[str, Any]:
    """CI and one-sided p-value for `metric(A) - metric(B)` on identical blocks."""
    y = np.asarray(y_true, dtype=float)
    a = np.asarray(pred_a, dtype=float)
    b = np.asarray(pred_b, dtype=float)
    mask = ~np.isnan(y) & ~np.isnan(a) & ~np.isnan(b)
    group_values = np.asarray(groups)[mask] if groups is not None else None
    y, a, b = y[mask], a[mask], b[mask]
    n = y.size

    def _safe(fn, *args) -> float:
        try:
            value = float(fn(*args))
            return value if np.isfinite(value) else np.nan
        except Exception:
            return np.nan

    point_a, point_b = _safe(metric_fn, y, a), _safe(metric_fn, y, b)
    difference = point_a - point_b

    if n < 30 or n_bootstrap <= 0:
        return {
            "metric_a": point_a, "metric_b": point_b, "difference": difference,
            "lower": np.nan, "upper": np.nan, "p_value": np.nan,
            "significant": False, "n": int(n), "n_bootstrap": 0,
        }

    rng = np.random.default_rng(seed)
    differences: list[float] = []
    for _ in range(n_bootstrap):
        indices = (
            _grouped_block_indices(group_values, block_length, rng)
            if group_values is not None
            else _block_indices(n, block_length, rng)
        )
        value_a = _safe(metric_fn, y[indices], a[indices])
        value_b = _safe(metric_fn, y[indices], b[indices])
        if np.isfinite(value_a) and np.isfinite(value_b):
            differences.append(value_a - value_b)

    if len(differences) < 20:
        return {
            "metric_a": point_a, "metric_b": point_b, "difference": difference,
            "lower": np.nan, "upper": np.nan, "p_value": np.nan,
            "significant": False, "n": int(n), "n_bootstrap": len(differences),
        }

    values = np.asarray(differences)
    lower = float(np.quantile(values, alpha / 2))
    upper = float(np.quantile(values, 1 - alpha / 2))
    # Approximate the null distribution by centring bootstrap errors at zero.
    # Counting the signs of the uncentred distribution is not a valid test: it
    # remains centred on the observed effect under the alternative.
    null_values = values - difference
    extreme = (
        np.count_nonzero(null_values >= difference)
        if higher_is_better
        else np.count_nonzero(null_values <= difference)
    )
    p_value = float((extreme + 1) / (len(null_values) + 1))

    return {
        "metric_a": point_a,
        "metric_b": point_b,
        "difference": difference,
        "difference_mean": float(values.mean()),
        "lower": lower,
        "upper": upper,
        "p_value": p_value,
        "significant": bool((lower > 0) if higher_is_better else (upper < 0)),
        "n": int(n),
        "n_bootstrap": len(values),
        "block_length": int(block_length),
    }


def paired_series_bootstrap(
    series_a: pd.Series,
    series_b: pd.Series,
    statistic: Callable[[np.ndarray], float],
    n_bootstrap: int = 1000,
    block_length: int = 20,
    alpha: float = 0.05,
    seed: int = 42,
    lower_is_better: bool = False,
) -> dict[str, Any]:
    """CI and p-value for `statistic(A) - statistic(B)` on two aligned series.

    Unlike `paired_bootstrap_difference` this takes the two outcome series
    directly rather than predictions against a shared label, which is what a
    portfolio comparison needs: there is no `y_true`, only two realised return
    streams. Resampling the SAME blocks from both removes the common market
    variation, so the interval reflects the difference between the rules rather
    than whether the sample period happened to be calm.

    Set `lower_is_better` for statistics like realised volatility, where A beats
    B when the difference is negative.
    """
    frame = pd.concat([series_a, series_b], axis=1, join="inner").dropna()
    if frame.shape[1] != 2:
        raise ValueError("Expected exactly two aligned series.")
    a = frame.iloc[:, 0].to_numpy(dtype=float)
    b = frame.iloc[:, 1].to_numpy(dtype=float)
    n = a.size

    def _safe(values: np.ndarray) -> float:
        try:
            value = float(statistic(values))
            return value if np.isfinite(value) else np.nan
        except Exception:
            return np.nan

    point_a, point_b = _safe(a), _safe(b)
    difference = point_a - point_b
    base = {
        "statistic_a": point_a,
        "statistic_b": point_b,
        "difference": difference,
        "n": int(n),
        "lower_is_better": bool(lower_is_better),
    }
    if n < 30 or n_bootstrap <= 0:
        return {**base, "lower": np.nan, "upper": np.nan, "p_value": np.nan, "significant": False,
                "n_bootstrap": 0}

    rng = np.random.default_rng(seed)
    differences: list[float] = []
    for _ in range(n_bootstrap):
        indices = _block_indices(n, block_length, rng)
        value = _safe(a[indices]) - _safe(b[indices])
        if np.isfinite(value):
            differences.append(value)

    if len(differences) < 20:
        return {**base, "lower": np.nan, "upper": np.nan, "p_value": np.nan, "significant": False,
                "n_bootstrap": len(differences)}

    values = np.asarray(differences)
    lower = float(np.quantile(values, alpha / 2))
    upper = float(np.quantile(values, 1 - alpha / 2))
    null_values = values - difference
    extreme = (
        np.count_nonzero(null_values <= difference)
        if lower_is_better
        else np.count_nonzero(null_values >= difference)
    )
    p_value = float((extreme + 1) / (len(null_values) + 1))
    return {
        **base,
        "difference_mean": float(values.mean()),
        "lower": lower,
        "upper": upper,
        "p_value": p_value,
        "significant": bool((upper < 0) if lower_is_better else (lower > 0)),
        "n_bootstrap": len(values),
        "block_length": int(block_length),
    }


def bootstrap_series_ci(
    series: pd.Series,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_bootstrap: int = 500,
    block_length: int = 20,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict[str, float]:
    """CI for a statistic of a single time series (e.g. mean rank IC)."""
    values = series.dropna().to_numpy(dtype=float)
    n = values.size
    if n < 20:
        return {"point": float(statistic(values)) if n else np.nan, "lower": np.nan, "upper": np.nan, "n": int(n)}

    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n_bootstrap):
        indices = _block_indices(n, block_length, rng)
        samples.append(float(statistic(values[indices])))
    resampled = np.asarray(samples)
    return {
        "point": float(statistic(values)),
        "lower": float(np.quantile(resampled, alpha / 2)),
        "upper": float(np.quantile(resampled, 1 - alpha / 2)),
        "std": float(resampled.std(ddof=1)),
        "n": int(n),
        "n_bootstrap": n_bootstrap,
    }
