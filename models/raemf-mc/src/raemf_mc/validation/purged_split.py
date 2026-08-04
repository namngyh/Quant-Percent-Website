"""Purged chronological validation split."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OuterSplit:
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray
    validation_start: pd.Timestamp
    test_start: pd.Timestamp


class PurgedWalkForwardSplit:
    """Walk-forward splitter with horizon-based purge/embargo."""

    def __init__(self, n_splits: int = 3, validation_size: int | None = None, horizon: int = 20) -> None:
        self.n_splits = n_splits
        self.validation_size = validation_size
        self.horizon = horizon

    def split(self, dates: pd.Series, target_end_dates: pd.Series):
        n = len(dates)
        val_size = self.validation_size or max(30, n // (self.n_splits + 3))
        first_validation = max(80, n - self.n_splits * val_size)
        for fold in range(self.n_splits):
            val_start_pos = first_validation + fold * val_size
            val_end_pos = min(val_start_pos + val_size, n)
            if val_end_pos <= val_start_pos or val_start_pos >= n:
                break
            val_start_date = dates.iloc[val_start_pos]
            train_mask = (np.arange(n) < val_start_pos) & (target_end_dates < val_start_date).to_numpy()
            val_idx = np.arange(val_start_pos, val_end_pos)
            train_idx = np.where(train_mask)[0]
            if len(train_idx) and len(val_idx):
                yield train_idx, val_idx


def make_outer_split(
    dates: pd.Series,
    target_end_dates: pd.Series,
    train_fraction: float = 0.65,
    validation_fraction: float = 0.15,
) -> OuterSplit:
    """Create chronological train, validation, and final test indices with purge."""
    n = len(dates)
    val_start_pos = int(n * train_fraction)
    test_start_pos = int(n * (train_fraction + validation_fraction))
    validation_start = pd.Timestamp(dates.iloc[val_start_pos])
    test_start = pd.Timestamp(dates.iloc[test_start_pos])
    idx = np.arange(n)
    train = idx[(idx < val_start_pos) & (target_end_dates < validation_start).to_numpy()]
    validation = idx[(idx >= val_start_pos) & (idx < test_start_pos) & (target_end_dates < test_start).to_numpy()]
    test = idx[idx >= test_start_pos]
    return OuterSplit(train=train, validation=validation, test=test, validation_start=validation_start, test_start=test_start)
