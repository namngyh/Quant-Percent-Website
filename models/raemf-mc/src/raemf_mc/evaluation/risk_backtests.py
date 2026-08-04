"""VaR coverage tests for chronological exceedance indicators."""

from __future__ import annotations

import numpy as np
from scipy.stats import chi2


def _safe_log(value: float) -> float:
    return float(np.log(np.clip(value, 1e-12, 1.0)))


def kupiec_test(exceedances: np.ndarray, expected_rate: float) -> dict[str, float]:
    """Kupiec unconditional coverage likelihood-ratio test."""
    hits = np.asarray(exceedances, dtype=bool)
    if hits.ndim != 1 or not len(hits) or not 0 < expected_rate < 1:
        raise ValueError("exceedances must be non-empty and expected_rate must be in (0, 1)")
    count = int(hits.sum())
    n = len(hits)
    observed = count / n
    null_log_likelihood = (n - count) * _safe_log(1 - expected_rate) + count * _safe_log(expected_rate)
    fitted_log_likelihood = (n - count) * _safe_log(1 - observed) + count * _safe_log(observed)
    statistic = max(0.0, -2.0 * (null_log_likelihood - fitted_log_likelihood))
    return {
        "observations": float(n),
        "exceedances": float(count),
        "expected_rate": float(expected_rate),
        "observed_rate": float(observed),
        "lr_uc": statistic,
        "p_value_uc": float(chi2.sf(statistic, 1)),
    }


def christoffersen_conditional_coverage_test(
    exceedances: np.ndarray,
    expected_rate: float,
) -> dict[str, float]:
    """Christoffersen independence plus conditional-coverage test."""
    hits = np.asarray(exceedances, dtype=int)
    if hits.ndim != 1 or len(hits) < 2 or not np.isin(hits, [0, 1]).all():
        raise ValueError("exceedances must contain at least two binary observations")
    previous, current = hits[:-1], hits[1:]
    n00 = int(((previous == 0) & (current == 0)).sum())
    n01 = int(((previous == 0) & (current == 1)).sum())
    n10 = int(((previous == 1) & (current == 0)).sum())
    n11 = int(((previous == 1) & (current == 1)).sum())
    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    independent_ll = (n00 + n10) * _safe_log(1 - pi) + (n01 + n11) * _safe_log(pi)
    markov_ll = n00 * _safe_log(1 - pi0) + n01 * _safe_log(pi0) + n10 * _safe_log(1 - pi1) + n11 * _safe_log(pi1)
    lr_ind = max(0.0, -2.0 * (independent_ll - markov_ll))
    uc = kupiec_test(hits, expected_rate)
    lr_cc = uc["lr_uc"] + lr_ind
    return {
        **uc,
        "n00": float(n00),
        "n01": float(n01),
        "n10": float(n10),
        "n11": float(n11),
        "lr_independence": lr_ind,
        "p_value_independence": float(chi2.sf(lr_ind, 1)),
        "lr_conditional_coverage": lr_cc,
        "p_value_conditional_coverage": float(chi2.sf(lr_cc, 2)),
    }
