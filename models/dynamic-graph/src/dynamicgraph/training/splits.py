r"""Chronological splits.

Only walk-forward splits exist here -- there is deliberately no shuffled or
random split available anywhere in the package, so it cannot be reached by
accident.

Layout of one fold (positions are trading-day indices, time flows left to right):

    [------------- train -------------][purge][-- val --][purge][-- test --][embargo]

`expanding_window=True` grows the training start from 0; otherwise the training
window slides with a fixed length.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.training.purging import PurgeSpec, assert_no_overlap

logger = get_logger(__name__)


@dataclass
class Fold:
    """One walk-forward fold, expressed as positions into a shared date index."""

    fold_id: int
    index: pd.DatetimeIndex
    train_positions: np.ndarray
    validation_positions: np.ndarray
    test_positions: np.ndarray
    purge_days: int = 0
    embargo_days: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- date views -----------------------------------------------------
    @property
    def train_dates(self) -> pd.DatetimeIndex:
        return self.index[self.train_positions]

    @property
    def validation_dates(self) -> pd.DatetimeIndex:
        return self.index[self.validation_positions]

    @property
    def test_dates(self) -> pd.DatetimeIndex:
        return self.index[self.test_positions]

    def mask(self, which: str = "train") -> pd.Series:
        """Boolean mask over the full index for one split."""
        positions = {
            "train": self.train_positions,
            "validation": self.validation_positions,
            "test": self.test_positions,
        }[which]
        mask = pd.Series(False, index=self.index)
        mask.iloc[positions] = True
        return mask

    def train_plus_validation_mask(self) -> pd.Series:
        """Everything the model is allowed to learn from in this fold."""
        return self.mask("train") | self.mask("validation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "n_train": int(self.train_positions.size),
            "n_validation": int(self.validation_positions.size),
            "n_test": int(self.test_positions.size),
            "train_start": str(self.train_dates.min().date()) if self.train_positions.size else None,
            "train_end": str(self.train_dates.max().date()) if self.train_positions.size else None,
            "validation_start": str(self.validation_dates.min().date()) if self.validation_positions.size else None,
            "validation_end": str(self.validation_dates.max().date()) if self.validation_positions.size else None,
            "test_start": str(self.test_dates.min().date()) if self.test_positions.size else None,
            "test_end": str(self.test_dates.max().date()) if self.test_positions.size else None,
            "purge_days": self.purge_days,
            "embargo_days": self.embargo_days,
            **self.metadata,
        }


def generate_walk_forward_folds(
    index: pd.DatetimeIndex,
    initial_train_days: int = 756,
    validation_days: int = 126,
    test_days: int = 63,
    purge_days: int = 40,
    embargo_days: int = 5,
    expanding_window: bool = True,
    max_horizon: int = 40,
    min_folds: int = 1,
) -> list[Fold]:
    """Build purged walk-forward folds over a date index."""
    index = pd.DatetimeIndex(index)
    n = len(index)
    spec = PurgeSpec(purge_days=purge_days, embargo_days=embargo_days, max_horizon=max_horizon)
    purge = spec.purge_days

    block = initial_train_days + purge + validation_days + purge + test_days
    if n < block:
        raise ValueError(
            f"Not enough observations ({n}) for one walk-forward fold "
            f"(need >= {block}). Reduce training.initial_train_days / validation_days / test_days."
        )

    folds: list[Fold] = []
    train_end = initial_train_days
    fold_id = 0

    while True:
        validation_start = train_end + purge
        validation_end = validation_start + validation_days
        test_start = validation_end + purge
        test_end = min(test_start + test_days, n)
        if test_start >= n or test_end - test_start < max(5, test_days // 4):
            break

        train_start = 0 if expanding_window else max(0, train_end - initial_train_days)
        train_positions = np.arange(train_start, train_end)
        validation_positions = np.arange(validation_start, validation_end)
        test_positions = np.arange(test_start, test_end)

        # Purge/embargo the training block against both evaluation blocks.
        from dynamicgraph.training.purging import purge_train_indices

        train_positions = purge_train_indices(
            index, train_positions, validation_start, validation_end - 1, purge, embargo_days
        )
        train_positions = purge_train_indices(
            index, train_positions, test_start, test_end - 1, purge, embargo_days
        )
        validation_positions = purge_train_indices(
            index, validation_positions, test_start, test_end - 1, purge, embargo_days
        )

        if train_positions.size < 100 or validation_positions.size < 20:
            logger.warning("Fold %d has too few observations after purging; stopping.", fold_id)
            break

        fold = Fold(
            fold_id=fold_id,
            index=index,
            train_positions=train_positions,
            validation_positions=validation_positions,
            test_positions=test_positions,
            purge_days=purge,
            embargo_days=embargo_days,
            metadata={"expanding_window": expanding_window, "max_horizon": max_horizon},
        )
        assert_no_overlap(train_positions, test_positions, max_horizon, embargo_days)
        assert_no_overlap(train_positions, validation_positions, max_horizon, embargo_days)
        assert_no_overlap(validation_positions, test_positions, max_horizon, embargo_days)
        folds.append(fold)

        fold_id += 1
        # Advance exactly one test block. Reconstructing from `test_end` and
        # adding `test_days` again skips a full OOS block between folds.
        train_end += test_days
        if train_end + purge + validation_days + purge >= n:
            break

    if len(folds) < min_folds:
        raise ValueError(
            f"Only {len(folds)} walk-forward fold(s) could be built; at least {min_folds} required."
        )
    logger.info(
        "Generated %d purged walk-forward fold(s): train>=%d, val=%d, test=%d, purge=%d, embargo=%d.",
        len(folds),
        initial_train_days,
        validation_days,
        test_days,
        purge,
        embargo_days,
    )
    return folds


def folds_from_config(index: pd.DatetimeIndex, config: Any) -> list[Fold]:
    training = config.training
    max_horizon = max(int(h) for h in config.targets.horizons)
    return generate_walk_forward_folds(
        index,
        initial_train_days=int(training.initial_train_days),
        validation_days=int(training.validation_days),
        test_days=int(training.test_days),
        purge_days=int(training.purge_days),
        embargo_days=int(training.embargo_days),
        expanding_window=bool(training.expanding_window),
        max_horizon=max_horizon,
    )


def fold_summary(folds: list[Fold]) -> pd.DataFrame:
    return pd.DataFrame([fold.to_dict() for fold in folds])


def iter_folds(folds: list[Fold]) -> Iterator[Fold]:
    return iter(folds)


def global_train_mask(folds: list[Fold], index: pd.DatetimeIndex) -> pd.Series:
    """Dates that are in the FIRST fold's training block.

    Used for artifacts that need a single "training period" -- e.g. the
    descriptive stress-score standardisation and the graphical-lasso alpha --
    so that those choices are never informed by any evaluated period.
    """
    if not folds:
        return pd.Series(True, index=index)
    return folds[0].mask("train").reindex(index, fill_value=False)
