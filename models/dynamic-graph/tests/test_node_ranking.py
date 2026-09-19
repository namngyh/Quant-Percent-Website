"""Cross-sectional node ranking."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.evaluation.ranking import (
    decile_portfolios,
    ic_summary,
    information_coefficient,
    portfolio_turnover,
    ranking_metrics,
)
from dynamicgraph.training.node_ranking import (
    CENTRALITY_FEATURE_NAMES,
    NEIGHBOR_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    NODE_FEATURE_SETS,
    node_ranking_verdict,
)


def test_feature_sets_are_nested():
    """Set B must contain A, and C must contain B, or the comparison is meaningless."""
    node = set(NODE_FEATURE_SETS["node"])
    centrality = set(NODE_FEATURE_SETS["node_plus_centrality"])
    neighbor = set(NODE_FEATURE_SETS["node_plus_neighbor"])
    assert node < centrality < neighbor
    assert centrality - node == set(CENTRALITY_FEATURE_NAMES)
    assert neighbor - centrality == set(NEIGHBOR_FEATURE_NAMES)


def test_node_feature_set_carries_no_network_information():
    """Feature set A is the baseline; a network column leaking in would void it.

    Matching is against the declared network feature names rather than
    substrings: `market_relative_strength_20d` is a price feature (return
    relative to the index) and merely happens to contain the word "strength".
    """
    network = set(CENTRALITY_FEATURE_NAMES) | set(NEIGHBOR_FEATURE_NAMES)
    leaked = sorted(set(NODE_FEATURE_NAMES) & network)
    assert not leaked, f"network features leaked into the node-only baseline: {leaked}"

    # Markers that can only come from the graph, whatever the naming scheme.
    unambiguous = ("centrality", "pagerank", "community", "coreness", "clustering",
                   "participation", "neighbor", "eigenvector")
    suspicious = [
        f for f in NODE_FEATURE_NAMES if any(m in f.lower() for m in unambiguous)
    ]
    assert not suspicious, f"graph-derived columns in the node-only baseline: {suspicious}"


def test_information_coefficient_detects_perfect_ordering():
    dates = pd.bdate_range("2022-01-01", periods=40)
    tickers = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(3)
    realized = pd.DataFrame(rng.normal(size=(40, 10)), index=dates, columns=tickers)

    ic = information_coefficient(realized, realized, "spearman")
    assert np.allclose(ic.dropna(), 1.0)

    ic_inverted = information_coefficient(-realized, realized, "spearman")
    assert np.allclose(ic_inverted.dropna(), -1.0)


def test_ic_summary_reports_dispersion_and_significance():
    ic = pd.Series(np.random.default_rng(4).normal(0.05, 0.15, 250))
    summary = ic_summary(ic)
    for key in ("ic_mean", "ic_std", "ic_ir", "ic_positive_rate", "ic_t_stat", "n"):
        assert key in summary
    assert summary["n"] == 250
    assert np.isfinite(summary["ic_t_stat"])


def test_ic_summary_handles_empty_input():
    summary = ic_summary(pd.Series(dtype=float))
    assert summary["n"] == 0
    assert np.isnan(summary["ic_mean"])


def test_decile_portfolios_spread_has_the_right_sign():
    dates = pd.bdate_range("2022-01-01", periods=60)
    tickers = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(5)
    realized = pd.DataFrame(rng.normal(size=(60, 10)), index=dates, columns=tickers)

    portfolios = decile_portfolios(realized, realized, n_buckets=5)
    assert not portfolios.empty
    # Predicting the outcome exactly must give a positive long-short spread.
    assert portfolios["long_short_spread"].mean() > 0


def test_portfolio_turnover_is_bounded():
    dates = pd.bdate_range("2022-01-01", periods=30)
    frame = pd.DataFrame(
        {"top_bucket_members": [[f"T{i}" for i in range(3)] for _ in range(30)]}, index=dates
    )
    turnover = portfolio_turnover(frame)
    assert (turnover.dropna() == 0.0).all(), "an unchanged bucket must have zero turnover"

    rng = np.random.default_rng(6)
    varying = pd.DataFrame(
        {"top_bucket_members": [list(rng.choice(20, 3, replace=False).astype(str)) for _ in range(30)]},
        index=dates,
    )
    turnover = portfolio_turnover(varying)
    assert turnover.dropna().between(0, 1).all()


def test_verdict_requires_statistical_significance():
    """A positive IC alone must not be reported as an improvement."""
    summary = pd.DataFrame(
        [
            {"feature_set": "node", "ic_ic_mean": 0.010, "ic_ic_t_stat": 0.4},
            {
                "feature_set": "node_plus_centrality",
                "ic_ic_mean": 0.020,
                "ic_ic_t_stat": 0.9,
                "ic_difference": 0.010,
                "ic_difference_ci_lower": -0.012,
                "ic_difference_ci_upper": 0.032,
                "ic_difference_p_adjusted": 0.41,
            },
        ]
    )
    verdict = node_ranking_verdict(summary)
    assert verdict["verdict"] == "improvement_not_significant"
    assert "paired IC improvement" in verdict["interpretation"]


def test_verdict_accepts_a_significant_improvement():
    summary = pd.DataFrame(
        [
            {"feature_set": "node", "ic_ic_mean": 0.010, "ic_ic_t_stat": 0.5},
            {
                "feature_set": "node_plus_neighbor",
                "ic_ic_mean": 0.045,
                "ic_ic_t_stat": 3.1,
                "ic_difference": 0.035,
                "ic_difference_ci_lower": 0.010,
                "ic_difference_ci_upper": 0.060,
                "ic_difference_p_adjusted": 0.018,
            },
        ]
    )
    verdict = node_ranking_verdict(summary)
    assert verdict["verdict"] == "network_features_improve_ranking"
    assert verdict["best_feature_set"] == "node_plus_neighbor"


def test_verdict_does_not_confuse_significant_candidate_ic_with_incremental_value():
    summary = pd.DataFrame(
        [
            {"feature_set": "node", "ic_ic_mean": 0.100, "ic_ic_t_stat": 8.0},
            {
                "feature_set": "node_plus_neighbor",
                "ic_ic_mean": 0.110,
                "ic_ic_t_stat": 9.0,
                "ic_difference": 0.010,
                "ic_difference_ci_lower": -0.015,
                "ic_difference_ci_upper": 0.035,
                "ic_difference_p_adjusted": 0.72,
            },
        ]
    )
    verdict = node_ranking_verdict(summary)
    assert verdict["verdict"] == "improvement_not_significant"
    assert verdict["best_ic_t_stat"] == 9.0
    assert verdict["paired_p_adjusted"] == pytest.approx(0.72)


def test_verdict_reports_no_improvement():
    summary = pd.DataFrame(
        [
            {"feature_set": "node", "ic_ic_mean": 0.030, "ic_ic_t_stat": 2.5},
            {"feature_set": "node_plus_centrality", "ic_ic_mean": 0.010, "ic_ic_t_stat": 0.8},
        ]
    )
    verdict = node_ranking_verdict(summary)
    assert verdict["verdict"] == "no_improvement"
    assert "not expected return" in verdict["interpretation"]


def test_verdict_always_carries_the_evaluation_caveat():
    summary = pd.DataFrame(
        [
            {"feature_set": "node", "ic_ic_mean": 0.01, "ic_ic_t_stat": 3.0},
            {"feature_set": "node_plus_neighbor", "ic_ic_mean": 0.05, "ic_ic_t_stat": 4.0},
        ]
    )
    verdict = node_ranking_verdict(summary)
    assert "not a tradable strategy" in verdict["caveat"]


def test_verdict_is_inconclusive_without_a_baseline():
    summary = pd.DataFrame([{"feature_set": "node_plus_centrality", "ic_ic_mean": 0.02}])
    assert node_ranking_verdict(summary)["verdict"] == "inconclusive"
    assert node_ranking_verdict(pd.DataFrame())["verdict"] == "inconclusive"


def test_build_node_target_ranks_within_each_date():
    from types import SimpleNamespace

    dates = pd.bdate_range("2022-01-01", periods=20)
    tickers = [f"T{i}" for i in range(5)]
    index = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    rng = np.random.default_rng(7)
    node_forward = pd.DataFrame(
        {"future_risk_adjusted_return_20d": rng.normal(size=len(index))}, index=index
    )
    state = SimpleNamespace(targets=SimpleNamespace(node_forward=node_forward))

    from dynamicgraph.training.node_ranking import build_node_target

    target = build_node_target(state, 20, "risk_adjusted_return")
    wide = target.unstack("ticker")
    # Percentile ranks within a date of 5 assets are {0.2, 0.4, 0.6, 0.8, 1.0}.
    assert np.allclose(sorted(wide.iloc[0].to_numpy()), [0.2, 0.4, 0.6, 0.8, 1.0])
    assert wide.min().min() > 0 and wide.max().max() <= 1.0


def test_rank_portfolio_uses_raw_returns_not_percentile_target():
    dates = pd.bdate_range("2024-01-01", periods=2)
    tickers = [f"T{i}" for i in range(10)]
    scores = pd.DataFrame(
        [np.arange(10, dtype=float), np.arange(10, dtype=float)],
        index=dates,
        columns=tickers,
    )
    raw_returns = pd.DataFrame(
        [
            [-0.10, -0.08, -0.06, -0.04, -0.02, 0.01, 0.02, 0.03, 0.08, 0.12],
            [-0.05, -0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.04, 0.06, 0.10],
        ],
        index=dates,
        columns=tickers,
    )
    metrics = ranking_metrics(
        scores, raw_returns, n_buckets=5, cost_bps=0.0, horizon=1
    )
    # Top bucket is T8/T9 and bottom bucket is T0/T1.
    expected_top = np.mean([0.10, 0.08])
    expected_bottom = np.mean([-0.075, -0.06])
    expected_spread = expected_top - expected_bottom
    assert metrics["top_bucket_return"] == pytest.approx(expected_top)
    assert metrics["bottom_bucket_return"] == pytest.approx(expected_bottom)
    assert metrics["long_short_spread"] == pytest.approx(expected_spread)
    assert metrics["cost_adjusted_spread_annualized"] == pytest.approx(expected_spread * 252)


def test_raw_return_scale_changes_portfolio_return_but_not_rank_ic():
    dates = pd.bdate_range("2024-01-01", periods=20)
    tickers = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(81)
    scores = pd.DataFrame(rng.normal(size=(20, 10)), index=dates, columns=tickers)
    raw_returns = scores * 0.01
    base = ranking_metrics(scores, raw_returns, horizon=1, cost_bps=0.0)
    scaled = ranking_metrics(scores, raw_returns * 7.0, horizon=1, cost_bps=0.0)
    assert scaled["long_short_spread"] == pytest.approx(base["long_short_spread"] * 7.0)
    assert scaled["spearman_ic_mean"] == pytest.approx(base["spearman_ic_mean"])


def test_long_short_turnover_and_cost_use_portfolio_weights():
    dates = pd.bdate_range("2024-01-01", periods=2)
    tickers = [f"T{i}" for i in range(10)]
    scores = pd.DataFrame(
        [np.arange(10), np.arange(9, -1, -1)], index=dates, columns=tickers
    )
    raw_returns = pd.DataFrame(0.0, index=dates, columns=tickers)
    metrics = ranking_metrics(scores, raw_returns, horizon=1, cost_bps=25.0)
    # Both long and short books are fully reversed: normalized one-way
    # long-short turnover is 2 and traded gross notional is 4.
    assert metrics["mean_turnover"] == pytest.approx(2.0)
    assert metrics["estimated_annual_cost"] == pytest.approx(4.0 * 0.0025 * 252)
    assert metrics["cost_adjusted_spread_annualized"] == pytest.approx(
        -metrics["estimated_annual_cost"]
    )


def test_ic_t_stat_accounts_for_overlapping_windows():
    """Daily-computed h-day IC overlaps by h-1 days.

    Treating 1,323 overlapping observations as independent inflates the
    t-statistic roughly threefold. The reported `ic_t_stat` must use a
    Newey-West standard error; the naive value is kept only for comparison.
    """
    rng = np.random.default_rng(11)
    # AR(1) with phi=0.85 mimics the ~0.86 lag-1 autocorrelation measured on
    # the real 20-day IC series.
    n, phi = 1300, 0.85
    noise = rng.normal(0, 0.13, n)
    series = np.empty(n)
    series[0] = noise[0]
    for t in range(1, n):
        series[t] = phi * series[t - 1] + noise[t]
    ic = pd.Series(series + 0.10)

    summary = ic_summary(ic, horizon=20)
    assert summary["ic_t_stat"] < summary["ic_t_stat_iid"], (
        "HAC t-statistic must be smaller than the i.i.d. one on autocorrelated IC"
    )
    assert summary["ic_t_stat_iid"] / summary["ic_t_stat"] > 2, (
        "the overlap correction should be substantial at h=20"
    )
    assert summary["n_effective"] == pytest.approx(n / 20)
    assert summary["ic_autocorr_lag1"] > 0.7


def test_ic_summary_reduces_to_iid_at_horizon_one():
    rng = np.random.default_rng(12)
    ic = pd.Series(rng.normal(0.02, 0.1, 500))
    summary = ic_summary(ic, horizon=1)
    assert summary["ic_t_stat"] == pytest.approx(summary["ic_t_stat_iid"], rel=1e-9)
    assert summary["n_effective"] == 500


def test_ic_ir_is_scaled_by_effective_rebalances():
    """Annualising a 20-day IC by sqrt(252) would count each rebalance 20 times."""
    ic = pd.Series([0.10] * 400)
    ic = ic + np.random.default_rng(13).normal(0, 0.2, 400)
    daily = ic_summary(ic, horizon=1)["ic_ir"]
    monthly = ic_summary(ic, horizon=20)["ic_ir"]
    assert monthly < daily
    assert monthly == pytest.approx(daily / np.sqrt(20), rel=1e-6)


def test_newey_west_se_exceeds_iid_se_under_autocorrelation():
    from dynamicgraph.evaluation.ranking import newey_west_se

    rng = np.random.default_rng(14)
    n, phi = 800, 0.8
    noise = rng.normal(0, 1, n)
    x = np.empty(n)
    x[0] = noise[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + noise[t]

    hac = newey_west_se(x, lag=19)
    iid = x.std(ddof=1) / np.sqrt(n)
    assert hac > iid, "HAC standard error must exceed the i.i.d. one on AR(1) data"
