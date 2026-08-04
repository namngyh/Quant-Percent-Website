import numpy as np
import pandas as pd

from raemf_mc.evaluation.oos_distribution_benchmark import (
    _weighted_distribution_row,
    bootstrap_distribution_differences,
    make_distribution_folds,
)


def test_distribution_folds_are_purged_and_test_blocks_do_not_overlap():
    dates = pd.Series(pd.date_range("2020-01-01", periods=300))
    target_end = dates.shift(-20)
    valid = target_end.notna()
    dates = dates[valid].reset_index(drop=True)
    target_end = target_end[valid].reset_index(drop=True)
    folds = make_distribution_folds(dates, target_end, n_folds=3, test_fraction=0.30, validation_fraction=0.10)
    all_test = np.concatenate([fold.test for fold in folds])
    assert len(np.unique(all_test)) == len(all_test)
    for fold in folds:
        assert (target_end.iloc[fold.train] < fold.validation_start).all()
        assert (target_end.iloc[fold.validation] < fold.test_start).all()
        assert fold.train.max() < fold.validation.min() < fold.test.min()


def test_weighted_distribution_metrics_are_finite():
    samples = np.array([-0.03, -0.01, 0.0, 0.01, 0.04])
    weights = np.array([0.05, 0.15, 0.40, 0.30, 0.10])
    row = _weighted_distribution_row(0.005, samples, weights)
    assert all(np.isfinite(value) for value in row.values())
    assert 0 <= row["pit"] <= 1
    assert row["crps"] >= 0


def test_distribution_bootstrap_is_paired_and_reports_zero_crossing():
    rows = []
    for date in pd.date_range("2020-01-01", periods=40):
        for mode, crps in (
            ("point_estimate", 0.03),
            ("posterior_mean_mc", 0.02),
            ("variational_posterior", 0.01),
        ):
            rows.append(
                {
                    "horizon": 20,
                    "date": date,
                    "fold": 0,
                    "seed": 42,
                    "scenario_mode": mode,
                    "actual_return": 0.0,
                    "q01": -0.03,
                    "q05": -0.02,
                    "mdd_q025": -0.2,
                    "mdd_q05": -0.15,
                    "mdd_q95": -0.01,
                    "mdd_q975": 0.0,
                    "actual_max_drawdown": -0.05,
                    "crps": crps,
                    "nlpd": crps,
                    "interval_score_50": crps,
                    "interval_score_80": crps,
                    "interval_score_90": crps,
                    "interval_score_95": crps,
                    "coverage_50": 1.0,
                    "coverage_80": 1.0,
                    "coverage_90": 1.0,
                    "coverage_95": 1.0,
                }
            )
    result = bootstrap_distribution_differences(pd.DataFrame(rows), replicates=30, block_length=5)
    crps = result[(result["benchmark"] == "point_estimate") & (result["metric"] == "crps")].iloc[0]
    assert crps["mean_diff_vb_minus_benchmark"] < 0
    assert crps["ci_excludes_zero"]
