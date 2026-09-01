"""Capital allocation: estimators, weight rules, and the no-look-ahead contract."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.allocation.backtest import (
    AllocationBacktestConfig,
    _community_labels,
    _rebalance_positions,
    _to_simple_returns,
    run_allocation_backtest,
)
from dynamicgraph.allocation.covariance import (
    COVARIANCE_ESTIMATORS,
    covariance_forecast_error,
    estimate_allocation_covariance,
)
from dynamicgraph.allocation.diagnostics import (
    diversification_ratio,
    effective_number_of_bets,
    risk_contributions,
    weight_concentration,
)
from dynamicgraph.allocation.evaluation import (
    annualized_volatility,
    max_drawdown,
    performance_metrics,
)
from dynamicgraph.allocation.portfolios import (
    PORTFOLIO_RULES,
    build_weights,
    community_risk_parity,
    minimum_variance,
    risk_parity,
)
from dynamicgraph.evaluation.bootstrap import paired_series_bootstrap


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _factor_returns(n_days: int = 500, n_assets: int = 12, seed: int = 0) -> pd.DataFrame:
    """Log returns with one common factor, so the assets are genuinely correlated."""
    rng = np.random.default_rng(seed)
    factor = rng.normal(0, 0.012, n_days)
    loadings = rng.uniform(0.5, 1.4, n_assets)
    idiosyncratic = rng.normal(0, 0.010, (n_days, n_assets))
    values = np.outer(factor, loadings) + idiosyncratic
    return pd.DataFrame(
        values,
        index=pd.bdate_range("2015-01-01", periods=n_days),
        columns=[f"T{i:02d}" for i in range(n_assets)],
    )


# ---------------------------------------------------------------------------
# covariance estimators
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("estimator", COVARIANCE_ESTIMATORS)
def test_every_estimator_returns_a_usable_covariance(estimator):
    returns = _factor_returns(120, 10).to_numpy()
    estimate = estimate_allocation_covariance(returns, estimator=estimator)
    covariance = estimate.covariance
    assert covariance.shape == (10, 10)
    assert np.allclose(covariance, covariance.T), "covariance must be symmetric"
    assert np.linalg.eigvalsh(covariance).min() > 0, "covariance must be positive definite"


@pytest.mark.parametrize("estimator", COVARIANCE_ESTIMATORS)
def test_estimators_agree_on_the_diagonal(estimator):
    """Only the correlation structure may differ between estimators.

    The whole comparison rests on this: if one estimator also shrank the
    variances, a lower backtested volatility could come from mis-stating the
    risk level rather than from a better dependence estimate.
    """
    returns = _factor_returns(120, 10).to_numpy()
    reference = np.var(returns, axis=0, ddof=1)
    estimate = estimate_allocation_covariance(returns, estimator=estimator)
    # The ridge adds a common constant; compare ratios rather than levels.
    ratio = np.diag(estimate.covariance) / reference
    assert np.allclose(ratio, ratio[0], rtol=1e-3), (
        f"{estimator} distorted the variances relative to one another"
    )
    assert abs(ratio[0] - 1.0) < 0.01, f"{estimator} changed the overall risk level"


def test_diagonal_estimator_removes_all_correlation():
    returns = _factor_returns(120, 8).to_numpy()
    estimate = estimate_allocation_covariance(returns, estimator="diagonal")
    off_diagonal = estimate.correlation[np.triu_indices(8, k=1)]
    assert np.allclose(off_diagonal, 0.0)
    assert estimate.off_diagonal_zeros == 1.0


def test_glasso_actually_zeroes_some_conditional_dependencies():
    """A penalty that leaves the precision matrix dense is not doing anything."""
    returns = _factor_returns(120, 15, seed=3).to_numpy()
    estimate = estimate_allocation_covariance(returns, estimator="glasso", alpha=0.10)
    assert estimate.off_diagonal_zeros > 0.05, (
        "graphical lasso produced an essentially dense precision matrix"
    )
    sample = estimate_allocation_covariance(returns, estimator="sample")
    assert estimate.condition_number < sample.condition_number, (
        "regularisation should improve conditioning"
    )


def test_sample_covariance_is_ill_conditioned_when_short():
    """T <= N is the regime the whole regularisation argument is about."""
    returns = _factor_returns(20, 25, seed=4).to_numpy()
    sample = estimate_allocation_covariance(returns, estimator="sample")
    shrunk = estimate_allocation_covariance(returns, estimator="ledoit_wolf")
    assert sample.condition_number > shrunk.condition_number * 10


def test_covariance_forecast_error_prefers_the_true_matrix():
    rng = np.random.default_rng(7)
    truth = np.array([[4e-4, 1e-4], [1e-4, 9e-4]])
    realized = rng.multivariate_normal([0, 0], truth, size=4000)
    good = covariance_forecast_error(truth, realized)
    bad = covariance_forecast_error(np.diag([1e-2, 1e-2]), realized)
    assert good["log_likelihood"] > bad["log_likelihood"]
    assert good["qlike"] < bad["qlike"]


# ---------------------------------------------------------------------------
# weight rules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rule", PORTFOLIO_RULES)
def test_weights_are_long_only_and_sum_to_one(rule):
    covariance = estimate_allocation_covariance(
        _factor_returns(120, 10).to_numpy(), "ledoit_wolf"
    ).covariance
    weights = build_weights(rule, covariance, max_weight=0.25)
    assert weights.shape == (10,)
    assert np.all(weights >= -1e-12), "no short positions"
    assert np.isclose(weights.sum(), 1.0)
    assert weights.max() <= 0.25 + 1e-9, "every rule must respect the common cap"


def test_minimum_variance_respects_the_weight_cap():
    """Without the cap the optimiser concentrates wherever estimation error points."""
    rng = np.random.default_rng(11)
    n = 12
    deviation = np.concatenate([[0.002], rng.uniform(0.02, 0.03, n - 1)])
    correlation = np.full((n, n), 0.5)
    np.fill_diagonal(correlation, 1.0)
    covariance = correlation * np.outer(deviation, deviation)

    uncapped = minimum_variance(covariance, max_weight=1.0)
    capped = minimum_variance(covariance, max_weight=0.15)
    assert uncapped.max() > 0.5, "the low-variance asset should dominate without a cap"
    assert capped.max() <= 0.15 + 1e-6


def test_minimum_variance_beats_equal_weight_on_the_matrix_it_was_given():
    """In sample this must hold by construction; if it fails, the optimiser is broken."""
    covariance = estimate_allocation_covariance(
        _factor_returns(250, 10, seed=5).to_numpy(), "ledoit_wolf"
    ).covariance
    weights = minimum_variance(covariance, max_weight=1.0)
    equal = np.full(10, 0.1)
    assert weights @ covariance @ weights <= equal @ covariance @ equal + 1e-12


def test_risk_parity_equalises_risk_contributions():
    covariance = estimate_allocation_covariance(
        _factor_returns(250, 8, seed=6).to_numpy(), "ledoit_wolf"
    ).covariance
    weights = risk_parity(covariance)
    contributions = risk_contributions(weights, covariance)
    assert np.allclose(contributions, 1.0 / 8, atol=1e-4), (
        f"risk contributions are not equal: {contributions}"
    )


def test_community_risk_parity_splits_the_budget_across_communities():
    """The two community sleeves must receive equal aggregate risk."""
    n = 9
    covariance = np.eye(n) * 4e-4
    communities = [0, 0, 0, 0, 0, 0, 1, 1, 1]  # 6 vs 3
    weights = community_risk_parity(covariance, communities=communities)
    contributions = risk_contributions(weights, covariance)
    assert contributions[:6].sum() == pytest.approx(
        contributions[6:].sum(), abs=1e-5
    )
    assert weights[:6].sum() > weights[6:].sum(), (
        "the larger diversified sleeve needs more capital to carry equal risk"
    )


def test_community_risk_parity_degrades_rather_than_fails():
    covariance = np.eye(5) * 4e-4
    fallback = community_risk_parity(covariance, communities=None)
    assert np.isclose(fallback.sum(), 1.0)
    single = community_risk_parity(covariance, communities=[0, 0, 0, 0, 0])
    assert np.allclose(single, 0.2)


def test_common_weight_cap_rejects_an_infeasible_simplex():
    covariance = np.eye(4)
    with pytest.raises(ValueError, match="Infeasible max_weight"):
        build_weights("equal_weight", covariance, max_weight=0.20)


@pytest.mark.parametrize("rule", PORTFOLIO_RULES)
def test_common_weight_cap_is_applied_to_every_rule(rule):
    covariance = np.diag([1.0, 2.0, 3.0, 4.0, 5.0])
    weights = build_weights(
        rule,
        covariance,
        communities=[0, 0, 1, 1, 1],
        max_weight=0.25,
    )
    assert weights.sum() == pytest.approx(1.0)
    assert weights.min() >= -1e-12
    assert weights.max() <= 0.25 + 1e-12


def test_unknown_rule_is_rejected():
    with pytest.raises(ValueError, match="Unknown portfolio rule"):
        build_weights("magic", np.eye(3))


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------
def test_effective_number_of_bets_counts_independent_risk_not_positions():
    n = 10
    independent = np.eye(n) * 4e-4
    weights = np.full(n, 1.0 / n)
    assert effective_number_of_bets(weights, independent) == pytest.approx(n, rel=1e-6)

    # One factor, no idiosyncratic risk: ten positions, one bet.
    single_factor = np.full((n, n), 4e-4)
    assert effective_number_of_bets(weights, single_factor) == pytest.approx(1.0, abs=1e-6)
    assert weight_concentration(weights) == pytest.approx(n)


def test_diversification_ratio_is_one_under_perfect_correlation():
    n = 6
    covariance = np.full((n, n), 4e-4)
    weights = np.full(n, 1.0 / n)
    assert diversification_ratio(weights, covariance) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# performance metrics
# ---------------------------------------------------------------------------
def test_annualized_volatility_matches_the_definition():
    rng = np.random.default_rng(9)
    returns = rng.normal(0, 0.01, 5000)
    assert annualized_volatility(returns) == pytest.approx(0.01 * np.sqrt(252), rel=0.05)


def test_max_drawdown_finds_the_worst_peak_to_trough():
    returns = np.array([0.10, -0.20, -0.20, 0.05])
    # 1.10 -> 0.88 -> 0.704, peak 1.10, trough 0.704 => -36%
    assert max_drawdown(returns) == pytest.approx(0.704 / 1.10 - 1.0, rel=1e-9)


def test_performance_metrics_on_an_empty_series():
    assert performance_metrics(pd.Series(dtype=float))["n_days"] == 0


# ---------------------------------------------------------------------------
# no look-ahead
# ---------------------------------------------------------------------------
def test_rebalance_positions_never_include_the_final_date():
    """A weight formed on the last date has no future return to be judged on."""
    index = pd.bdate_range("2020-01-01", periods=100)
    positions = _rebalance_positions(index, window=20, step=10, start=None)
    assert min(positions) == 19
    assert max(positions) <= len(index) - 2


def test_weights_do_not_change_when_the_future_is_altered():
    """The decisive no-look-ahead test.

    Two histories identical up to a cut date and completely different after it
    must produce identical weights at every rebalance on or before the cut.
    """
    returns = _factor_returns(400, 8, seed=21)
    cut = 300
    tampered = returns.copy()
    rng = np.random.default_rng(99)
    tampered.iloc[cut:] = rng.normal(0, 0.20, tampered.iloc[cut:].shape)

    config = AllocationBacktestConfig(
        estimation_window=60, rebalance_days=20, min_assets=5, cost_bps_per_side=0.0
    )
    original = run_allocation_backtest(returns, "ledoit_wolf", "minimum_variance", config)
    altered = run_allocation_backtest(tampered, "ledoit_wolf", "minimum_variance", config)

    cut_date = returns.index[cut - 1]
    a = original.weights.loc[original.weights.index <= cut_date]
    b = altered.weights.loc[altered.weights.index <= cut_date]
    assert not a.empty, "the test needs at least one rebalance before the cut"
    pd.testing.assert_frame_equal(a, b)


def test_community_labels_never_reach_forward_in_time():
    partitions = {
        pd.Timestamp("2020-01-31"): {"A": 0, "B": 1},
        pd.Timestamp("2020-03-31"): {"A": 1, "B": 0},
    }
    # A date between the two partitions must use the EARLIER one.
    labels = _community_labels(partitions, pd.Timestamp("2020-02-15"), ["A", "B"])
    assert labels == [0, 1]
    # A date before any partition has nothing legitimate to use.
    assert _community_labels(partitions, pd.Timestamp("2019-12-01"), ["A", "B"]) is None


def test_portfolio_returns_start_strictly_after_the_first_rebalance():
    returns = _factor_returns(200, 6, seed=31)
    config = AllocationBacktestConfig(estimation_window=60, rebalance_days=20, min_assets=4)
    result = run_allocation_backtest(returns, "sample", "risk_parity", config)
    assert result.portfolio_returns.index.min() > result.weights.index.min()


def test_missing_held_asset_contributes_zero_without_implicit_reallocation():
    from dynamicgraph.allocation.backtest import _portfolio_returns

    weights = pd.Series({"A": 0.5, "B": 0.5})
    holding = pd.DataFrame(
        {"A": [0.10, -0.04], "B": [np.nan, np.nan]},
        index=pd.bdate_range("2024-01-01", periods=2),
    )
    realized = _portfolio_returns(weights, holding, missing_return_policy="zero")
    assert realized.iloc[0] == pytest.approx(0.05)
    assert realized.iloc[1] == pytest.approx(-0.02)


def test_next_close_execution_lags_weights_and_realized_returns_one_session():
    returns = _factor_returns(120, 5, seed=32)
    config = AllocationBacktestConfig(
        estimation_window=60,
        rebalance_days=20,
        min_assets=3,
        execution_lag_sessions=1,
        execution_convention="next_close",
        cost_bps_per_side=0.0,
    )
    result = run_allocation_backtest(returns, "sample", "equal_weight", config)
    first_signal = returns.index[59]
    first_execution = returns.index[60]
    first_realized = returns.index[61]
    assert result.diagnostics.index[0] == first_execution
    assert result.diagnostics.iloc[0]["signal_date"] == first_signal
    assert result.weights.index[0] == first_execution
    assert result.portfolio_returns.index[0] == first_realized
    assert result.notes and "next_close" in result.notes[0]


# ---------------------------------------------------------------------------
# backtest mechanics
# ---------------------------------------------------------------------------
def test_log_returns_are_converted_before_being_weighted():
    """`w' r` is the portfolio return only for simple returns."""
    log_returns = pd.DataFrame({"A": [0.10, -0.10]})
    simple = _to_simple_returns(log_returns)
    assert simple["A"].iloc[0] == pytest.approx(np.exp(0.10) - 1.0)
    assert simple["A"].iloc[0] != pytest.approx(0.10)


def test_costs_reduce_realised_returns():
    returns = _factor_returns(300, 8, seed=41)
    free = AllocationBacktestConfig(
        estimation_window=60, rebalance_days=20, min_assets=5, cost_bps_per_side=0.0
    )
    expensive = AllocationBacktestConfig(
        estimation_window=60, rebalance_days=20, min_assets=5, cost_bps_per_side=100.0
    )
    a = run_allocation_backtest(returns, "ledoit_wolf", "minimum_variance", free)
    b = run_allocation_backtest(returns, "ledoit_wolf", "minimum_variance", expensive)
    assert b.portfolio_returns.sum() < a.portfolio_returns.sum()
    assert (b.costs > 0).all()


def test_equal_weight_backtest_matches_the_naive_average():
    """A sanity anchor: with no costs, equal weight is the cross-sectional mean."""
    returns = _factor_returns(200, 5, seed=51)
    config = AllocationBacktestConfig(
        estimation_window=60, rebalance_days=1, cost_bps_per_side=0.0, min_assets=3
    )
    result = run_allocation_backtest(returns, "sample", "equal_weight", config)
    expected = _to_simple_returns(returns).mean(axis=1)
    aligned = expected.reindex(result.portfolio_returns.index)
    assert np.allclose(result.portfolio_returns, aligned, atol=1e-12)


def test_backtest_rejects_a_history_shorter_than_the_window():
    returns = _factor_returns(30, 5)
    config = AllocationBacktestConfig(estimation_window=60)
    with pytest.raises(ValueError, match="shorter than"):
        run_allocation_backtest(returns, "sample", "equal_weight", config)


def test_missing_assets_are_excluded_not_imputed():
    returns = _factor_returns(200, 6, seed=61)
    returns.iloc[:, 0] = np.nan  # one ticker with no data at all
    config = AllocationBacktestConfig(estimation_window=60, rebalance_days=20, min_assets=3)
    result = run_allocation_backtest(returns, "sample", "risk_parity", config)
    assert returns.columns[0] not in result.weights.columns or (
        result.weights[returns.columns[0]].isna().all()
    )


def test_allocation_config_override_and_round_trip():
    from dynamicgraph.config import load_config

    config = load_config(
        "config/default.yaml",
        overrides={
            "allocation": {
                "rebalance_days": 7,
                "cost_bps_per_side": 99.0,
                "missing_return_policy": "zero",
                "execution_lag_sessions": 2,
            }
        },
    )
    assert config.allocation.rebalance_days == 7
    assert config.allocation.cost_bps_per_side == pytest.approx(99.0)
    assert config.allocation.execution_lag_sessions == 2
    payload = config.to_dict()
    assert payload["allocation"]["rebalance_days"] == 7
    assert payload["allocation"]["missing_return_policy"] == "zero"


def test_unknown_allocation_field_is_rejected():
    from dynamicgraph.config import load_config

    with pytest.raises((ValueError, TypeError), match="unknown|Unknown|extra"):
        load_config(
            "config/default.yaml",
            overrides={"allocation": {"silent_typo": 123}},
        )


def test_allocation_uses_fitted_graph_alpha_and_start_date():
    from dynamicgraph.allocation.backtest import AllocationBacktestConfig
    from dynamicgraph.config import load_config
    from dynamicgraph.graphs.specification import FittedGraphSpecification

    config = load_config("config/default.yaml")
    fitted = FittedGraphSpecification(
        selected_alpha=0.137,
        selection_method="cv_train_only",
        estimator="graphical_lasso_on_correlation",
        training_start="2018-01-01",
        training_end="2021-12-31",
        validation_start="2022-01-10",
        validation_end="2022-06-30",
        universe_definition={"method": "liquidity_proxy"},
        feature_specification={"return_type": "residual"},
        convergence_diagnostics=[{"date": "2021-12-31", "converged": True}],
    )
    backtest = AllocationBacktestConfig.from_config(config, fitted_graph_spec=fitted)
    assert backtest.glasso_alpha == pytest.approx(0.137)
    assert backtest.start_date == pd.Timestamp("2021-12-31")
    assert fitted.to_dict()["estimator"] == "graphical_lasso_on_correlation"
    assert fitted.to_dict()["convergence_diagnostics"][0]["converged"]


# ---------------------------------------------------------------------------
# significance testing
# ---------------------------------------------------------------------------
def test_paired_bootstrap_finds_no_difference_between_identical_series():
    rng = np.random.default_rng(71)
    series = pd.Series(rng.normal(0, 0.01, 800))
    test = paired_series_bootstrap(
        series, series.copy(), statistic=annualized_volatility, n_bootstrap=200, lower_is_better=True
    )
    assert test["difference"] == pytest.approx(0.0, abs=1e-12)
    assert not test["significant"]


def test_paired_bootstrap_detects_a_real_volatility_reduction():
    rng = np.random.default_rng(72)
    noisy = pd.Series(rng.normal(0, 0.020, 1200))
    quiet = noisy / 2.0
    test = paired_series_bootstrap(
        quiet, noisy, statistic=annualized_volatility, n_bootstrap=300, lower_is_better=True
    )
    assert test["difference"] < 0
    assert test["significant"], "halving the volatility must register as significant"
    assert test["upper"] < 0


def test_paired_bootstrap_direction_flag_is_respected():
    """`lower_is_better` must flip which tail counts as a win."""
    rng = np.random.default_rng(73)
    noisy = pd.Series(rng.normal(0, 0.020, 1200))
    quiet = noisy / 2.0
    wrong_direction = paired_series_bootstrap(
        quiet, noisy, statistic=annualized_volatility, n_bootstrap=300, lower_is_better=False
    )
    assert not wrong_direction["significant"]
