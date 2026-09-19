"""Leakage-safe sequential conformal calibration for overlapping time-series labels."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .evaluation import historical_var_tests, interval_metrics


@dataclass(frozen=True)
class ConformalSelection:
    method: str
    window: int | None
    validation_table: pd.DataFrame
    reason: str


def eligible_score_indices(target_end_positions: np.ndarray, forecast_origin: int) -> np.ndarray:
    """Return score origins whose target is observable at the current forecast origin."""
    target_end_positions = np.asarray(target_end_positions, dtype=int)
    return np.flatnonzero(target_end_positions <= int(forecast_origin))


def finite_sample_quantile(values: np.ndarray, alpha: float) -> float:
    """Conservative split-conformal upper quantile with the finite-sample correction."""
    values = np.sort(np.asarray(values, dtype=float)[np.isfinite(values)])
    if len(values) == 0:
        raise ValueError("Không có conformal score hữu hạn")
    k = min(int(np.ceil((len(values) + 1) * (1.0 - float(alpha)))), len(values))
    return float(values[max(k - 1, 0)])


def signed_lower_quantile(values: np.ndarray, alpha: float) -> float:
    """Conservative lower-tail quantile for one-sided conformal VaR."""
    values = np.sort(np.asarray(values, dtype=float)[np.isfinite(values)])
    if len(values) == 0:
        raise ValueError("Không có signed conformal score hữu hạn")
    k = max(int(np.floor((len(values) + 1) * float(alpha))), 1)
    return float(values[min(k - 1, len(values) - 1)])


def volatility_bin_edges(volatility: np.ndarray, bins: int) -> np.ndarray:
    values = np.asarray(volatility, dtype=float)
    quantiles = np.linspace(0, 1, int(bins) + 1)[1:-1]
    return np.unique(np.quantile(values[np.isfinite(values)], quantiles))


def assign_volatility_bins(volatility: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.digitize(np.asarray(volatility, dtype=float), np.asarray(edges, dtype=float), right=True)


def _stratum_mask(
    method: str,
    regimes: np.ndarray,
    vol_bins: np.ndarray,
    regime: int,
    vol_bin: int,
    minimum_size: int,
) -> tuple[np.ndarray, str]:
    all_mask = np.ones(len(regimes), dtype=bool)
    regime_mask = regimes == regime
    volatility_mask = vol_bins == vol_bin
    if method == "volatility_regime":
        candidates = [
            (regime_mask & volatility_mask, "regime_x_volatility"),
            (volatility_mask, "volatility"),
            (regime_mask, "regime"),
            (all_mask, "global"),
        ]
    elif method == "volatility_stratified":
        candidates = [(volatility_mask, "volatility"), (all_mask, "global")]
    elif method == "regime_stratified":
        candidates = [(regime_mask, "regime"), (all_mask, "global")]
    else:
        candidates = [(all_mask, "global")]
    for mask, label in candidates:
        if int(mask.sum()) >= int(minimum_size) or label == "global":
            return mask, label
    return all_mask, "global"


def sequential_conformal(
    calibration_actual: np.ndarray,
    calibration_center: np.ndarray,
    calibration_sigma: np.ndarray,
    calibration_regime: np.ndarray,
    calibration_vol_bin: np.ndarray,
    evaluation_actual: np.ndarray,
    evaluation_center: np.ndarray,
    evaluation_sigma: np.ndarray,
    evaluation_regime: np.ndarray,
    evaluation_vol_bin: np.ndarray,
    horizon: int,
    alpha_levels: list[float],
    method: str = "global",
    window: int | None = None,
    minimum_stratum_size: int = 80,
    epsilon: float = 1e-8,
) -> pd.DataFrame:
    """Forecast sequential intervals; evaluation score j enters only at origin j+h."""
    arrays = [
        calibration_actual,
        calibration_center,
        calibration_sigma,
        calibration_regime,
        calibration_vol_bin,
    ]
    cal_actual, cal_center, cal_sigma, cal_regime, cal_bin = map(np.asarray, arrays)
    eval_actual = np.asarray(evaluation_actual, dtype=float)
    eval_center = np.asarray(evaluation_center, dtype=float)
    eval_sigma = np.maximum(np.asarray(evaluation_sigma, dtype=float), epsilon)
    eval_regime = np.asarray(evaluation_regime)
    eval_bin = np.asarray(evaluation_vol_bin)
    signed_scores = (cal_actual - cal_center) / np.maximum(cal_sigma, epsilon)
    score_regimes = cal_regime.copy()
    score_bins = cal_bin.copy()
    rows: list[dict[str, float | int | str]] = []
    for position in range(len(eval_actual)):
        matured_stop = max(position - int(horizon) + 1, 0)
        if matured_stop:
            new_scores = (eval_actual[:matured_stop] - eval_center[:matured_stop]) / eval_sigma[:matured_stop]
            pool_scores = np.concatenate([signed_scores, new_scores])
            pool_regimes = np.concatenate([score_regimes, eval_regime[:matured_stop]])
            pool_bins = np.concatenate([score_bins, eval_bin[:matured_stop]])
        else:
            pool_scores, pool_regimes, pool_bins = signed_scores, score_regimes, score_bins
        if window is not None and len(pool_scores) > int(window):
            pool_scores = pool_scores[-int(window) :]
            pool_regimes = pool_regimes[-int(window) :]
            pool_bins = pool_bins[-int(window) :]
        row = interval_from_scores(
            pool_scores,
            pool_regimes,
            pool_bins,
            method,
            eval_regime[position],
            eval_bin[position],
            float(eval_center[position]),
            float(eval_sigma[position]),
            alpha_levels,
            minimum_stratum_size,
        )
        rows.append({"position": position, **row})
    return pd.DataFrame(rows)


def select_conformal_method(
    actual: np.ndarray,
    center: np.ndarray,
    sigma: np.ndarray,
    regimes: np.ndarray,
    volatility_bins: np.ndarray,
    horizon: int,
    alpha_levels: list[float],
    candidate_windows: list[int | None],
    minimum_stratum_size: int,
) -> ConformalSelection:
    """Select method on a latter validation slice, never on test records."""
    actual = np.asarray(actual, dtype=float)
    center = np.asarray(center, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    regimes = np.asarray(regimes)
    volatility_bins = np.asarray(volatility_bins)
    split = max(int(len(actual) * 0.60), int(horizon) + minimum_stratum_size)
    split = min(split, len(actual) - max(int(horizon) + 20, 1))
    if split <= 0 or split >= len(actual):
        raise ValueError("Validation quá ngắn cho sequential conformal selection")
    methods = ["global", "volatility_stratified", "regime_stratified", "volatility_regime"]
    rows: list[dict[str, float | int | str | bool | None]] = []
    for method in methods:
        for window in candidate_windows:
            result = sequential_conformal(
                actual[:split],
                center[:split],
                sigma[:split],
                regimes[:split],
                volatility_bins[:split],
                actual[split:],
                center[split:],
                sigma[split:],
                regimes[split:],
                volatility_bins[split:],
                horizon,
                alpha_levels,
                method,
                window,
                minimum_stratum_size,
            )
            interval = interval_metrics(actual[split:], result["lower_95"], result["upper_95"], 0.95)
            var = historical_var_tests(actual[split:], result["var_95"], 0.05)
            coverage_ok = 0.925 <= interval["coverage"] <= 0.975
            var_ok = 0.03 <= var["var_exceedance_rate"] <= 0.07
            objective = (
                abs(interval["coverage"] - 0.95) / 0.025
                + abs(var["var_exceedance_rate"] - 0.05) / 0.02
                + interval["interval_score"] / max(float(np.mean(np.abs(actual[split:]))), 1e-8)
            )
            rows.append(
                {
                    "method": method,
                    "window": window,
                    **interval,
                    "var_exceedance_rate": var["var_exceedance_rate"],
                    "coverage_acceptance": coverage_ok,
                    "var_acceptance": var_ok,
                    "objective": objective,
                    "selection_records": len(actual) - split,
                }
            )
    table = pd.DataFrame(rows)
    eligible = table[table["coverage_acceptance"] & table["var_acceptance"]]
    if len(eligible):
        selected_index = eligible["interval_score"].idxmin()
        reason = "validation coverage và VaR acceptance đạt; chọn interval score thấp nhất"
    else:
        selected_index = table["objective"].idxmin()
        reason = "không candidate nào đạt đồng thời acceptance; chọn composite validation objective"
    table["selected"] = table.index == selected_index
    selected = table.loc[selected_index]
    selected_window = None if pd.isna(selected["window"]) else int(selected["window"])
    return ConformalSelection(str(selected["method"]), selected_window, table, reason)


# ---------------------------------------------------------------------------
# Online layer: the same conformal machinery driven one session at a time.
# ---------------------------------------------------------------------------


def interval_from_scores(
    pool_scores: np.ndarray,
    pool_regimes: np.ndarray,
    pool_volatility_bins: np.ndarray,
    method: str,
    regime: int,
    volatility_bin: int,
    center: float,
    sigma: float,
    alpha_levels: list[float],
    minimum_stratum_size: int = 80,
    effective_alpha: dict[float, float] | None = None,
) -> dict[str, float | int | str]:
    """Build one conformal interval from an explicit score pool.

    This is the body of :func:`sequential_conformal`'s loop, extracted so the
    batch backtest and the online session update share one implementation
    instead of two that can drift apart. ``effective_alpha`` overrides the
    nominal miscoverage per level, which is how Adaptive Conformal Inference
    feeds its running alpha back into the quantile.
    """
    pool_scores = np.asarray(pool_scores, dtype=float)
    mask, fallback = _stratum_mask(
        method,
        np.asarray(pool_regimes),
        np.asarray(pool_volatility_bins),
        regime,
        volatility_bin,
        minimum_stratum_size,
    )
    selected_scores = pool_scores[mask]
    row: dict[str, float | int | str] = {
        "center": float(center),
        "sigma": float(sigma),
        "regime": int(regime),
        "volatility_bin": int(volatility_bin),
        "score_count": int(len(selected_scores)),
        "stratum_used": fallback,
    }
    for miscoverage in alpha_levels:
        suffix = str(int(round((1.0 - float(miscoverage)) * 100)))
        applied = float((effective_alpha or {}).get(float(miscoverage), miscoverage))
        multiplier = finite_sample_quantile(np.abs(selected_scores), applied)
        row[f"multiplier_{suffix}"] = multiplier
        row[f"lower_{suffix}"] = center - multiplier * sigma
        row[f"upper_{suffix}"] = center + multiplier * sigma
    row["var_95"] = center + signed_lower_quantile(selected_scores, 0.05) * sigma
    return row


@dataclass
class ConformalPool:
    """Signed conformal scores plus the stratum each score belongs to.

    Scores are kept as three parallel sequences rather than bucketed per
    stratum label, because :func:`_stratum_mask` resolves a stratum by
    *unioning* cells with a fallback cascade, and the rolling ``window`` trims
    the pooled sequence - neither is expressible on pre-bucketed lists.
    """

    scores: list[float] = field(default_factory=list)
    regimes: list[int] = field(default_factory=list)
    volatility_bins: list[int] = field(default_factory=list)

    def append(self, score: float, regime: int, volatility_bin: int) -> None:
        self.scores.append(float(score))
        self.regimes.append(int(regime))
        self.volatility_bins.append(int(volatility_bin))

    def truncate(self, window: int | None) -> None:
        if window is None or len(self.scores) <= int(window):
            return
        keep = int(window)
        self.scores = self.scores[-keep:]
        self.regimes = self.regimes[-keep:]
        self.volatility_bins = self.volatility_bins[-keep:]

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.asarray(self.scores, dtype=float),
            np.asarray(self.regimes, dtype=int),
            np.asarray(self.volatility_bins, dtype=int),
        )

    def __len__(self) -> int:
        return len(self.scores)


@dataclass
class PendingScore:
    """A forecast already published whose target has not been observed yet."""

    origin_date: str
    horizon: int
    target_end_date: str
    center: float
    sigma: float
    regime: int
    volatility_bin: int
    interval_bounds: dict[float, tuple[float, float]] = field(default_factory=dict)


@dataclass
class AdaptiveConformalState:
    """Adaptive conformal inference (Gibbs and Candes, 2021), one alpha per level."""

    gamma: float
    alpha_target: dict[float, float]
    alpha_current: dict[float, float]
    epsilon: float = 1e-3

    def update(self, level: float, covered: bool) -> float:
        level = float(level)
        target = float(self.alpha_target[level])
        current = float(self.alpha_current[level])
        updated = current + float(self.gamma) * (target - (0.0 if covered else 1.0))
        updated = float(np.clip(updated, self.epsilon, 1.0 - self.epsilon))
        self.alpha_current[level] = updated
        return updated

    def effective_alpha(self) -> dict[float, float]:
        return dict(self.alpha_current)


def mature_pending_scores(
    pending: list[PendingScore],
    pools: dict[int, ConformalPool],
    as_of_date: pd.Timestamp,
    realized_return: Callable[[PendingScore], float | None],
    windows: dict[int, int | None],
    adaptive: AdaptiveConformalState | None = None,
    epsilon: float = 1e-8,
) -> tuple[list[PendingScore], list[dict[str, object]]]:
    """Move every observable pending forecast into its horizon's score pool.

    A forecast matures only once ``target_end_date <= as_of_date``, the online
    equivalent of the ``position - horizon + 1`` maturity rule enforced by
    :func:`sequential_conformal`. When ``realized_return`` cannot supply the
    outcome yet the item stays pending rather than being scored on a guess.
    """
    as_of_date = pd.Timestamp(as_of_date)
    remaining: list[PendingScore] = []
    matured: list[dict[str, object]] = []
    for item in pending:
        if pd.Timestamp(item.target_end_date) > as_of_date:
            remaining.append(item)
            continue
        realized = realized_return(item)
        if realized is None or not np.isfinite(realized):
            remaining.append(item)
            continue
        score = float((realized - item.center) / max(float(item.sigma), epsilon))
        pool = pools.setdefault(item.horizon, ConformalPool())
        pool.append(score, item.regime, item.volatility_bin)
        pool.truncate(windows.get(item.horizon))
        record: dict[str, object] = {
            "origin_date": item.origin_date,
            "horizon": item.horizon,
            "target_end_date": item.target_end_date,
            "realized": float(realized),
            "score": score,
        }
        if adaptive is not None:
            for level, (lower, upper) in item.interval_bounds.items():
                covered = bool(lower <= realized <= upper)
                suffix = int(round((1 - float(level)) * 100))
                record[f"covered_{suffix}"] = covered
                record[f"alpha_{suffix}"] = adaptive.update(level, covered)
        matured.append(record)
    return remaining, matured
