import numpy as np
import pandas as pd
import pytest

from vnindex_model.conformal import (
    AdaptiveConformalState,
    ConformalPool,
    PendingScore,
    interval_from_scores,
    mature_pending_scores,
    sequential_conformal,
)

ALPHA_LEVELS = [0.50, 0.20, 0.10, 0.05]


def _pool(n: int = 180) -> ConformalPool:
    rng = np.random.default_rng(7)
    return ConformalPool(
        scores=rng.normal(0, 1, n).tolist(),
        regimes=np.tile([0, 1, 2], n // 3).tolist(),
        volatility_bins=np.tile([0, 0, 1, 1, 2, 2], n // 6).tolist(),
    )


def test_interval_from_scores_matches_the_batch_sequential_path():
    pool = _pool()
    scores, regimes, bins = pool.arrays()
    batch = sequential_conformal(
        np.asarray(pool.scores) * 0.01,
        np.zeros(len(scores)),
        np.full(len(scores), 0.01),
        regimes,
        bins,
        np.array([0.004]),
        np.array([0.002]),
        np.array([0.011]),
        np.array([1]),
        np.array([2]),
        20,
        ALPHA_LEVELS,
        "volatility_regime",
        None,
        80,
    )
    online = interval_from_scores(
        scores, regimes, bins, "volatility_regime", 1, 2, 0.002, 0.011, ALPHA_LEVELS, 80
    )
    for column in ["multiplier_95", "lower_95", "upper_95", "lower_50", "upper_50", "var_95"]:
        assert online[column] == pytest.approx(float(batch[column].iloc[0]))
    assert online["stratum_used"] == batch["stratum_used"].iloc[0]
    assert online["score_count"] == int(batch["score_count"].iloc[0])


def test_conformal_pool_window_truncation_keeps_the_arrays_aligned():
    pool = _pool(30)
    pool.append(9.0, 1, 1)
    pool.truncate(10)
    scores, regimes, bins = pool.arrays()
    assert len(scores) == len(regimes) == len(bins) == 10
    assert scores[-1] == 9.0


def test_pending_scores_only_mature_once_their_target_is_observable():
    pending = [
        PendingScore("2024-01-02", 5, "2024-01-09", 0.0, 0.01, 0, 0, {0.05: (-0.02, 0.02)}),
        PendingScore("2024-01-08", 5, "2024-01-15", 0.0, 0.01, 0, 0, {0.05: (-0.02, 0.02)}),
    ]
    pools = {5: ConformalPool([], [], [])}
    remaining, matured = mature_pending_scores(
        pending, pools, pd.Timestamp("2024-01-09"), lambda item: 0.005, {5: None}
    )
    assert [item.origin_date for item in remaining] == ["2024-01-08"]
    assert len(matured) == 1
    assert pools[5].arrays()[0].tolist() == [pytest.approx(0.5)]


def test_pending_score_never_contributes_to_its_own_interval():
    dates = pd.bdate_range("2024-01-01", periods=120)
    horizon = 5
    rng = np.random.default_rng(3)
    prices = 1000 * np.exp(np.cumsum(rng.normal(0, 0.01, len(dates))))
    realized = {
        str(dates[i].date()): float(np.log(prices[i + horizon] / prices[i]))
        for i in range(len(dates) - horizon)
    }
    pool = ConformalPool(rng.normal(0, 1, 100).tolist(), [0] * 100, [0] * 100)
    pools = {horizon: pool}
    pending: list[PendingScore] = []
    for position, date in enumerate(dates[: len(dates) - horizon]):
        pending, _ = mature_pending_scores(
            pending, pools, date, lambda item: realized[item.origin_date], {horizon: None}
        )
        # Every score already pooled must have matured strictly before this origin.
        assert all(pd.Timestamp(item.target_end_date) > date for item in pending)
        target_end = dates[position + horizon]
        pending.append(
            PendingScore(
                str(date.date()), horizon, str(target_end.date()), 0.0, 0.01, 0, 0, {0.05: (-0.02, 0.02)}
            )
        )
    assert len(pool.arrays()[0]) == 100 + len(dates) - 2 * horizon


def test_adaptive_conformal_widens_after_a_miscoverage():
    state = AdaptiveConformalState(gamma=0.05, alpha_target={0.05: 0.05}, alpha_current={0.05: 0.05})
    state.update(0.05, covered=False)
    assert state.alpha_current[0.05] == pytest.approx(0.05 + 0.05 * (0.05 - 1.0))
    assert state.alpha_current[0.05] < 0.05


def test_adaptive_conformal_alpha_stays_inside_the_unit_interval():
    state = AdaptiveConformalState(gamma=0.9, alpha_target={0.05: 0.05}, alpha_current={0.05: 0.05})
    for _ in range(20):
        state.update(0.05, covered=False)
    assert 0.0 < state.alpha_current[0.05] < 1.0
    for _ in range(200):
        state.update(0.05, covered=True)
    assert 0.0 < state.alpha_current[0.05] < 1.0


def test_adaptive_conformal_recovers_nominal_coverage_when_the_pool_is_too_narrow():
    rng = np.random.default_rng(21)
    calibration = rng.normal(0, 1, 400)
    outcomes = rng.normal(0, 1.3, 3000)
    state = AdaptiveConformalState(gamma=0.02, alpha_target={0.05: 0.05}, alpha_current={0.05: 0.05})
    adaptive_hits, static_hits = [], []
    static_multiplier = float(np.quantile(np.abs(calibration), 0.95))
    for outcome in outcomes:
        multiplier = float(np.quantile(np.abs(calibration), 1.0 - state.alpha_current[0.05]))
        covered = abs(outcome) <= multiplier
        adaptive_hits.append(covered)
        static_hits.append(abs(outcome) <= static_multiplier)
        state.update(0.05, covered=covered)
    adaptive_coverage = float(np.mean(adaptive_hits[1000:]))
    assert abs(adaptive_coverage - 0.95) < abs(float(np.mean(static_hits[1000:])) - 0.95)
    assert 0.92 <= adaptive_coverage <= 0.98
