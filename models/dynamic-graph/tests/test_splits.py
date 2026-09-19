"""Walk-forward split construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.training.splits import (
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


@pytest.mark.parametrize("expanding", [True, False])
def test_oos_blocks_are_contiguous_without_duplicates(index, expanding):
    folds = generate_walk_forward_folds(
        index,
        initial_train_days=500,
        validation_days=100,
        test_days=73,
        purge_days=40,
        embargo_days=5,
        expanding_window=expanding,
    )
    positions = np.concatenate([fold.test_positions for fold in folds])
    assert len(positions) == len(np.unique(positions))
    assert np.array_equal(positions, np.arange(positions.min(), positions.max() + 1))
    for previous, current in zip(folds, folds[1:]):
        assert current.test_positions.min() == previous.test_positions.max() + 1


def test_final_oos_block_may_be_partial_but_has_no_gap():
    index = pd.bdate_range("2015-01-01", periods=1_177)
    folds = generate_walk_forward_folds(
        index,
        initial_train_days=500,
        validation_days=100,
        test_days=73,
        purge_days=40,
        embargo_days=5,
    )
    positions = np.concatenate([fold.test_positions for fold in folds])
    assert np.array_equal(positions, np.arange(positions.min(), positions.max() + 1))
    assert len(folds[-1].test_positions) < 73


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


def test_oos_hard_metrics_use_each_rows_fold_threshold():
    from dynamicgraph.evaluation.classification import classification_metrics
    from dynamicgraph.training.walk_forward import WalkForwardResult

    probabilities = np.array(
        [0.25, 0.15, 0.30, 0.10, 0.40, 0.05, 0.75, 0.85, 0.70, 0.90, 0.60, 0.95]
    )
    y_true = np.array([1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1])
    thresholds = np.array([0.20] * 6 + [0.80] * 6)
    predictions = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=12),
            "fold": [0] * 6 + [1] * 6,
            "probability": probabilities,
            "y_true": y_true,
            "threshold": thresholds,
        }
    )
    result = WalkForwardResult("model", "market", 5, "target", predictions=predictions)
    actual = result.oos_metrics()
    expected = classification_metrics(y_true, probabilities, threshold=thresholds)
    median_based = classification_metrics(y_true, probabilities, threshold=0.5)
    assert actual["mcc"] == pytest.approx(expected["mcc"])
    assert actual["recall"] == pytest.approx(expected["recall"])
    assert actual["mcc"] != pytest.approx(median_based["mcc"])
    assert actual["threshold_policy"] == "per_prediction"


def test_calibration_and_threshold_blocks_are_disjoint_and_purged():
    from dynamicgraph.training.walk_forward import _chronological_subsplit

    index = pd.bdate_range("2023-01-01", periods=126)
    calibration, threshold = _chronological_subsplit(
        index, gap=20, min_each=20
    )

    assert len(calibration) >= 20
    assert len(threshold) >= 20
    assert set(calibration).isdisjoint(threshold)
    assert index.get_loc(threshold.min()) - index.get_loc(calibration.max()) > 20
