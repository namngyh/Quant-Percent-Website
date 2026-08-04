r"""Cross-sectional node ranking (brief sections 21.4 and 22).

Answers a different question from the market-level stress model: *can the
network order the 30 constituents by forward risk-adjusted return?*

Three nested feature sets isolate what the graph contributes:

    node                 per-stock return / volatility / drawdown / liquidity
    node_plus_centrality + the stock's own position in the network
    node_plus_neighbor   + aggregates over its neighbours in the network

Evaluation is rank-based (Spearman IC, IC information ratio, decile spread)
rather than RMSE, because ordering is what a cross-sectional model is for. The
long-short spread is reported before and after transaction costs, and is an
evaluation device -- not a strategy, and not evidence of a causal effect.

Folds, purging and embargo are shared with the market-level experiment, so a
node label window can never reach into an evaluated block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.evaluation.ranking import (
    decile_portfolios,
    ic_summary,
    information_coefficient,
    newey_west_se,
    portfolio_turnover,
)
from dynamicgraph.logging_config import get_logger
from dynamicgraph.models.feature_selection import FeatureSelector
from dynamicgraph.training.splits import Fold

logger = get_logger(__name__)

#: Per-stock features that carry no network information (feature set A).
NODE_FEATURE_NAMES: tuple[str, ...] = (
    "return_5d", "return_20d", "return_60d", "momentum_20d", "short_term_reversal",
    "volatility_5d", "volatility_20d", "volatility_60d", "volatility_ratio_5_20",
    "downside_volatility_20d", "semivariance_20d", "skewness_60d", "excess_kurtosis_60d",
    "current_drawdown", "max_drawdown_60d", "days_since_peak", "recovery_ratio_60d",
    "rolling_beta_60d", "downside_beta_60d", "idiosyncratic_volatility",
    "market_relative_strength_20d", "amihud_illiquidity", "log_turnover",
    "turnover_zscore_20d", "volume_zscore_20d", "zero_return_ratio_20d",
    "cs_z_return_20d", "cs_z_volatility_20d", "cs_z_current_drawdown",
)

#: The stock's own position in the network (feature set B adds these).
CENTRALITY_FEATURE_NAMES: tuple[str, ...] = (
    "degree", "strength", "positive_strength", "negative_strength", "edge_sign_ratio",
    "eigenvector_centrality", "pagerank", "betweenness_centrality", "closeness_centrality",
    "clustering", "coreness", "participation_coefficient", "within_community_degree_z",
    "strength_change_20d", "eigenvector_centrality_change_20d", "pagerank_change_20d",
    "strength_zscore_60", "rank_strength",
)

#: Aggregates over the stock's neighbours (feature set C adds these).
NEIGHBOR_FEATURE_NAMES: tuple[str, ...] = (
    "avg_neighbor_strength", "avg_neighbor_degree", "avg_neighbor_risk",
    "avg_neighbor_volatility", "neighbor_downside_exposure", "avg_neighbor_drawdown",
)

NODE_FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "node": NODE_FEATURE_NAMES,
    "node_plus_centrality": NODE_FEATURE_NAMES + CENTRALITY_FEATURE_NAMES,
    "node_plus_neighbor": NODE_FEATURE_NAMES + CENTRALITY_FEATURE_NAMES + NEIGHBOR_FEATURE_NAMES,
}


@dataclass
class NodeRankingResult:
    """OOS cross-sectional predictions and ranking metrics for one feature set."""

    feature_set: str
    model_name: str
    horizon: int
    target: str
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)   # date x ticker
    realized: pd.DataFrame = field(default_factory=pd.DataFrame)      # date x ticker
    metrics: dict[str, Any] = field(default_factory=dict)
    ic_series: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    n_features_candidate: int = 0
    n_features_selected: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.target}__{self.feature_set}__{self.model_name}"


def build_node_panel(state: Any) -> pd.DataFrame:
    """Assemble a `(date, ticker)`-indexed panel of node + network features."""
    node_features = state.node_features
    frames: dict[str, pd.DataFrame] = {}

    for name in NODE_FEATURE_NAMES:
        if name in node_features.frames:
            frames[name] = node_features.frames[name]

    history = state.node_metric_history
    if history is not None and not history.empty:
        for name in CENTRALITY_FEATURE_NAMES + NEIGHBOR_FEATURE_NAMES:
            if name not in history.columns:
                continue
            pivot = history.pivot_table(index="date", columns="ticker", values=name, aggfunc="last")
            frames[name] = pivot

    if not frames:
        return pd.DataFrame()

    index = node_features.index
    columns = node_features.columns
    stacked = []
    for name, frame in frames.items():
        aligned = frame.reindex(index=index, columns=columns)
        # Network metrics come from strided snapshots for some layers; carry the
        # last known value forward only (backward-looking, no look-ahead).
        if name in CENTRALITY_FEATURE_NAMES + NEIGHBOR_FEATURE_NAMES:
            aligned = aligned.ffill(limit=10)
        stacked.append(aligned.stack(future_stack=True).rename(name))

    panel = pd.concat(stacked, axis=1)
    panel.index.names = ["date", "ticker"]
    return panel.replace([np.inf, -np.inf], np.nan)


def build_node_target(
    state: Any, horizon: int, kind: str = "risk_adjusted_return"
) -> pd.Series:
    r"""Forward cross-sectional target, ranked within each date.

    `risk_adjusted_return` uses FutureReturn / (FutureVol + eps) as specified in
    the brief. Ranking within the date removes the market component, so the
    model is scored on *relative* ordering rather than on getting the market
    direction right -- which is the market-level model's job, not this one.
    """
    node_forward = state.targets.node_forward
    if node_forward is None or node_forward.empty:
        return pd.Series(dtype=float)

    column = {
        "risk_adjusted_return": f"future_risk_adjusted_return_{horizon}d",
        "return": f"future_return_{horizon}d",
        "drawdown": f"future_drawdown_{horizon}d",
    }[kind]
    if column not in node_forward.columns:
        return pd.Series(dtype=float)

    values = node_forward[column]
    wide = values.unstack("ticker")
    # Percentile rank within each date: scale-free and robust to the fat tails
    # that would otherwise let one stock dominate a squared-error objective.
    ranked = wide.rank(axis=1, pct=True)
    return ranked.stack(future_stack=True).rename(f"target_{kind}_{horizon}d")


def _fit_predict_fold(
    panel: pd.DataFrame,
    target: pd.Series,
    train_dates: pd.DatetimeIndex,
    test_dates: pd.DatetimeIndex,
    feature_names: list[str],
    config: Any,
    model_name: str,
) -> tuple[pd.Series, int, int]:
    """Fit on the training dates, predict the test dates. Returns (preds, n_cand, n_sel)."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    seed = int(config.project.seed)
    available = [c for c in feature_names if c in panel.columns]
    if not available:
        return pd.Series(dtype=float), 0, 0

    train = panel.loc[panel.index.get_level_values("date").isin(train_dates), available]
    test = panel.loc[panel.index.get_level_values("date").isin(test_dates), available]
    y_train = target.reindex(train.index)

    mask = y_train.notna() & train.notna().any(axis=1)
    train, y_train = train[mask], y_train[mask]
    if len(train) < 300 or test.empty:
        return pd.Series(dtype=float), len(available), 0

    # Fold-local feature selection, fitted on training rows only.
    n_candidate = train.shape[1]
    budget = int(getattr(config.training, "max_features", 0) or 0)
    if budget and n_candidate > budget:
        selector = FeatureSelector(
            max_features=budget,
            redundancy_threshold=float(config.training.feature_redundancy_threshold),
            seed=seed,
        )
        # The selector scores against a binary label; use the top/bottom tercile
        # of the ranked target as a proxy so the same machinery applies.
        binary = (y_train > 0.667).astype(float)
        selector.fit(train, binary)
        if selector.selected_:
            train = selector.transform(train)
            test = selector.transform(test)
    n_selected = train.shape[1]

    if model_name == "hist_gradient_boosting":
        estimator = HistGradientBoostingRegressor(
            max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=40,
            early_stopping=False, random_state=seed,
        )
        model = Pipeline([("model", estimator)])
    else:
        model = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=10.0, random_state=seed)),
            ]
        )

    try:
        model.fit(train, y_train)
        predicted = model.predict(test)
    except Exception as exc:
        logger.debug("Node ranking fold failed (%s): %s", model_name, exc)
        return pd.Series(dtype=float), n_candidate, n_selected

    return pd.Series(predicted, index=test.index), n_candidate, n_selected


