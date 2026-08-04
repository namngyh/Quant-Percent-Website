r"""Out-of-sample scoring for the allocation layer.

The primary metric is **realised annualised volatility**, not return. That is a
deliberate choice, not a convenient one: every rule in `portfolios.py` is a
function of the covariance matrix only, so the covariance matrix can only be
held responsible for the risk it produced. Judging these rules on return would
be judging a variance model on a mean forecast it never made -- and the
predictive layer already established that means are not forecastable here.

Return and Sharpe are reported alongside because a risk reduction bought by
quietly holding cash-like defensives is not free, and the reader is entitled to
see what it cost.

Significance comes from a paired moving-block bootstrap on the two return
streams. The i.i.d. alternative would be wrong twice over: daily returns are
volatility-clustered, and two portfolios over the same period share the same
market shocks.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS, TRADING_DAYS_PER_YEAR
from dynamicgraph.evaluation.bootstrap import paired_series_bootstrap
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def annualized_volatility(returns: np.ndarray) -> float:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return np.nan
    return float(values.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def annualized_return(returns: np.ndarray) -> float:
    """Geometric, so it matches what the equity curve actually did."""
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan
    growth = float(np.prod(1.0 + values))
    if growth <= 0:
        return -1.0
    return float(growth ** (TRADING_DAYS_PER_YEAR / values.size) - 1.0)


def sharpe_ratio(returns: np.ndarray) -> float:
    """Excess over a zero risk-free rate; VN deposit rates make this optimistic."""
    volatility = annualized_volatility(returns)
    if not np.isfinite(volatility) or volatility <= EPS:
        return np.nan
    return float(annualized_return(returns) / volatility)


def max_drawdown(returns: np.ndarray) -> float:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan
    equity = np.cumprod(1.0 + values)
    peak = np.maximum.accumulate(equity)
    return float((equity / peak - 1.0).min())


def sortino_ratio(returns: np.ndarray) -> float:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    downside = values[values < 0]
    if downside.size < 2:
        return np.nan
    deviation = float(np.sqrt((downside**2).mean()) * np.sqrt(TRADING_DAYS_PER_YEAR))
    if deviation <= EPS:
        return np.nan
    return float(annualized_return(values) / deviation)


def performance_metrics(returns: pd.Series) -> dict[str, float]:
    """Everything a reader needs to judge one return stream."""
    values = returns.dropna().to_numpy(dtype=float)
    if values.size == 0:
        return {"n_days": 0}
    drawdown = max_drawdown(values)
    return {
        "annual_return": annualized_return(values),
        "annual_volatility": annualized_volatility(values),
        "sharpe": sharpe_ratio(values),
        "sortino": sortino_ratio(values),
        "max_drawdown": drawdown,
        "calmar": (
            annualized_return(values) / abs(drawdown)
            if np.isfinite(drawdown) and abs(drawdown) > EPS
            else np.nan
        ),
        "downside_deviation": float(
            np.sqrt((values[values < 0] ** 2).mean()) * np.sqrt(TRADING_DAYS_PER_YEAR)
        ) if (values < 0).any() else np.nan,
        "var_95_daily": float(np.quantile(values, 0.05)),
        "cvar_95_daily": float(values[values <= np.quantile(values, 0.05)].mean()),
        "skew": float(pd.Series(values).skew()),
        "excess_kurtosis": float(pd.Series(values).kurtosis()),
        "hit_rate": float((values > 0).mean()),
        "n_days": int(values.size),
    }


def summarize_results(results: Sequence[Any]) -> pd.DataFrame:
    """One row per (rule, estimator), performance plus mean diagnostics."""
    rows: list[dict[str, Any]] = []
    for result in results:
        row: dict[str, Any] = {
            "rule": result.rule,
            "estimator": result.estimator,
            "key": result.key,
        }
        row.update(performance_metrics(result.portfolio_returns))
        diagnostics = result.diagnostics
        if not diagnostics.empty:
            for column in (
                "effective_n_bets",
                "effective_n_weights",
                "diversification_ratio",
                "max_weight",
                "max_risk_contribution",
                "ex_ante_volatility_annual",
                "condition_number",
                "off_diagonal_zeros",
                "turnover_traded",
                "forecast_log_likelihood",
            ):
                if column in diagnostics.columns:
                    row[f"mean_{column}"] = float(diagnostics[column].mean())
            row["n_rebalances"] = int(len(diagnostics))
        row["annual_cost_drag"] = float(
            result.costs.mean() * TRADING_DAYS_PER_YEAR / max(result.config.rebalance_days, 1)
        ) if len(result.costs) else np.nan
        # How well the ex-ante volatility forecast matched what happened. A
        # ratio above 1 means the estimator understated risk.
        if not diagnostics.empty and "ex_ante_volatility_annual" in diagnostics.columns:
            ex_ante = float(diagnostics["ex_ante_volatility_annual"].mean())
            realized = row.get("annual_volatility", np.nan)
            row["realized_over_ex_ante_volatility"] = (
                float(realized / ex_ante) if ex_ante > EPS else np.nan
            )
        rows.append(row)
    frame = pd.DataFrame(rows)
    return frame.sort_values("annual_volatility").reset_index(drop=True) if not frame.empty else frame


def compare_against_benchmark(
    results: Sequence[Any],
    benchmark_key: str,
    n_bootstrap: int = 1000,
    block_length: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Paired block-bootstrap tests of every portfolio against one benchmark.

    Volatility is tested with `lower_is_better`, Sharpe with higher-is-better.
    Both are reported for every pair, because a rule that lowers risk while
    lowering return by more has not helped anyone.
    """
    by_key = {r.key: r for r in results}
    if benchmark_key not in by_key:
        raise ValueError(
            f"Benchmark `{benchmark_key}` not among the backtested portfolios: {sorted(by_key)}"
        )
    benchmark = by_key[benchmark_key].portfolio_returns

    rows: list[dict[str, Any]] = []
    for key, result in by_key.items():
        if key == benchmark_key:
            continue
        for name, statistic, lower_is_better in (
            ("annual_volatility", annualized_volatility, True),
            ("sharpe", sharpe_ratio, False),
            ("annual_return", annualized_return, False),
            ("max_drawdown", max_drawdown, False),
        ):
            test = paired_series_bootstrap(
                result.portfolio_returns,
                benchmark,
                statistic=statistic,
                n_bootstrap=n_bootstrap,
                block_length=block_length,
                seed=seed,
                lower_is_better=lower_is_better,
            )
            rows.append(
                {
                    "portfolio": key,
                    "benchmark": benchmark_key,
                    "metric": name,
                    "portfolio_value": test["statistic_a"],
                    "benchmark_value": test["statistic_b"],
                    "difference": test["difference"],
                    "ci_lower": test.get("lower", np.nan),
                    "ci_upper": test.get("upper", np.nan),
                    "p_value": test.get("p_value", np.nan),
                    "significant": test.get("significant", False),
                    "n": test["n"],
                }
            )
    return pd.DataFrame(rows)


