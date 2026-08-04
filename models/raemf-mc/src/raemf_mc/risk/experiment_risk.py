"""Model, distribution and paper-exposure risk for downside experiments."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    precision_recall_fscore_support,
    roc_auc_score,
)

from raemf_mc.backtest.exposure import backtest_exposure
from raemf_mc.backtest.metrics import backtest_metrics
from raemf_mc.evaluation.risk_backtests import kupiec_test
from raemf_mc.risk.threshold_selection import binary_ece
from raemf_mc.uncertainty.block_bootstrap import moving_block_indices


def calculate_exposure_cap(
    capital: float,
    loss_budget_fraction: float,
    stress_market_move: float,
    portfolio_beta: float = 1.0,
    transaction_cost_fraction: float = 0.0,
    slippage_fraction: float = 0.0,
    max_exposure: float = 1.0,
) -> float:
    """Approximate notional exposure cap under a stress-loss budget."""
    values = {
        "capital": capital,
        "loss_budget_fraction": loss_budget_fraction,
        "stress_market_move": stress_market_move,
        "transaction_cost_fraction": transaction_cost_fraction,
        "slippage_fraction": slippage_fraction,
        "max_exposure": max_exposure,
    }
    if not all(np.isfinite(float(value)) for value in values.values()) or not np.isfinite(float(portfolio_beta)):
        raise ValueError("Exposure-cap inputs must be finite")
    if capital <= 0 or not 0 <= loss_budget_fraction <= 1 or stress_market_move <= 0:
        raise ValueError("capital/stress budget inputs are outside their valid domains")
    if transaction_cost_fraction < 0 or slippage_fraction < 0 or max_exposure < 0:
        raise ValueError("Costs and max_exposure must be non-negative")
    denominator = abs(float(portfolio_beta)) * float(stress_market_move)
    if denominator <= 0:
        raise ValueError("Absolute portfolio_beta × stress_market_move must be positive")
    budget = float(loss_budget_fraction) - float(transaction_cost_fraction) - float(slippage_fraction)
    return float(np.clip(budget / denominator, 0.0, max_exposure))


def validate_probability_bands(bands: list[dict[str, float]]) -> list[dict[str, float]]:
    """Require complete probability coverage and a non-increasing multiplier."""
    if not bands:
        raise ValueError("risk_overlay.probability_bands cannot be empty")
    ordered = sorted(
        [
            {
                "max_probability": float(item["max_probability"]),
                "multiplier": float(item["multiplier"]),
            }
            for item in bands
        ],
        key=lambda item: item["max_probability"],
    )
    maxima = [item["max_probability"] for item in ordered]
    multipliers = [item["multiplier"] for item in ordered]
    if maxima[-1] < 1.0 or any(value <= 0 or value > 1 for value in maxima):
        raise ValueError("Probability bands must end at 1.0 and stay in (0, 1]")
    if any(left >= right for left, right in zip(maxima, maxima[1:], strict=False)):
        raise ValueError("Probability-band maxima must be strictly increasing")
    if any(value < 0 or value > 1 for value in multipliers):
        raise ValueError("Risk multipliers must stay in [0, 1]")
    if any(left < right for left, right in zip(multipliers, multipliers[1:], strict=False)):
        raise ValueError("Risk multiplier must be non-increasing as Risk-off probability rises")
    return ordered


def risk_multiplier(probability: pd.Series | np.ndarray, bands: list[dict[str, float]]) -> np.ndarray:
    """Map Risk-off probability to a monotone paper-exposure multiplier."""
    ordered = validate_probability_bands(bands)
    values = np.asarray(probability, dtype=float)
    if np.any(~np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError("Risk-off probabilities must be finite and inside [0, 1]")
    result = np.empty(len(values), dtype=float)
    lower = 0.0
    for item in ordered:
        upper = item["max_probability"]
        mask = (values >= lower) & (values <= upper if upper >= 1.0 else values < upper)
        result[mask] = item["multiplier"]
        lower = upper
    return result


def evaluate_distribution_risk(
    realized_return: pd.Series | np.ndarray,
    intervals: dict[float, tuple[pd.Series | np.ndarray, pd.Series | np.ndarray]],
    *,
    var_95: pd.Series | np.ndarray,
    cvar_95: pd.Series | np.ndarray,
    future_mae: pd.Series | np.ndarray,
    drawdown_probabilities: dict[float, pd.Series | np.ndarray],
    effective_sample_size: pd.Series | np.ndarray | None = None,
    tail_estimates_by_seed: pd.Series | np.ndarray | None = None,
) -> dict[str, float]:
    """Summarize distribution calibration without changing the production mode."""
    realized = np.asarray(realized_return, dtype=float)
    var = np.asarray(var_95, dtype=float)
    cvar = np.asarray(cvar_95, dtype=float)
    mae = np.asarray(future_mae, dtype=float)
    if not (len(realized) == len(var) == len(cvar) == len(mae)):
        raise ValueError("Distribution-risk arrays must have equal length")
    output: dict[str, float] = {}
    for level in (0.50, 0.80, 0.90, 0.95):
        if level not in intervals:
            output[f"coverage_{int(level * 100)}"] = float("nan")
            output[f"interval_width_{int(level * 100)}"] = float("nan")
            continue
        lower = np.asarray(intervals[level][0], dtype=float)
        upper = np.asarray(intervals[level][1], dtype=float)
        if len(lower) != len(realized) or len(upper) != len(realized):
            raise ValueError(f"Interval arrays for level={level} have invalid length")
        valid = np.isfinite(realized) & np.isfinite(lower) & np.isfinite(upper)
        output[f"coverage_{int(level * 100)}"] = (
            float(np.mean((realized[valid] >= lower[valid]) & (realized[valid] <= upper[valid])))
            if valid.any()
            else float("nan")
        )
        output[f"interval_width_{int(level * 100)}"] = (
            float(np.mean(upper[valid] - lower[valid])) if valid.any() else float("nan")
        )
    valid_var = np.isfinite(realized) & np.isfinite(var)
    exceptions = (realized[valid_var] < var[valid_var]).astype(int)
    output["var_95_exception_rate"] = float(exceptions.mean()) if len(exceptions) else float("nan")
    kupiec = kupiec_test(exceptions, 0.05) if len(exceptions) else {}
    for key, value in kupiec.items():
        output[f"kupiec_95_{key}"] = float(value)
    output["mean_predicted_cvar_95"] = float(np.nanmean(cvar)) if np.isfinite(cvar).any() else float("nan")
    realized_tail = realized[valid_var & (realized < var)]
    output["realized_cvar_95"] = (
        float(-np.mean(realized_tail)) if len(realized_tail) else float("nan")
    )
    for drawdown in (0.05, 0.10, 0.15, 0.20):
        key = f"{int(drawdown * 100)}"
        probability = drawdown_probabilities.get(drawdown)
        if probability is None:
            output[f"prob_drawdown_{key}"] = float("nan")
            output[f"drawdown_calibration_gap_{key}"] = float("nan")
            continue
        probability_array = np.asarray(probability, dtype=float)
        if len(probability_array) != len(mae):
            raise ValueError(f"Drawdown probability arrays for {drawdown} have invalid length")
        observed = mae <= np.log1p(-drawdown)
        valid = np.isfinite(probability_array) & np.isfinite(mae)
        output[f"prob_drawdown_{key}"] = (
            float(np.mean(probability_array[valid])) if valid.any() else float("nan")
        )
        output[f"drawdown_calibration_gap_{key}"] = (
            float(np.mean(probability_array[valid]) - np.mean(observed[valid]))
            if valid.any()
            else float("nan")
        )
    if effective_sample_size is None:
        output["effective_sample_size_mean"] = float("nan")
        output["effective_sample_size_min"] = float("nan")
    else:
        ess = np.asarray(effective_sample_size, dtype=float)
        output["effective_sample_size_mean"] = float(np.nanmean(ess))
        output["effective_sample_size_min"] = float(np.nanmin(ess))
    if tail_estimates_by_seed is None:
        output["tail_stability_std"] = float("nan")
        output["tail_stability_range"] = float("nan")
    else:
        tails = np.asarray(tail_estimates_by_seed, dtype=float)
        output["tail_stability_std"] = float(np.nanstd(tails))
        output["tail_stability_range"] = float(np.nanmax(tails) - np.nanmin(tails))
    return output


def _calibration_slope_intercept(target: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    if len(target) < 30 or len(np.unique(target)) < 2:
        return float("nan"), float("nan")
    logits = logit(np.clip(probability, 1e-6, 1 - 1e-6)).reshape(-1, 1)
    model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(logits, target)
    return float(model.coef_[0, 0]), float(model.intercept_[0])


def evaluate_model_risk(
    dates: pd.Series,
    target: pd.Series | np.ndarray,
    probability: np.ndarray,
    threshold: float,
    forward_return: pd.Series | np.ndarray,
    future_mae: pd.Series | np.ndarray,
    *,
    horizon: int,
    model: str,
    fold: int,
    fn_cost_multiplier: float = 3.0,
    fp_cost_multiplier: float = 1.0,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute model risk plus event, rolling and yearly diagnostics."""
    y = np.asarray(target, dtype=int)
    p = np.clip(np.asarray(probability, dtype=float), 1e-8, 1 - 1e-8)
    forward = np.asarray(forward_return, dtype=float)
    mae = np.asarray(future_mae, dtype=float)
    predicted = p >= float(threshold)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y,
        predicted.astype(int),
        labels=[0, 1],
        zero_division=0,
    )
    matrix = confusion_matrix(y, predicted.astype(int), labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    pr_auc = float(average_precision_score(y, p)) if len(np.unique(y)) > 1 else float("nan")
    roc_auc = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")
    missed = (y == 1) & ~predicted
    false_positive = (y == 0) & predicted
    missed_loss = np.abs(np.minimum(mae[missed], 0.0))
    opportunity = np.maximum(forward[false_positive], 0.0)
    calibration_slope, calibration_intercept = _calibration_slope_intercept(y, p)
    metrics: dict[str, Any] = {
        "model": model,
        "horizon": int(horizon),
        "fold": int(fold),
        "n_obs": int(len(y)),
        "threshold": float(threshold),
        "recall": float(recall[1]),
        "precision": float(precision[1]),
        "f1": float(f1[1]),
        "specificity": float(tn / max(tn + fp, 1)),
        "false_negative_rate": float(fn / max(fn + tp, 1)),
        "false_positive_rate": float(fp / max(fp + tn, 1)),
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "ece": binary_ece(y, p),
        "calibration_slope": calibration_slope,
        "calibration_intercept": calibration_intercept,
        "expected_false_negative_loss": float(missed_loss.sum() / max(len(y), 1)),
        "expected_false_positive_opportunity_cost": float(opportunity.sum() / max(len(y), 1)),
        "expected_cost": float(
            (fn_cost_multiplier * missed_loss.sum() + fp_cost_multiplier * opportunity.sum()) / max(len(y), 1)
        ),
        "worst_missed_drawdown": float(missed_loss.max()) if len(missed_loss) else float("nan"),
        "mean_missed_drawdown": float(missed_loss.mean()) if len(missed_loss) else float("nan"),
        "alert_fraction": float(predicted.mean()),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
    }
    event_frame = pd.DataFrame(
        {
            "date": pd.to_datetime(dates).to_numpy(),
            "horizon": horizon,
            "fold": fold,
            "model": model,
            "actual_risk_off": y,
            "probability": p,
            "threshold": threshold,
            "alert": predicted.astype(int),
            "forward_return": forward,
            "future_mae": mae,
        }
    )
    missed_events = event_frame.loc[missed].sort_values("future_mae").reset_index(drop=True)
    false_positive_events = event_frame.loc[false_positive].sort_values("forward_return", ascending=False).reset_index(drop=True)
    rolling = _rolling_model_risk(event_frame)
    yearly = _yearly_model_risk(event_frame)
    severity = _severity_recall(event_frame)
    return metrics, missed_events, false_positive_events, rolling, pd.concat([yearly, severity], ignore_index=True)


def _rolling_model_risk(events: pd.DataFrame, window: int = 120) -> pd.DataFrame:
    frame = events.sort_values("date").copy()
    actual = frame["actual_risk_off"].astype(float)
    alert = frame["alert"].astype(float)
    tp = (actual * alert).rolling(window, min_periods=max(20, window // 3)).sum()
    positives = actual.rolling(window, min_periods=max(20, window // 3)).sum()
    fp = ((1 - actual) * alert).rolling(window, min_periods=max(20, window // 3)).sum()
    alerts = alert.rolling(window, min_periods=max(20, window // 3)).sum()
    return pd.DataFrame(
        {
            "scope": "rolling",
            "date": frame["date"],
            "horizon": frame["horizon"],
            "fold": frame["fold"],
            "model": frame["model"],
            "recall": tp / positives.replace(0, np.nan),
            "precision": tp / alerts.replace(0, np.nan),
            "false_positive_rate": fp
            / (1 - actual).rolling(window, min_periods=max(20, window // 3)).sum().replace(0, np.nan),
        }
    ).dropna(subset=["recall", "precision"], how="all")


def _yearly_model_risk(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    frame = events.assign(year=pd.to_datetime(events["date"]).dt.year)
    for year, group in frame.groupby("year"):
        actual = group["actual_risk_off"].to_numpy(dtype=int)
        alert = group["alert"].to_numpy(dtype=int)
        tp = int(np.sum((actual == 1) & (alert == 1)))
        fp = int(np.sum((actual == 0) & (alert == 1)))
        fn = int(np.sum((actual == 1) & (alert == 0)))
        rows.append(
            {
                "scope": "calendar_year",
                "bucket": int(year),
                "horizon": int(group["horizon"].iloc[0]),
                "fold": int(group["fold"].iloc[0]),
                "model": str(group["model"].iloc[0]),
                "recall": tp / max(tp + fn, 1),
                "precision": tp / max(tp + fp, 1),
                "support": int(np.sum(actual == 1)),
            }
        )
    return pd.DataFrame(rows)


def _severity_recall(events: pd.DataFrame) -> pd.DataFrame:
    positives = events.loc[events["actual_risk_off"] == 1].copy()
    if len(positives) < 4:
        return pd.DataFrame()
    ranks = (-positives["future_mae"]).rank(method="first")
    bucket_count = min(4, len(positives))
    positives["bucket"] = pd.qcut(ranks, q=bucket_count, labels=False, duplicates="drop")
    rows: list[dict[str, Any]] = []
    for bucket, group in positives.groupby("bucket"):
        rows.append(
            {
                "scope": "severity_bucket",
                "bucket": int(bucket),
                "horizon": int(group["horizon"].iloc[0]),
                "fold": int(group["fold"].iloc[0]),
                "model": str(group["model"].iloc[0]),
                "recall": float(group["alert"].mean()),
                "precision": float("nan"),
                "support": int(len(group)),
                "mean_future_mae": float(group["future_mae"].mean()),
            }
        )
    return pd.DataFrame(rows)


def bootstrap_risk_differences(
    events: pd.DataFrame,
    candidate: str,
    baseline: str,
    *,
    replicates: int,
    block_length: int,
    seed: int,
    fn_cost_multiplier: float = 3.0,
    fp_cost_multiplier: float = 1.0,
) -> pd.DataFrame:
    """Moving-block CI for candidate-minus-baseline recall and expected cost."""
    rows: list[dict[str, Any]] = []
    for horizon, horizon_frame in events.groupby("horizon"):
        left = horizon_frame[horizon_frame["model"] == candidate].sort_values(["date", "fold"])
        right = horizon_frame[horizon_frame["model"] == baseline].sort_values(["date", "fold"])
        keys = ["date", "fold", "actual_risk_off", "forward_return", "future_mae"]
        paired = left.merge(right, on=keys, suffixes=("_candidate", "_baseline"))
        if paired.empty:
            continue
        rng = np.random.default_rng(seed + int(horizon))
        differences = {"recall": [], "expected_cost": []}
        for _ in range(int(replicates)):
            index = moving_block_indices(len(paired), min(block_length, len(paired)), rng)
            sample = paired.iloc[index]
            actual = sample["actual_risk_off"].to_numpy(dtype=int)
            for suffix, store in (("candidate", "candidate"), ("baseline", "baseline")):
                alert = sample[f"alert_{suffix}"].to_numpy(dtype=int)
                tp = np.sum((actual == 1) & (alert == 1))
                fn_mask = (actual == 1) & (alert == 0)
                fp_mask = (actual == 0) & (alert == 1)
                recall = tp / max(np.sum(actual == 1), 1)
                cost = (
                    fn_cost_multiplier
                    * np.abs(np.minimum(sample.loc[fn_mask, "future_mae"], 0.0)).sum()
                    + fp_cost_multiplier
                    * np.maximum(sample.loc[fp_mask, "forward_return"], 0.0).sum()
                ) / max(len(sample), 1)
                sample.attrs[f"recall_{store}"] = recall
                sample.attrs[f"cost_{store}"] = cost
            differences["recall"].append(sample.attrs["recall_candidate"] - sample.attrs["recall_baseline"])
            differences["expected_cost"].append(sample.attrs["cost_candidate"] - sample.attrs["cost_baseline"])
        for metric, values in differences.items():
            array = np.asarray(values, dtype=float)
            rows.append(
                {
                    "horizon": int(horizon),
                    "candidate": candidate,
                    "baseline": baseline,
                    "metric": metric,
                    "mean_difference": float(array.mean()),
                    "ci_low": float(np.quantile(array, 0.025)),
                    "ci_high": float(np.quantile(array, 0.975)),
                    "ci_excludes_zero": bool(np.quantile(array, 0.025) > 0 or np.quantile(array, 0.975) < 0),
                }
            )
    return pd.DataFrame(rows)


def paper_risk_overlay_backtest(
    dates: pd.Series,
    close: pd.Series,
    baseline_exposure: pd.Series | np.ndarray,
    risk_probability: pd.Series | np.ndarray,
    bands: list[dict[str, float]],
    *,
    transaction_cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare paper baseline/overlay/buy-and-hold/cash on one OOS calendar."""
    multiplier = risk_multiplier(risk_probability, bands)
    baseline = np.clip(np.asarray(baseline_exposure, dtype=float), 0.0, 1.0)
    signals = {
        "baseline_no_overlay": baseline,
        "baseline_risk_overlay": baseline * multiplier,
        "buy_and_hold": np.ones(len(baseline)),
        "cash": np.zeros(len(baseline)),
    }
    time_series: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    clean_close = pd.Series(np.asarray(close, dtype=float)).reset_index(drop=True)
    clean_dates = pd.Series(pd.to_datetime(dates).to_numpy()).reset_index(drop=True)
    for name, signal in signals.items():
        backtest = backtest_exposure(clean_close, pd.Series(signal), transaction_cost_bps)
        backtest.insert(0, "date", clean_dates)
        backtest.insert(1, "strategy", name)
        backtest["equity"] = np.exp(backtest["strategy_return"].cumsum())
        backtest["drawdown"] = backtest["equity"] / backtest["equity"].cummax() - 1.0
        backtest["risk_multiplier"] = multiplier if name == "baseline_risk_overlay" else 1.0
        time_series.append(backtest)
        summary = backtest_metrics(backtest, name)
        returns = backtest["strategy_return"].to_numpy(dtype=float)
        cutoff = np.quantile(returns, 0.05)
        summary["cvar_95"] = float(-returns[returns <= cutoff].mean()) if np.any(returns <= cutoff) else 0.0
        summary["time_in_risk_reduced_state"] = float((multiplier < 1).mean()) if name == "baseline_risk_overlay" else 0.0
        summaries.append(summary)
    combined = pd.concat(time_series, ignore_index=True)
    summary_frame = pd.DataFrame(summaries)
    base_return = combined.loc[combined["strategy"] == "baseline_no_overlay", "strategy_return"].to_numpy()
    overlay_return = combined.loc[combined["strategy"] == "baseline_risk_overlay", "strategy_return"].to_numpy()
    summary_frame.loc[summary_frame["model"] == "baseline_risk_overlay", "avoided_loss"] = float(
        np.maximum(-base_return, 0).sum() - np.maximum(-overlay_return, 0).sum()
    )
    summary_frame.loc[summary_frame["model"] == "baseline_risk_overlay", "opportunity_cost"] = float(
        np.maximum(base_return - overlay_return, 0).sum()
    )
    return combined, summary_frame


def probability_from_logit(log_odds: np.ndarray) -> np.ndarray:
    """Small public helper used when auditing calibration coefficients."""
    return expit(np.asarray(log_odds, dtype=float))