def run_node_ranking(
    state: Any,
    folds: list[Fold],
    horizon: int | None = None,
    target_kind: str = "risk_adjusted_return",
    model_name: str = "ridge",
) -> dict[str, NodeRankingResult]:
    """Walk-forward cross-sectional ranking across the three node feature sets."""
    config = state.config
    horizon = horizon or int(config.targets.horizons[len(config.targets.horizons) // 2])

    panel = build_node_panel(state)
    if panel.empty:
        logger.warning("Node ranking skipped: no node panel could be assembled.")
        return {}

    target = build_node_target(state, horizon, target_kind)
    if target.empty:
        logger.warning("Node ranking skipped: target `%s` unavailable.", target_kind)
        return {}

    realized_wide = target.unstack("ticker")
    results: dict[str, NodeRankingResult] = {}

    for set_name, feature_names in NODE_FEATURE_SETS.items():
        predictions: list[pd.Series] = []
        candidates, selected = [], []

        for fold in folds:
            preds, n_cand, n_sel = _fit_predict_fold(
                panel, target, fold.train_dates, fold.test_dates,
                list(feature_names), config, model_name,
            )
            if not preds.empty:
                predictions.append(preds)
                candidates.append(n_cand)
                selected.append(n_sel)

        if not predictions:
            logger.warning("Node ranking produced no predictions for `%s`.", set_name)
            continue

        stacked = pd.concat(predictions)
        prediction_wide = stacked.unstack("ticker").sort_index()
        realized = realized_wide.reindex(prediction_wide.index)

        ic = information_coefficient(prediction_wide, realized, "spearman")
        summary = ic_summary(ic, horizon=horizon)
        portfolios = decile_portfolios(prediction_wide, realized, n_buckets=5)

        metrics: dict[str, Any] = {
            "feature_set": set_name,
            "model": model_name,
            "horizon": horizon,
            "target": target_kind,
            "n_dates": int(len(prediction_wide)),
            "n_folds": len(predictions),
            **{f"ic_{k}": v for k, v in summary.items()},
        }

        if not portfolios.empty:
            spread = portfolios["long_short_spread"].dropna()
            turnover = portfolio_turnover(portfolios)
            mean_turnover = float(turnover.mean()) if not turnover.empty else np.nan
            rebalances = 252.0 / max(horizon, 1)
            cost_bps = 25.0
            annual_cost = (
                mean_turnover * (cost_bps / 1e4) * rebalances * 2.0
                if np.isfinite(mean_turnover) else np.nan
            )
            metrics.update(
                {
                    "top_bucket": float(portfolios["bucket_5"].mean()),
                    "bottom_bucket": float(portfolios["bucket_1"].mean()),
                    "long_short_spread": float(spread.mean()),
                    # Same overlap problem as the IC: consecutive h-day spreads
                    # share h-1 days, so an i.i.d. standard error is far too
                    # small. Newey-West with h-1 lags.
                    "long_short_spread_t": (
                        float(spread.mean() / newey_west_se(spread.to_numpy(), lag=horizon - 1))
                        if len(spread) > 3 else np.nan
                    ),
                    "mean_turnover": mean_turnover,
                    "assumed_cost_bps_round_trip": cost_bps,
                    "cost_adjusted_spread_annualized": (
                        float(spread.mean()) * rebalances - annual_cost
                        if np.isfinite(annual_cost) else np.nan
                    ),
                }
            )

        results[set_name] = NodeRankingResult(
            feature_set=set_name,
            model_name=model_name,
            horizon=horizon,
            target=target_kind,
            predictions=prediction_wide,
            realized=realized,
            metrics=metrics,
            ic_series=ic,
            n_features_candidate=int(np.mean(candidates)) if candidates else 0,
            n_features_selected=float(np.mean(selected)) if selected else 0.0,
        )
        logger.info(
            "Node ranking `%s`: IC mean %.4f, IC IR %.2f, long-short spread %.4f over %d date(s).",
            set_name,
            summary.get("ic_mean", float("nan")),
            summary.get("ic_ir", float("nan")),
            metrics.get("long_short_spread", float("nan")),
            metrics["n_dates"],
        )
    return results


def summarize_node_ranking(results: dict[str, NodeRankingResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    frame = pd.DataFrame([r.metrics for r in results.values()])
    baseline = frame[frame["feature_set"] == "node"]
    if not baseline.empty:
        base_ic = float(baseline["ic_ic_mean"].iloc[0])
        frame["ic_mean_vs_node_only"] = frame["ic_ic_mean"] - base_ic
    return frame.sort_values("ic_ic_mean", ascending=False).reset_index(drop=True)


def node_ranking_verdict(summary: pd.DataFrame) -> dict[str, Any]:
    """Does adding network information improve cross-sectional ordering?"""
    if summary.empty or "ic_ic_mean" not in summary.columns:
        return {"verdict": "inconclusive", "reason": "no node ranking results"}

    by_set = summary.set_index("feature_set")
    if "node" not in by_set.index:
        return {"verdict": "inconclusive", "reason": "node-only baseline missing"}

    base_ic = float(by_set.loc["node", "ic_ic_mean"])
    base_t = float(by_set.loc["node"].get("ic_ic_t_stat", np.nan))
    improvements = {
        name: float(by_set.loc[name, "ic_ic_mean"]) - base_ic
        for name in by_set.index if name != "node"
    }
    best_name = max(improvements, key=improvements.get) if improvements else None
    best_ic = float(by_set.loc[best_name, "ic_ic_mean"]) if best_name else np.nan
    best_t = float(by_set.loc[best_name].get("ic_ic_t_stat", np.nan)) if best_name else np.nan

    # A mean IC is only meaningful if it is distinguishable from zero.
    significant = np.isfinite(best_t) and abs(best_t) > 2.0
    if best_name and improvements[best_name] > 0 and significant:
        verdict = "network_features_improve_ranking"
    elif best_name and improvements[best_name] > 0:
        verdict = "improvement_not_significant"
    else:
        verdict = "no_improvement"

    return {
        "verdict": verdict,
        "baseline_ic_mean": base_ic,
        "baseline_ic_t_stat": base_t,
        "best_feature_set": best_name,
        "best_ic_mean": best_ic,
        "best_ic_t_stat": best_t,
        "ic_improvements": improvements,
        "interpretation": {
            "network_features_improve_ranking": (
                "Adding network position and neighbour aggregates improved the mean rank IC over "
                "per-stock features alone, with an IC t-statistic above 2."
            ),
            "improvement_not_significant": (
                "Network features raised the mean rank IC, but the IC is not distinguishable from "
                "zero at conventional levels. This does not support a claim of cross-sectional "
                "predictive value."
            ),
            "no_improvement": (
                "Network features did not improve cross-sectional ordering over per-stock "
                "features. Centrality describes structural position, not expected return."
            ),
            "inconclusive": "Not enough data to decide.",
        }[verdict],
        "caveat": (
            "Rank IC and long-short spreads are evaluation devices. They demonstrate ordering "
            "ability, not a causal effect and not a tradable strategy."
        ),
    }
