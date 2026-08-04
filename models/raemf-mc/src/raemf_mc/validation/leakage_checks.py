"""Leakage validators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc.targets.regime_targets import target_columns


def assert_no_future_feature_columns(feature_columns: list[str]) -> None:
    forbidden = set(target_columns())
    bad = sorted(set(feature_columns) & forbidden)
    if bad:
        raise AssertionError(f"Forward-looking columns used as features: {bad}")
    bad_tokens = [
        c
        for c in feature_columns
        if c.startswith(
            (
                "target_",
                "forward_return_",
                "future_mae_",
                "risk_off_",
                "negative_terminal_",
                "stress_path_",
                "drawdown_5_",
                "drawdown_10_",
            )
        )
    ]
    if bad_tokens:
        raise AssertionError(f"Forbidden target-like feature columns: {bad_tokens}")


def assert_target_end_before_boundary(target_end_dates: pd.Series, indices: np.ndarray, boundary: pd.Timestamp, name: str) -> None:
    if len(indices) and not (target_end_dates.iloc[indices] < boundary).all():
        raise AssertionError(f"{name} contains labels ending at or after {boundary}")


def assert_purged_fold(train_idx: np.ndarray, val_idx: np.ndarray, target_end_dates: pd.Series, dates: pd.Series) -> None:
    if len(train_idx) == 0 or len(val_idx) == 0:
        return
    val_start = pd.Timestamp(dates.iloc[val_idx[0]])
    if not (target_end_dates.iloc[train_idx] < val_start).all():
        raise AssertionError("Purged fold has train target overlap with validation window")


def assert_backtest_one_day_lag(signals: pd.Series, returns: pd.Series, strategy_returns: pd.Series) -> None:
    expected = signals.shift(1).fillna(0.0) * returns
    if not np.allclose(expected.fillna(0.0), strategy_returns.fillna(0.0)):
        raise AssertionError("Backtest return does not use one-day lag")


def assert_backtest_dates_are_oos(backtest_dates: pd.Series, prediction_dates: pd.Series) -> None:
    """Require the backtest calendar to match the persisted OOS predictions."""
    left = pd.DatetimeIndex(pd.to_datetime(backtest_dates).drop_duplicates().sort_values())
    right = pd.DatetimeIndex(pd.to_datetime(prediction_dates).drop_duplicates().sort_values())
    if not left.equals(right):
        raise AssertionError("Backtest dates do not exactly match OOS prediction dates")
