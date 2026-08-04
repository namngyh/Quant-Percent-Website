r"""Forward-looking targets.

This is the only module allowed to look into the future. Everything here is
computed with `shift(-h)`-style logic and is never merged into a feature matrix
by the training code; `tests/test_no_lookahead.py` asserts the separation.

Quantile thresholds are NEVER fitted here on the whole sample. `build_targets`
produces the raw forward quantities plus absolute-threshold labels; quantile
labels are produced per walk-forward fold by `label_by_train_quantile`, which
takes an explicit training mask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.constants import TRADING_DAYS_PER_YEAR
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TargetSet:
    """Forward quantities and labels, indexed by date (or date x ticker)."""

    forward: pd.DataFrame = field(default_factory=pd.DataFrame)
    labels: pd.DataFrame = field(default_factory=pd.DataFrame)
    horizons: list[int] = field(default_factory=list)
    definition: str = "absolute"
    node_forward: pd.DataFrame | None = None
    node_labels: pd.DataFrame | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def valid_index(self) -> pd.Index:
        """Dates where at least one label is defined (i.e. the horizon fits)."""
        return self.labels.dropna(how="all").index


def future_drawdown(prices: pd.Series | pd.DataFrame, horizon: int) -> pd.Series | pd.DataFrame:
    r"""FutureDD_{t,h} = min_{1<=u<=h} (P_{t+u}/P_t) - 1.

    The minimum is taken over the *future* window, excluding t itself.
    """
    if isinstance(prices, pd.Series):
        forward_min = prices.shift(-1).rolling(horizon, min_periods=horizon).min().shift(-(horizon - 1))
        return forward_min / prices - 1.0
    forward_min = prices.shift(-1).rolling(horizon, min_periods=horizon).min().shift(-(horizon - 1))
    return forward_min / prices - 1.0


def future_return(prices: pd.Series | pd.DataFrame, horizon: int) -> pd.Series | pd.DataFrame:
    r"""log(P_{t+h} / P_t)."""
    return np.log(prices.shift(-horizon) / prices)


def future_realized_volatility(returns: pd.Series, horizon: int) -> pd.Series:
    r"""FVOL_{t,h} = sqrt(252/h * sum_{u=1}^{h} r_{t+u}^2)."""
    squared = returns.pow(2)
    forward_sum = squared.shift(-1).rolling(horizon, min_periods=horizon).sum().shift(-(horizon - 1))
    return np.sqrt(TRADING_DAYS_PER_YEAR / horizon * forward_sum)


def future_max_gain(prices: pd.Series, horizon: int) -> pd.Series:
    forward_max = prices.shift(-1).rolling(horizon, min_periods=horizon).max().shift(-(horizon - 1))
    return forward_max / prices - 1.0


def build_targets(
    panel: pd.DataFrame,
    config: Any,
    index_ticker: str = "VN30",
    build_node_targets: bool = True,
) -> TargetSet:
    """Build all forward quantities and absolute-threshold labels."""
    cfg = config.targets
    horizons = [int(h) for h in cfg.horizons]

    index_rows = panel[panel["ticker"] == index_ticker].sort_values("date")
    if index_rows.empty:
        raise ValueError(f"Index `{index_ticker}` not present; cannot build market targets.")
    price = index_rows.set_index("date")["adjusted_close"].astype(float)
    returns = np.log(price / price.shift(1))

    forward = pd.DataFrame(index=price.index)
    labels = pd.DataFrame(index=price.index)

    thresholds = {int(k): float(v) for k, v in (cfg.absolute_drawdown_thresholds or {}).items()}
    for horizon in horizons:
        drawdown = future_drawdown(price, horizon)
        volatility = future_realized_volatility(returns, horizon)
        forward[f"future_drawdown_{horizon}d"] = drawdown
        forward[f"future_return_{horizon}d"] = future_return(price, horizon)
        forward[f"future_volatility_{horizon}d"] = volatility
        forward[f"future_max_gain_{horizon}d"] = future_max_gain(price, horizon)

        threshold = thresholds.get(horizon)
        if threshold is not None:
            labels[f"stress_abs_{horizon}d"] = (
                (drawdown <= threshold).astype(float).where(drawdown.notna())
            )

    node_forward = None
    node_labels = None
    if build_node_targets:
        stock_panel = panel[panel["ticker"] != index_ticker]
        stock_price = stock_panel.pivot_table(
            index="date", columns="ticker", values="adjusted_close", aggfunc="last"
        ).sort_index()
        node_thresholds = {
            int(k): float(v) for k, v in (cfg.node_absolute_drawdown_thresholds or {}).items()
        }
        forward_parts: list[pd.DataFrame] = []
        label_parts: list[pd.DataFrame] = []
        for horizon in horizons:
            drawdown = future_drawdown(stock_price, horizon)
            ret = future_return(stock_price, horizon)
            realized = np.sqrt(
                (np.log(stock_price / stock_price.shift(1)).pow(2))
                .shift(-1)
                .rolling(horizon, min_periods=horizon)
                .sum()
                .shift(-(horizon - 1))
                * TRADING_DAYS_PER_YEAR
                / horizon
            )
            forward_parts.append(
                drawdown.stack(future_stack=True).rename(f"future_drawdown_{horizon}d")
            )
            forward_parts.append(ret.stack(future_stack=True).rename(f"future_return_{horizon}d"))
            forward_parts.append(
                realized.stack(future_stack=True).rename(f"future_volatility_{horizon}d")
            )
            forward_parts.append(
                (ret / (realized + 1e-8))
                .stack(future_stack=True)
                .rename(f"future_risk_adjusted_return_{horizon}d")
            )
            threshold = node_thresholds.get(horizon)
            if threshold is not None:
                label = (drawdown <= threshold).astype(float).where(drawdown.notna())
                label_parts.append(label.stack(future_stack=True).rename(f"node_stress_abs_{horizon}d"))

        node_forward = pd.concat(forward_parts, axis=1)
        node_forward.index.names = ["date", "ticker"]
        if label_parts:
            node_labels = pd.concat(label_parts, axis=1)
            node_labels.index.names = ["date", "ticker"]

    positive_rates = {
        column: float(labels[column].mean()) for column in labels.columns if labels[column].notna().any()
    }
    logger.info(
        "Targets built for horizons %s. Absolute-threshold positive rates: %s",
        horizons,
        {k: round(v, 4) for k, v in positive_rates.items()},
    )

    return TargetSet(
        forward=forward,
        labels=labels,
        horizons=horizons,
        definition=str(cfg.stress_definition),
        node_forward=node_forward,
        node_labels=node_labels,
        metadata={
            "absolute_thresholds": thresholds,
            "node_absolute_thresholds": node_thresholds if build_node_targets else {},
            "positive_rates_absolute": positive_rates,
            "index_ticker": index_ticker,
        },
    )


def label_by_train_quantile(
    forward_values: pd.Series,
    train_mask: pd.Series,
    quantile: float,
    direction: str = "lower",
) -> tuple[pd.Series, float]:
    r"""Y_{t,h} = 1{ x_t <= Q_q(x | train) }  (or >= for `direction='upper'`).

    The threshold is estimated **only** on rows where `train_mask` is True, which
    is what keeps quantile labels free of test-set leakage. Returns
    `(labels, threshold)`.
    """
    train_values = forward_values[train_mask.reindex(forward_values.index, fill_value=False)]
    train_values = train_values.dropna()
    if train_values.empty:
        raise ValueError("Cannot estimate a target quantile: the training slice is empty.")

    if direction == "lower":
        threshold = float(np.quantile(train_values, quantile))
        labels = (forward_values <= threshold).astype(float)
    else:
        threshold = float(np.quantile(train_values, quantile))
        labels = (forward_values >= threshold).astype(float)
    return labels.where(forward_values.notna()), threshold


def label_volatility_regime(
    forward_volatility: pd.Series, train_mask: pd.Series, quantile: float = 0.90
) -> tuple[pd.Series, float]:
    r"""Y^{vol}_{t,h} = 1{ FVOL_{t,h} >= Q_{0.90}(FVOL | train) }."""
    return label_by_train_quantile(forward_volatility, train_mask, quantile, direction="upper")


def stress_events(labels: pd.Series, min_gap_days: int = 20) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Collapse a 0/1 label series into distinct stress episodes.

    Consecutive positive days separated by fewer than `min_gap_days` belong to
    the same event. Used by the event-level detection metrics so that one long
    drawdown is not counted as 40 independent successes.
    """
    positives = labels[labels > 0].index
    if len(positives) == 0:
        return []
    events: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start = previous = positives[0]
    positions = {d: i for i, d in enumerate(labels.index)}
    for date in positives[1:]:
        if positions[date] - positions[previous] > min_gap_days:
            events.append((start, previous))
            start = date
        previous = date
    events.append((start, previous))
    return events
