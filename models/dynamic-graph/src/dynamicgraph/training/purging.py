r"""Purging and embargo.

A label at date t is built from the window (t, t+h]. If t sits in the training
set and t+h reaches into the test set, the model has effectively seen test-period
outcomes. Two guards:

**Purge** -- drop training dates whose label window overlaps the evaluation
window. The purge must be at least the largest forecast horizon.

**Embargo** -- additionally drop the first `embargo_days` of training data
*after* an evaluation block, because serial correlation in features makes
observations immediately following the test window informative about it.

Positions are measured in *trading days* (index positions), never calendar days.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PurgeSpec:
    purge_days: int
    embargo_days: int
    max_horizon: int

    def __post_init__(self) -> None:
        if self.purge_days < self.max_horizon:
            logger.warning(
                "purge_days=%d is smaller than the largest forecast horizon (%d); raising it. "
                "A shorter purge leaves overlapping labels between train and test.",
                self.purge_days,
                self.max_horizon,
            )
            self.purge_days = self.max_horizon


def purge_train_indices(
    index: pd.DatetimeIndex,
    train_positions: np.ndarray,
    eval_start: int,
    eval_end: int,
    purge_days: int,
    embargo_days: int = 0,
) -> np.ndarray:
    """Remove train positions that leak into `[eval_start, eval_end]`.

    Dropped: training dates within `purge_days` *before* the evaluation block
    (their label window reaches into it) and within `embargo_days` *after* it.
    """
    lower = eval_start - purge_days
    upper = eval_end + embargo_days
    keep = (train_positions < lower) | (train_positions > upper)
    removed = int((~keep).sum())
    if removed:
        logger.debug(
            "Purged %d training observation(s) around evaluation block [%s, %s].",
            removed,
            index[eval_start].date(),
            index[eval_end].date(),
        )
    return train_positions[keep]


def assert_no_overlap(
    train_positions: np.ndarray,
    eval_positions: np.ndarray,
    horizon: int,
    embargo_days: int = 0,
) -> None:
    """Raise if any training label window can touch the evaluation window.

    Used both as a runtime guard and by `tests/test_purging.py`.
    """
    if train_positions.size == 0 or eval_positions.size == 0:
        return
    eval_start, eval_end = int(eval_positions.min()), int(eval_positions.max())
    label_end = train_positions + horizon
    leaking = train_positions[(label_end >= eval_start) & (train_positions <= eval_end)]
    if leaking.size:
        raise AssertionError(
            f"{leaking.size} training observation(s) have label windows overlapping the "
            f"evaluation block [{eval_start}, {eval_end}] at horizon {horizon}."
        )
    if embargo_days > 0:
        embargoed = train_positions[
            (train_positions > eval_end) & (train_positions <= eval_end + embargo_days)
        ]
        if embargoed.size:
            raise AssertionError(
                f"{embargoed.size} training observation(s) fall inside the {embargo_days}-day "
                "embargo after the evaluation block."
            )


def effective_sample_size(n_observations: int, horizon: int) -> float:
    """Rough independent-sample count once overlapping labels are accounted for.

    Overlapping h-day windows share h-1 days of outcome, so the effective sample
    is closer to n/h than to n. Reported alongside every metric so that
    confidence intervals are not read as if they came from n independent draws.
    """
    if horizon <= 1:
        return float(n_observations)
    return float(n_observations / horizon)
