"""Node (per-stock) feature construction.

Produces a `NodeFeatureSet`: a dict of `date x ticker` frames, one per feature,
plus helpers to view them as a tidy long table or as the per-date matrix
`X_t` consumed by the graph and GNN layers.

Every feature is backward-looking. `assert_no_lookahead` in
`tests/test_no_lookahead.py` verifies this empirically by perturbing the future
and checking that no past feature value moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from dynamicgraph.features import returns as R
from dynamicgraph.features.cross_sectional import (
    cross_sectional_percentile,
    cross_sectional_rank,
    cross_sectional_robust_z,
    sector_relative_rank,
)
from dynamicgraph.features.liquidity_features import build_liquidity_features
from dynamicgraph.features.residualization import (
    ResidualizationResult,
    downside_upside_beta,
    residualize_returns,
    rolling_beta,
    sector_return_matrix,
)
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class NodeFeatureSet:
    """Collection of `date x ticker` feature frames."""

    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    returns_raw: pd.DataFrame | None = None
    returns_residual: pd.DataFrame | None = None
    market_returns: pd.Series | None = None
    sector_of: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return sorted(self.frames)

    @property
    def index(self) -> pd.Index:
        return next(iter(self.frames.values())).index

    @property
    def columns(self) -> pd.Index:
        return next(iter(self.frames.values())).columns

    def matrix_at(self, date: pd.Timestamp, tickers: Iterable[str] | None = None,
                  names: Iterable[str] | None = None) -> pd.DataFrame:
        """X_t: rows = tickers, columns = features, for a single date."""
        names = list(names or self.names)
        tickers = list(tickers or self.columns)
        data = {}
        for name in names:
            frame = self.frames[name]
            if date not in frame.index:
                data[name] = pd.Series(np.nan, index=tickers)
            else:
                data[name] = frame.loc[date].reindex(tickers)
        return pd.DataFrame(data, index=tickers)

    def to_long(self, names: Iterable[str] | None = None) -> pd.DataFrame:
        """Tidy (date, ticker, feature...) frame."""
        names = list(names or self.names)
        parts = []
        for name in names:
            stacked = self.frames[name].stack(future_stack=True).rename(name)
            parts.append(stacked)
        out = pd.concat(parts, axis=1)
        out.index.names = ["date", "ticker"]
        return out.reset_index()

    def subset(self, names: Iterable[str]) -> "NodeFeatureSet":
        keep = [n for n in names if n in self.frames]
        return NodeFeatureSet(
            frames={n: self.frames[n] for n in keep},
            returns_raw=self.returns_raw,
            returns_residual=self.returns_residual,
            market_returns=self.market_returns,
            sector_of=dict(self.sector_of),
            assumptions=list(self.assumptions),
        )


def build_node_features(
    panel: pd.DataFrame,
    config: Any,
    index_ticker: str = "VN30",
    sector_of: dict[str, str] | None = None,
) -> NodeFeatureSet:
    """Build the full node feature set from a normalised long panel."""
    cfg = config.features
    sector_of = sector_of or {}

    def wide(column: str) -> pd.DataFrame | None:
        if column not in panel.columns or panel[column].isna().all():
            return None
        return panel.pivot_table(index="date", columns="ticker", values=column, aggfunc="last").sort_index()

    price_all = wide("adjusted_close")
    if price_all is None:
        raise ValueError("`adjusted_close` is required to build node features.")

    stocks = [c for c in price_all.columns if c != index_ticker]
    price = price_all[stocks]
    market_price = price_all[index_ticker] if index_ticker in price_all.columns else None

    close_raw = wide("close")
    volume = wide("volume")
    turnover = wide("turnover")
    market_cap = wide("market_cap")
    if close_raw is not None:
        close_raw = close_raw.reindex(columns=stocks)
    for name in ("volume", "turnover", "market_cap"):
        pass
    volume = volume.reindex(columns=stocks) if volume is not None else None
    turnover = turnover.reindex(columns=stocks) if turnover is not None else None
    market_cap = market_cap.reindex(columns=stocks) if market_cap is not None else None

    frames: dict[str, pd.DataFrame] = {}
    assumptions: list[str] = []

    # ---------------- 7.1 return and momentum -------------------------
    returns_1d = R.compute_log_returns(price, 1)
    market_returns = (
        R.compute_log_returns(market_price.to_frame("m"), 1)["m"] if market_price is not None else None
    )

    for window in cfg.return_windows:
        frames[f"return_{window}d"] = R.compute_log_returns(price, window)
    for window in (20, 60):
        frames[f"momentum_{window}d"] = R.momentum(price, window)
    frames["short_term_reversal"] = R.short_term_reversal(returns_1d, 5)
    frames["cumulative_return_from_recent_peak"] = R.cumulative_return_from_recent_peak(price, 252)

    # ---------------- 7.4 market exposure (needed early) --------------
    residual: ResidualizationResult | None = None
    if market_returns is not None and cfg.residualize_market:
        sector_returns = None
        if cfg.residualize_sector and sector_of:
            sector_returns = sector_return_matrix(returns_1d, sector_of)
        residual = residualize_returns(
            returns_1d,
            market_returns,
            window=int(cfg.residual_window),
            sector_returns=sector_returns,
            sector_of=sector_of if cfg.residualize_sector else None,
        )
        frames["residual_return_1d"] = residual.residuals
        frames["residual_return_5d"] = residual.residuals.rolling(5, min_periods=3).sum()
        frames["idiosyncratic_volatility"] = residual.idiosyncratic_volatility
        frames["market_r_squared"] = residual.r_squared
        assumptions.append(
            f"Residual returns come from a {cfg.residual_window}-day rolling "
            f"{residual.method} regression; residual at t uses coefficients fitted on "
            "[t-W+1, t] only."
        )

        for window in cfg.beta_windows:
            _, beta = rolling_beta(returns_1d, market_returns, window)
            frames[f"rolling_beta_{window}d"] = beta
        down_beta, up_beta = downside_upside_beta(returns_1d, market_returns, 60)
        frames["downside_beta_60d"] = down_beta
        frames["upside_beta_60d"] = up_beta

        market_frame = pd.DataFrame(
            {t: market_returns for t in returns_1d.columns}, index=returns_1d.index
        )
        frames["rolling_correlation_with_index_60d"] = (
            returns_1d.rolling(60, min_periods=30).corr(market_frame)
        )
        frames["market_relative_strength_20d"] = frames["return_20d"].sub(
            market_returns.rolling(20, min_periods=10).sum(), axis=0
        )
    else:
        logger.warning("No market series available; skipping residualization and beta features.")

    # ---------------- 7.2 volatility and downside risk ----------------
    for window in cfg.volatility_windows:
        frames[f"volatility_{window}d"] = R.rolling_volatility(returns_1d, window)
    frames["ewma_volatility"] = R.ewma_volatility(returns_1d, lam=float(cfg.ewma_lambda))
    frames["downside_volatility_20d"] = R.downside_volatility(returns_1d, 20)
    frames["upside_volatility_20d"] = R.upside_volatility(returns_1d, 20)
    frames["semivariance_20d"] = R.semivariance(returns_1d, 20)
    if "volatility_5d" in frames and "volatility_20d" in frames:
        frames["volatility_ratio_5_20"] = frames["volatility_5d"] / (frames["volatility_20d"] + 1e-12)
    if "volatility_20d" in frames and "volatility_60d" in frames:
        frames["volatility_ratio_20_60"] = frames["volatility_20d"] / (frames["volatility_60d"] + 1e-12)
    frames["historical_var_60d"] = R.historical_var(returns_1d, 60, float(cfg.var_quantile))
    frames["expected_shortfall_60d"] = R.historical_expected_shortfall(
        returns_1d, 60, float(cfg.var_quantile)
    )
    frames["skewness_60d"] = R.rolling_skewness(returns_1d, 60)
    frames["excess_kurtosis_60d"] = R.rolling_excess_kurtosis(returns_1d, 60)

    # ---------------- 7.3 drawdown ------------------------------------
    frames["current_drawdown"] = R.drawdown_series(price)
    for window in cfg.drawdown_windows:
        frames[f"max_drawdown_{window}d"] = R.rolling_max_drawdown(price, window)
    since_peak = R.days_since_peak(price)
    frames["days_since_peak"] = since_peak
    frames["drawdown_duration"] = since_peak.where(frames["current_drawdown"] < 0, 0.0)
    frames["drawdown_speed"] = R.drawdown_speed(frames["current_drawdown"], since_peak)
    frames["recovery_ratio_60d"] = R.recovery_ratio(price, 60)

    # ---------------- 7.5 liquidity -----------------------------------
    if cfg.liquidity_features and (volume is not None or turnover is not None):
        source_close = close_raw if close_raw is not None else price
        liquidity, approximated = build_liquidity_features(
            close=source_close,
            returns=returns_1d,
            volume=volume,
            turnover=turnover,
            market_cap=market_cap,
            volatility_20d=frames.get("volatility_20d"),
            window=20,
        )
        frames.update(liquidity)
        frames["zero_return_ratio_20d"] = R.zero_return_ratio(returns_1d, 20)
        if approximated:
            assumptions.append(
                "Value traded approximated as close * volume (source has no turnover column); "
                "Amihud illiquidity is therefore an approximation."
            )
    # ---------------- 7.7 sector --------------------------------------
    if sector_of:
        sector_returns = sector_return_matrix(returns_1d, sector_of)
        mapped = pd.DataFrame(
            {t: sector_returns.get(sector_of.get(t, ""), pd.Series(np.nan, index=returns_1d.index))
             for t in returns_1d.columns},
            index=returns_1d.index,
        )
        frames["sector_return_1d"] = mapped
        frames["sector_volatility_20d"] = R.rolling_volatility(mapped, 20)
        frames["return_relative_to_sector_20d"] = frames["return_20d"] - mapped.rolling(
            20, min_periods=10
        ).sum()

    # ---------------- 7.6 cross-sectional views -----------------------
    base_for_cs = [
        "return_20d", "return_60d", "momentum_20d", "volatility_20d", "volatility_60d",
        "current_drawdown", "downside_volatility_20d", "idiosyncratic_volatility",
        "amihud_illiquidity", "log_turnover",
    ]
    for name in base_for_cs:
        if name not in frames:
            continue
        frame = frames[name]
        if cfg.robust_cross_sectional_scaling:
            frames[f"cs_z_{name}"] = cross_sectional_robust_z(frame, clip=float(cfg.winsorize_z))
        frames[f"cs_pct_{name}"] = cross_sectional_percentile(frame)
        frames[f"cs_rank_{name}"] = cross_sectional_rank(frame)
        if sector_of:
            frames[f"cs_sector_rank_{name}"] = sector_relative_rank(frame, sector_of)

    frames = {k: v.reindex(columns=stocks) for k, v in frames.items()}
    frames = {k: v.replace([np.inf, -np.inf], np.nan) for k, v in frames.items()}

    logger.info("Built %d node features for %d tickers.", len(frames), len(stocks))
    return NodeFeatureSet(
        frames=frames,
        returns_raw=returns_1d,
        returns_residual=residual.residuals if residual is not None else None,
        market_returns=market_returns,
        sector_of=dict(sector_of),
        assumptions=assumptions,
    )
