r"""Walk-forward allocation backtest.

The no-look-ahead rule is enforced in one place, `_rebalance_positions`: weights
formed at date `t` are estimated from the window ending at `t` inclusive, and are
then applied to the returns of `t+1 ... t+h`. No date ever appears in both roles.

Nothing in this module is fitted globally. The graphical-lasso penalty is passed
in already frozen (it was selected on the training period in `stage_graphs`),
the estimation window and the rebalance frequency are configuration, and no
weight rule sees a return it has not already been charged for. That is why the
whole series can be treated as out of sample rather than only the walk-forward
test folds.

Costs are charged at each rebalance on the traded notional, against the weights
*after* they have drifted with the previous period's returns -- charging against
the pre-drift weights would overstate turnover for a buy-and-hold-like rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dynamicgraph.allocation.covariance import (
    covariance_forecast_error,
    estimate_allocation_covariance,
)
from dynamicgraph.allocation.diagnostics import portfolio_diagnostics
from dynamicgraph.allocation.portfolios import build_weights
from dynamicgraph.constants import EPS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class AllocationBacktestConfig:
    estimation_window: int = 60
    rebalance_days: int = 20
    max_weight: float = 0.20
    cost_bps_per_side: float = 15.0
    glasso_alpha: float = 0.02
    min_assets: int = 10
    max_missing_ratio: float = 0.10
    start_date: pd.Timestamp | None = None
    missing_return_policy: str = "zero"
    execution_lag_sessions: int = 1
    execution_convention: str = "next_close"

    @classmethod
    def from_config(
        cls, config: Any, fitted_graph_spec: Any | None = None
    ) -> "AllocationBacktestConfig":
        allocation = getattr(config, "allocation", None)
        graph = getattr(config, "graph", None)
        if allocation is None:
            return cls()
        fitted_alpha = (
            float(fitted_graph_spec.selected_alpha)
            if fitted_graph_spec is not None
            else float(getattr(graph, "graphical_lasso_alpha", 0.02))
        )
        selection_method = (
            str(getattr(fitted_graph_spec, "selection_method", "fixed"))
            if fitted_graph_spec is not None
            else "fixed"
        )
        fitted_start = (
            pd.Timestamp(fitted_graph_spec.training_end)
            if fitted_graph_spec is not None and selection_method != "fixed"
            else None
        )
        return cls(
            estimation_window=int(
                allocation.estimation_window or getattr(graph, "core_window", 60)
            ),
            rebalance_days=int(allocation.rebalance_days),
            max_weight=float(allocation.max_weight),
            cost_bps_per_side=float(allocation.cost_bps_per_side),
            glasso_alpha=fitted_alpha,
            min_assets=int(allocation.min_assets),
            max_missing_ratio=float(getattr(config.data, "max_missing_ratio_per_window", 0.10)),
            start_date=fitted_start,
            missing_return_policy=str(allocation.missing_return_policy),
            execution_lag_sessions=max(1, int(allocation.execution_lag_sessions)),
            execution_convention=str(allocation.execution_convention),
        )


@dataclass
class AllocationBacktestResult:
    estimator: str
    rule: str
    portfolio_returns: pd.Series
    weights: pd.DataFrame
    diagnostics: pd.DataFrame
    costs: pd.Series
    config: AllocationBacktestConfig
    notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.rule}__{self.estimator}"


def _to_simple_returns(log_returns: pd.DataFrame) -> pd.DataFrame:
    """Portfolio arithmetic is linear in simple returns, not log returns.

    `w' r` is only the portfolio return when `r` is simple. At daily magnitudes
    the difference is third-order, but it accumulates over 3,500 days and there
    is no reason to carry the approximation when the conversion is exact.
    """
    return np.expm1(log_returns)


def _rebalance_positions(
    index: pd.DatetimeIndex,
    window: int,
    step: int,
    start: pd.Timestamp | None,
    execution_lag_sessions: int = 0,
) -> list[int]:
    """Integer positions of the rebalance dates.

    The first possible rebalance is at `window - 1` (the first date with a full
    trailing window) and the last is the second-to-last date, because a weight
    formed on the final date has no future return to be evaluated against.
    """
    first = window - 1
    if start is not None:
        candidates = np.nonzero(index >= start)[0]
        if candidates.size:
            first = max(first, int(candidates[0]))
    return list(
        range(first, len(index) - max(1, execution_lag_sessions + 1), max(1, step))
    )


def _eligible_assets(
    window_returns: pd.DataFrame, max_missing_ratio: float, min_assets: int
) -> list[str]:
    """Assets with enough observations inside the estimation window.

    Eligibility is decided on the window alone. Screening on whether an asset
    trades during the *holding* period would be look-ahead, so a name that stops
    trading after the rebalance keeps its weight and simply contributes no return.
    """
    coverage = window_returns.notna().mean()
    eligible = [c for c in window_returns.columns if coverage[c] >= 1.0 - max_missing_ratio]
    return eligible if len(eligible) >= min_assets else []


def _drift_weights(weights: pd.Series, holding_returns: pd.DataFrame) -> pd.Series:
    """Weights at the end of the holding period after price drift."""
    if holding_returns.empty:
        return weights
    growth = (1.0 + holding_returns.reindex(columns=weights.index).fillna(0.0)).prod()
    drifted = weights * growth
    total = float(drifted.sum())
    return drifted / total if total > EPS else weights


def run_allocation_backtest(
    log_returns: pd.DataFrame,
    estimator: str,
    rule: str,
    config: AllocationBacktestConfig,
    communities_by_date: Mapping[pd.Timestamp, Mapping[str, int]] | None = None,
) -> AllocationBacktestResult:
    """One (covariance estimator, weight rule) pair over the whole history."""
    simple = _to_simple_returns(log_returns.sort_index())
    index = simple.index
    positions = _rebalance_positions(
        index,
        config.estimation_window,
        config.rebalance_days,
        config.start_date,
        config.execution_lag_sessions,
    )
    if not positions:
        raise ValueError(
            f"No rebalance dates: {len(index)} observations is shorter than the "
            f"{config.estimation_window}-day estimation window."
        )

    daily_returns: list[pd.Series] = []
    weight_rows: dict[pd.Timestamp, pd.Series] = {}
    diagnostic_rows: list[dict[str, Any]] = []
    cost_rows: dict[pd.Timestamp, float] = {}
    if config.execution_convention != "next_close":
        raise ValueError(
            "Only `next_close` execution is currently implemented; "
            f"received `{config.execution_convention}`."
        )
    if config.missing_return_policy != "zero":
        raise ValueError(
            "Only `zero` missing_return_policy is currently implemented; "
            f"received `{config.missing_return_policy}`."
        )
    notes: list[str] = [
        f"Signals use data through close t, execute at {config.execution_convention} "
        f"after {config.execution_lag_sessions} session(s), and accrue returns only after execution."
    ]
    previous_drifted: pd.Series | None = None

    for position in positions:
        signal_date = index[position]
        execution_position = position + config.execution_lag_sessions
        execution_date = index[execution_position]
        window = simple.iloc[position - config.estimation_window + 1 : position + 1]
        eligible = _eligible_assets(window, config.max_missing_ratio, config.min_assets)
        if not eligible:
            continue

        block = window[eligible].dropna(axis=0, how="any")
        if len(block) < max(10, config.estimation_window // 3):
            continue

        try:
            estimate = estimate_allocation_covariance(
                block.to_numpy(), estimator=estimator, alpha=config.glasso_alpha
            )
        except Exception as exc:
            logger.warning(
                "Covariance estimation failed on %s (%s); skipping.",
                signal_date.date(),
                exc,
            )
            continue

        kwargs: dict[str, Any] = {"max_weight": config.max_weight}
        if rule == "community_risk_parity":
            kwargs["communities"] = _community_labels(
                communities_by_date, signal_date, eligible
            )
            if kwargs["communities"] is None and not any(
                "community partition" in note for note in notes
            ):
                notes.append(
                    "No community partition was available at some rebalance dates; "
                    "community_risk_parity fell back to inverse volatility there."
                )

        weights = pd.Series(
            build_weights(rule, estimate.covariance, **kwargs), index=eligible
        )
        weight_rows[execution_date] = weights

        # ---- costs, charged against the drifted previous book -------------
        traded = 1.0
        if previous_drifted is not None:
            aligned_previous = previous_drifted.reindex(weights.index).fillna(0.0)
            dropped = previous_drifted.drop(labels=weights.index, errors="ignore").abs().sum()
            traded = float((weights - aligned_previous).abs().sum() + dropped)
        cost = traded * config.cost_bps_per_side / 1e4
        cost_rows[execution_date] = cost

        # ---- realised returns over the holding period ---------------------
        start_return = execution_position + 1
        end = min(start_return + config.rebalance_days, len(index))
        holding = simple.iloc[start_return:end]
        if holding.empty:
            continue
        realized = _portfolio_returns(
            weights, holding, missing_return_policy=config.missing_return_policy
        )
        realized.iloc[0] = realized.iloc[0] - cost
        daily_returns.append(realized)
        previous_drifted = _drift_weights(weights, holding)

        row = {
            "date": execution_date,
            "signal_date": signal_date,
            "execution_date": execution_date,
            "execution_convention": config.execution_convention,
            "execution_lag_sessions": config.execution_lag_sessions,
            "n_assets": len(eligible),
            "estimator": estimator,
            "rule": rule,
            "condition_number": estimate.condition_number,
            "off_diagonal_zeros": estimate.off_diagonal_zeros,
            "shrinkage": estimate.shrinkage,
            "turnover_traded": traded,
            "cost": cost,
        }
        row.update(portfolio_diagnostics(weights.to_numpy(), estimate.covariance))
        row.update(
            {
                f"forecast_{k}": v
                for k, v in covariance_forecast_error(
                    estimate.covariance,
                    holding[eligible].fillna(0.0).to_numpy(),
                ).items()
            }
        )
        diagnostic_rows.append(row)

    if not daily_returns:
        raise ValueError(f"Backtest produced no returns for {rule}/{estimator}.")

    portfolio_returns = pd.concat(daily_returns).sort_index()
    portfolio_returns = portfolio_returns[~portfolio_returns.index.duplicated(keep="first")]
    portfolio_returns.name = f"{rule}__{estimator}"

    return AllocationBacktestResult(
        estimator=estimator,
        rule=rule,
        portfolio_returns=portfolio_returns,
        weights=pd.DataFrame(weight_rows).T.sort_index(),
        diagnostics=pd.DataFrame(diagnostic_rows).set_index("date") if diagnostic_rows else pd.DataFrame(),
        costs=pd.Series(cost_rows, name="cost").sort_index(),
        config=config,
        notes=notes,
    )


def _portfolio_returns(
    weights: pd.Series,
    holding: pd.DataFrame,
    missing_return_policy: str = "zero",
) -> pd.Series:
    """Daily portfolio return under an explicit missing-return policy.

    Under the default `zero` policy, a held asset without a print has zero
    mark-to-market return for that session. Its capital remains invested and the
    other positions are not implicitly levered or reallocated.
    """
    if missing_return_policy != "zero":
        raise ValueError(f"Unsupported missing_return_policy `{missing_return_policy}`.")
    available = holding.reindex(columns=weights.index)
    return available.fillna(0.0).mul(weights, axis=1).sum(axis=1)


def _community_labels(
    communities_by_date: Mapping[pd.Timestamp, Mapping[str, int]] | None,
    date: pd.Timestamp,
    assets: Sequence[str],
) -> list[int] | None:
    """Community label per asset at `date`, or None when unavailable.

    Only partitions dated at or before `date` are considered -- reaching forward
    for the next available partition would import future graph structure.
    """
    if not communities_by_date:
        return None
    mapping = communities_by_date.get(date)
    if mapping is None:
        earlier = [d for d in communities_by_date if d <= date]
        if not earlier:
            return None
        mapping = communities_by_date[max(earlier)]
    if not mapping:
        return None
    fallback = max(mapping.values(), default=0) + 1
    return [int(mapping.get(asset, fallback)) for asset in assets]
