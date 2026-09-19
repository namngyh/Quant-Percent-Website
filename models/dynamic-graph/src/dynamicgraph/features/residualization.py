r"""Market (and optional sector) residualization.

Raw correlation between VN30 stocks is dominated by the market mode, so the
core graph is built on residual returns:

    r_{i,t} = alpha_{i,t} + beta_{i,t} r_{m,t} + eps_{i,t}

with `alpha`, `beta` estimated on a trailing window ending at t. The residual
reported at t is the *in-window* residual at t, i.e. it uses the coefficients
fitted on [t-W+1, t] -- no future information.

The rolling OLS is computed in closed form from rolling moments, so it is
vectorised over tickers rather than looped.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ResidualizationResult:
    residuals: pd.DataFrame
    alpha: pd.DataFrame
    beta: pd.DataFrame
    r_squared: pd.DataFrame
    idiosyncratic_volatility: pd.DataFrame
    window: int
    method: str


def rolling_beta(
    stock_returns: pd.DataFrame,
    market_returns: pd.Series,
    window: int,
    min_periods: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    r"""Rolling OLS beta and alpha against a single factor.

        beta = Cov(r_i, r_m) / Var(r_m)
        alpha = E[r_i] - beta * E[r_m]

    Both use only the trailing `window` observations ending at t.
    """
    min_periods = min_periods or max(10, window // 2)
    market = market_returns.reindex(stock_returns.index)

    mean_market = market.rolling(window, min_periods=min_periods).mean()
    var_market = market.rolling(window, min_periods=min_periods).var(ddof=1)
    mean_stock = stock_returns.rolling(window, min_periods=min_periods).mean()

    product = stock_returns.mul(market, axis=0)
    mean_product = product.rolling(window, min_periods=min_periods).mean()
    n = stock_returns.rolling(window, min_periods=min_periods).count()
    bessel = n / (n - 1.0).replace(0.0, np.nan)
    covariance = (mean_product.sub(mean_stock.mul(mean_market, axis=0))).mul(bessel)

    beta = covariance.div(var_market.replace(0.0, np.nan), axis=0)
    alpha = mean_stock.sub(beta.mul(mean_market, axis=0))
    return alpha, beta


def residualize_returns(
    stock_returns: pd.DataFrame,
    market_returns: pd.Series,
    window: int = 60,
    sector_returns: pd.DataFrame | None = None,
    sector_of: dict[str, str] | None = None,
    min_periods: int | None = None,
) -> ResidualizationResult:
    r"""Strip the market (and optionally the sector) mode out of stock returns.

    Single factor:
        eps_{i,t} = r_{i,t} - alpha_{i,t} - beta_{i,t} r_{m,t}

    Two factors (when `sector_returns` and `sector_of` are supplied):
        r_{i,t} = alpha_i + beta_m,i r_{m,t} + beta_s,i r_{s(i),t} + eps_{i,t}
    with the sector factor first orthogonalised against the market factor so the
    two loadings stay identified.
    """
    min_periods = min_periods or max(10, window // 2)
    market = market_returns.reindex(stock_returns.index)

    alpha, beta = rolling_beta(stock_returns, market, window, min_periods)
    fitted = alpha.add(beta.mul(market, axis=0))
    residuals = stock_returns - fitted
    method = "market"

    beta_sector = pd.DataFrame(np.nan, index=stock_returns.index, columns=stock_returns.columns)
    if sector_returns is not None and sector_of:
        method = "market+sector"
        # Orthogonalise each sector/leave-one-out ticker factor against the
        # market factor. A ticker-labelled column takes precedence so a stock
        # is never included in its own sector benchmark.
        ortho: dict[str, pd.Series] = {}
        for factor_name in sector_returns.columns:
            series = sector_returns[factor_name].reindex(stock_returns.index)
            a_s, b_s = rolling_beta(
                series.to_frame(factor_name), market, window, min_periods
            )
            ortho[factor_name] = (
                series - (a_s[factor_name] + b_s[factor_name] * market)
            )

        for ticker in stock_returns.columns:
            sector = (sector_of or {}).get(ticker)
            factor_name = ticker if ticker in ortho else sector
            if factor_name is None or factor_name not in ortho:
                continue
            factor = ortho[factor_name]
            resid_i = residuals[ticker]
            a_i, b_i = rolling_beta(resid_i.to_frame(ticker), factor, window, min_periods)
            beta_sector[ticker] = b_i[ticker]
            residuals[ticker] = resid_i - (a_i[ticker] + b_i[ticker] * factor)

    total_var = stock_returns.rolling(window, min_periods=min_periods).var(ddof=1)
    residual_var = residuals.rolling(window, min_periods=min_periods).var(ddof=1)
    r_squared = (1.0 - residual_var / (total_var + EPS)).clip(-1.0, 1.0)
    ivol = residuals.rolling(window, min_periods=min_periods).std(ddof=1) * np.sqrt(252.0)

    logger.info(
        "Residualized %d tickers on a %d-day rolling %s regression.",
        stock_returns.shape[1],
        window,
        method,
    )
    return ResidualizationResult(
        residuals=residuals,
        alpha=alpha,
        beta=beta,
        r_squared=r_squared,
        idiosyncratic_volatility=ivol,
        window=window,
        method=method,
    )


def downside_upside_beta(
    stock_returns: pd.DataFrame,
    market_returns: pd.Series,
    window: int = 60,
    min_periods: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    r"""Betas conditional on the sign of the market return.

    Implemented via rolling conditional moments so it stays vectorised:
        beta^- = Cov(r_i, r_m | r_m < 0) / Var(r_m | r_m < 0)
    """
    # Each conditional branch sees only ~half the window, so the unconditional
    # min_periods would leave the estimate permanently NaN.
    min_periods = min_periods or max(10, window // 5)
    market = market_returns.reindex(stock_returns.index)
    out: list[pd.DataFrame] = []

    for mask in (market < 0, market >= 0):
        market_masked = market.where(mask)
        stock_masked = stock_returns.where(mask, axis=0)

        count = market_masked.rolling(window, min_periods=min_periods).count()
        mean_market = market_masked.rolling(window, min_periods=min_periods).mean()
        mean_stock = stock_masked.rolling(window, min_periods=min_periods).mean()
        mean_product = (
            stock_masked.mul(market_masked, axis=0)
            .rolling(window, min_periods=min_periods)
            .mean()
        )
        mean_market_sq = (
            market_masked.pow(2).rolling(window, min_periods=min_periods).mean()
        )

        covariance = mean_product.sub(mean_stock.mul(mean_market, axis=0))
        variance = mean_market_sq - mean_market.pow(2)
        beta = covariance.div(variance.replace(0.0, np.nan), axis=0)
        beta = beta.where(count.ge(max(5, min_periods // 3)), np.nan)
        out.append(beta)

    return out[0], out[1]


def sector_return_matrix(
    stock_returns: pd.DataFrame,
    sector_of: dict[str, str],
    weights: pd.DataFrame | None = None,
    leave_one_out: bool = False,
) -> pd.DataFrame:
    """Return equal- or weight-averaged sector factors.

    The default result is ``date x sector`` for backward compatibility. With
    ``leave_one_out=True`` the result is ``date x ticker`` and each ticker's
    factor contains only its sector peers. Singleton sectors are undefined.
    """
    if leave_one_out:
        out = pd.DataFrame(
            np.nan, index=stock_returns.index, columns=stock_returns.columns
        )
        for ticker in stock_returns.columns:
            sector = sector_of.get(ticker)
            peers = [
                member
                for member in stock_returns.columns
                if member != ticker and sector_of.get(member) == sector
            ]
            if not sector or not peers:
                continue
            block = stock_returns[peers]
            if weights is None:
                out[ticker] = block.mean(axis=1, skipna=True)
            else:
                weight_block = weights.reindex(
                    index=block.index, columns=peers
                ).where(block.notna())
                denominator = weight_block.sum(axis=1, min_count=1)
                normalised = weight_block.div(
                    denominator.replace(0.0, np.nan), axis=0
                )
                out[ticker] = (block * normalised).sum(axis=1, min_count=1)
        return out

    sectors = sorted({s for s in sector_of.values() if s})
    out = pd.DataFrame(index=stock_returns.index, columns=sectors, dtype=float)
    for sector in sectors:
        members = [t for t in stock_returns.columns if sector_of.get(t) == sector]
        if not members:
            continue
        block = stock_returns[members]
        if weights is None:
            out[sector] = block.mean(axis=1, skipna=True)
        else:
            weight_block = weights[members].reindex(block.index)
            normalised = weight_block.div(weight_block.sum(axis=1) + EPS, axis=0)
            out[sector] = (block * normalised).sum(axis=1, min_count=1)
    return out
