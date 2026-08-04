"""Walk-forward split construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.training.splits import (
    Fold,
    fold_summary,
    generate_walk_forward_folds,
    global_train_mask,
)


@pytest.fixture
def index() -> pd.DatetimeIndex:
    return pd.bdate_range("2015-01-01", periods=2000)


def test_folds_are_chronological(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100, purge_days=40, embargo_days=5)
    assert len(folds) >= 2
    for fold in folds:
        assert fold.train_positions.max() < fold.validation_positions.min()
        assert fold.validation_positions.max() < fold.test_positions.min()


def test_test_blocks_advance_and_do_not_overlap(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100, purge_days=40, embargo_days=5)
    starts = [f.test_positions.min() for f in folds]
    assert starts == sorted(starts)
    for a, b in zip(folds, folds[1:]):
        assert a.test_positions.max() < b.test_positions.min()


def test_purge_gap_is_at_least_the_horizon(index):
    purge = 40
    folds = generate_walk_forward_folds(index, 500, 100, 100, purge_days=purge, embargo_days=5, max_horizon=40)
    for fold in folds:
        gap = fold.test_positions.min() - fold.train_positions.max()
        assert gap > purge, f"gap {gap} does not exceed the purge of {purge}"


def test_purge_is_raised_to_the_horizon_when_configured_too_small(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100, purge_days=5, embargo_days=0, max_horizon=40)
    assert folds[0].purge_days >= 40


def test_expanding_window_grows(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100, expanding_window=True)
    sizes = [len(f.train_positions) for f in folds]
    assert sizes[-1] > sizes[0]
    assert all(f.train_positions.min() == 0 for f in folds)


def test_rolling_window_stays_bounded(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100, expanding_window=False)
    sizes = [len(f.train_positions) for f in folds]
    assert max(sizes) <= 500


def test_masks_are_disjoint(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100)
    for fold in folds:
        train = fold.mask("train")
        validation = fold.mask("validation")
        test = fold.mask("test")
        assert not (train & validation).any()
        assert not (train & test).any()
        assert not (validation & test).any()


def test_too_short_index_raises():
    with pytest.raises(ValueError):
        generate_walk_forward_folds(pd.bdate_range("2020-01-01", periods=300), 756, 126, 63)


def test_fold_summary_columns(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100)
    summary = fold_summary(folds)
    for column in ("fold_id", "n_train", "n_test", "train_end", "test_start", "purge_days"):
        assert column in summary.columns


def test_global_train_mask_is_the_first_fold(index):
    folds = generate_walk_forward_folds(index, 500, 100, 100)
    mask = global_train_mask(folds, index)
    assert mask.sum() == len(folds[0].train_positions)
    assert not mask.iloc[folds[0].test_positions].any()


def test_no_shuffled_split_exists_in_the_package():
    """Guard against a random split ever being reintroduced."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "dynamicgraph"
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in ("train_test_split", "KFold(", "StratifiedKFold", "ShuffleSplit"):
            if pattern in text:
                offenders.append(f"{path.name}: {pattern}")
    assert not offenders, f"Non-chronological split found: {offenders}"
