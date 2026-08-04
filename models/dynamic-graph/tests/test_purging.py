"""Purging and embargo behaviour."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.training.purging import (
    PurgeSpec,
    assert_no_overlap,
    effective_sample_size,
    purge_train_indices,
)
from dynamicgraph.training.splits import generate_walk_forward_folds


@pytest.fixture
def index() -> pd.DatetimeIndex:
    return pd.bdate_range("2015-01-01", periods=1500)


def test_purge_spec_raises_purge_to_the_horizon():
    spec = PurgeSpec(purge_days=10, embargo_days=5, max_horizon=40)
    assert spec.purge_days == 40


def test_purge_removes_the_leaking_window(index):
    train = np.arange(0, 500)
    kept = purge_train_indices(index, train, eval_start=520, eval_end=600, purge_days=40, embargo_days=0)
    assert kept.max() < 480
    assert len(kept) == 480


def test_embargo_removes_observations_after_the_evaluation_block(index):
    train = np.concatenate([np.arange(0, 500), np.arange(700, 900)])
    kept = purge_train_indices(index, train, eval_start=520, eval_end=690, purge_days=40, embargo_days=20)
    assert not ((kept > 690) & (kept <= 710)).any()
    assert (kept > 710).any()


def test_assert_no_overlap_detects_leakage():
    train = np.arange(0, 100)
    evaluation = np.arange(110, 150)
    # Horizon 40: training labels from t=99 reach t=139, inside the eval block.
    with pytest.raises(AssertionError):
        assert_no_overlap(train, evaluation, horizon=40)
    # Horizon 5 is safe.
    assert_no_overlap(train, evaluation, horizon=5)


def test_assert_no_overlap_detects_embargo_violation():
    train = np.arange(200, 260)
    evaluation = np.arange(100, 190)
    with pytest.raises(AssertionError):
        assert_no_overlap(train, evaluation, horizon=1, embargo_days=20)


def test_generated_folds_pass_the_overlap_assertion(index):
    for horizon in (5, 20, 40):
        folds = generate_walk_forward_folds(
            index, 500, 100, 100, purge_days=40, embargo_days=5, max_horizon=horizon
        )
        for fold in folds:
            assert_no_overlap(fold.train_positions, fold.test_positions, horizon, fold.embargo_days)
            assert_no_overlap(fold.train_positions, fold.validation_positions, horizon, fold.embargo_days)
            assert_no_overlap(fold.validation_positions, fold.test_positions, horizon, fold.embargo_days)


def test_effective_sample_size_accounts_for_overlap():
    assert effective_sample_size(252, 1) == pytest.approx(252)
    assert effective_sample_size(252, 20) == pytest.approx(12.6)
    assert effective_sample_size(1000, 40) < 1000


def test_label_windows_never_reach_the_test_block(index):
    """Direct end-to-end check on the invariant that matters."""
    horizon = 40
    folds = generate_walk_forward_folds(
        index, 600, 120, 120, purge_days=horizon, embargo_days=5, max_horizon=horizon
    )
    for fold in folds:
        latest_label_date = fold.train_positions.max() + horizon
        assert latest_label_date < fold.test_positions.min(), (
            f"fold {fold.fold_id}: a training label reaches into the test block"
        )
