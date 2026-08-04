import pandas as pd

from raemf_mc.validation.purged_split import PurgedWalkForwardSplit, make_outer_split


def test_target_end_before_validation():
    dates = pd.Series(pd.date_range("2020-01-01", periods=200))
    target_end = dates.shift(-20)
    valid = target_end.notna()
    split = make_outer_split(dates[valid].reset_index(drop=True), target_end[valid].reset_index(drop=True))
    assert (target_end[valid].reset_index(drop=True).iloc[split.train] < split.validation_start).all()


def test_purged_fold_has_no_overlap():
    dates = pd.Series(pd.date_range("2020-01-01", periods=220))
    target_end = dates.shift(-20)
    valid = target_end.notna()
    splitter = PurgedWalkForwardSplit(n_splits=2, validation_size=40, horizon=20)
    for train, val in splitter.split(dates[valid].reset_index(drop=True), target_end[valid].reset_index(drop=True)):
        assert (target_end[valid].reset_index(drop=True).iloc[train] < dates[valid].reset_index(drop=True).iloc[val[0]]).all()