def estimator_comparison(
    results: Sequence[Any],
    rule: str,
    baseline_estimator: str = "sample",
    n_bootstrap: int = 1000,
    block_length: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Hold the weight rule fixed and vary only the covariance estimator.

    This is the isolated test of the project's actual claim. Comparing
    `minimum_variance/glasso` against `equal_weight` confounds two changes at
    once; comparing it against `minimum_variance/sample` does not.
    """
    subset = {r.estimator: r for r in results if r.rule == rule}
    if baseline_estimator not in subset:
        return pd.DataFrame()
    baseline = subset[baseline_estimator].portfolio_returns

    rows: list[dict[str, Any]] = []
    for estimator, result in subset.items():
        if estimator == baseline_estimator:
            continue
        test = paired_series_bootstrap(
            result.portfolio_returns,
            baseline,
            statistic=annualized_volatility,
            n_bootstrap=n_bootstrap,
            block_length=block_length,
            seed=seed,
            lower_is_better=True,
        )
        rows.append(
            {
                "rule": rule,
                "estimator": estimator,
                "baseline_estimator": baseline_estimator,
                "volatility": test["statistic_a"],
                "baseline_volatility": test["statistic_b"],
                "volatility_difference": test["difference"],
                "ci_lower": test.get("lower", np.nan),
                "ci_upper": test.get("upper", np.nan),
                "p_value": test.get("p_value", np.nan),
                "significant_reduction": test.get("significant", False),
                "n": test["n"],
            }
        )
    return pd.DataFrame(rows)


def allocation_verdict(
    summary: pd.DataFrame,
    estimator_tests: pd.DataFrame,
    benchmark_tests: pd.DataFrame,
    benchmark_key: str = "equal_weight__sample",
) -> dict[str, Any]:
    """State plainly whether the graph-based covariance earned its place.

    Three separate claims, kept separate on purpose:

    1. does *any* covariance-aware rule beat naive equal weighting?
    2. does the *graphical-lasso* covariance beat the sample covariance at the
       same weight rule?
    3. does the *community* partition beat a covariance-free risk split?

    A yes to (1) with a no to (2) means dependence modelling helped but the
    network layer specifically did not -- which is a different conclusion, and
    the one most likely to be glossed over.
    """
    verdict: dict[str, Any] = {
        "benchmark": benchmark_key,
        "caveat": (
            "Backtested weights ignore market impact, borrow availability, foreign "
            "ownership limits and the VN30 constituent changes over the period. "
            "These are risk-model comparisons, not a tradable strategy."
        ),
    }
    if summary.empty:
        return {**verdict, "verdict": "inconclusive", "interpretation": "No backtest results."}

    benchmark_row = summary[summary["key"] == benchmark_key]
    benchmark_volatility = (
        float(benchmark_row["annual_volatility"].iloc[0]) if not benchmark_row.empty else np.nan
    )
    best = summary.loc[summary["annual_volatility"].idxmin()]
    verdict.update(
        {
            "lowest_volatility_portfolio": str(best["key"]),
            "lowest_volatility": float(best["annual_volatility"]),
            "benchmark_volatility": benchmark_volatility,
        }
    )

    beats_benchmark = False
    if not benchmark_tests.empty:
        volatility_tests = benchmark_tests[benchmark_tests["metric"] == "annual_volatility"]
        winners = volatility_tests[volatility_tests["significant"].astype(bool)]
        beats_benchmark = bool(len(winners))
        verdict["n_significant_volatility_reductions"] = int(len(winners))
        verdict["n_comparisons"] = int(len(volatility_tests))
        if beats_benchmark:
            verdict["significant_vs_benchmark"] = sorted(winners["portfolio"].tolist())

    graph_wins = pd.DataFrame()
    if not estimator_tests.empty:
        graph = estimator_tests[estimator_tests["estimator"] == "glasso"]
        graph_wins = graph[graph["significant_reduction"].astype(bool)]
        verdict["glasso_significant_rules"] = sorted(graph_wins["rule"].tolist())
        verdict["glasso_mean_volatility_difference"] = (
            float(graph["volatility_difference"].mean()) if not graph.empty else np.nan
        )

    community_rows = summary[summary["rule"] == "community_risk_parity"]
    inverse_rows = summary[summary["rule"] == "inverse_volatility"]
    if not community_rows.empty and not inverse_rows.empty:
        verdict["community_vs_inverse_volatility"] = float(
            community_rows["annual_volatility"].min() - inverse_rows["annual_volatility"].min()
        )

    if not beats_benchmark:
        verdict["verdict"] = "no_benefit_over_equal_weight"
        verdict["interpretation"] = (
            "No covariance-aware rule reduced realised volatility significantly "
            "relative to equal weighting. On this universe and period, dependence "
            "modelling did not improve allocation."
        )
    elif len(graph_wins):
        verdict["verdict"] = "graph_covariance_improves_allocation"
        verdict["interpretation"] = (
            "Covariance-aware allocation beat equal weighting, and the sparse "
            "graphical-lasso covariance beat the sample covariance at the same "
            "weight rule. The network layer contributed beyond generic shrinkage."
        )
    else:
        verdict["verdict"] = "covariance_helps_graph_does_not"
        verdict["interpretation"] = (
            "Covariance-aware allocation beat equal weighting, but the sparse "
            "graphical-lasso estimate did not beat the sample covariance at the "
            "same weight rule. The gain came from modelling dependence at all, "
            "not from the network layer specifically."
        )
    return verdict


def build_equity_curves(results: Sequence[Any]) -> pd.DataFrame:
    """Cumulative growth of one unit for every portfolio, on a shared index."""
    curves: dict[str, pd.Series] = {}
    for result in results:
        returns = result.portfolio_returns.dropna()
        curves[result.key] = (1.0 + returns).cumprod()
    if not curves:
        return pd.DataFrame()
    return pd.DataFrame(curves).sort_index()


def rolling_volatility_comparison(
    results: Sequence[Any], window: int = 126
) -> pd.DataFrame:
    """Rolling realised volatility per portfolio, for the time-series figure."""
    columns: dict[str, pd.Series] = {}
    for result in results:
        returns = result.portfolio_returns.dropna()
        columns[result.key] = returns.rolling(window, min_periods=window // 2).std(
            ddof=1
        ) * np.sqrt(TRADING_DAYS_PER_YEAR)
    return pd.DataFrame(columns).sort_index() if columns else pd.DataFrame()
