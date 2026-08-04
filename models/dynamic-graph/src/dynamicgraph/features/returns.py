r"""Return, volatility and drawdown primitives.

All functions are backward-looking by construction:
    r_{i,t} = log(P_{i,t} / P_{i,t-1})
uses `shift(1)`, and every rolling statistic ends at t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS, TRADING_DAYS_PER_YEAR


def compute_log_returns(prices: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    r"""Log returns over `periods` days: log(P_t / P_{t-periods})."""
    prices = prices.sort_index()
    positive = prices.where(prices > 0)
    return np.log(positive / positive.shift(periods))


def compute_simple_returns(prices: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    prices = prices.sort_index()
    positive = prices.where(prices > 0)
    return positive / positive.shift(periods) - 1.0


def momentum(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    r"""MOM^{(k)}_{i,t} = log(P_{i,t} / P_{i,t-k})."""
    return compute_log_returns(prices, periods=window)


def rolling_volatility(
    returns: pd.DataFrame, window: int, annualize: bool = True, min_periods: int | None = None
) -> pd.DataFrame:
    r"""sigma^{(k)}_{i,t} = sqrt(252/(k-1) * sum (r - rbar)^2) over the trailing k days."""
    min_periods = min_periods or max(3, window // 2)
    sigma = returns.rolling(window, min_periods=min_periods).std(ddof=1)
    if annualize:
        sigma = sigma * np.sqrt(TRADING_DAYS_PER_YEAR)
    return sigma


def ewma_volatility(returns: pd.DataFrame, lam: float = 0.94, annualize: bool = True) -> pd.DataFrame:
    r"""RiskMetrics EWMA volatility, sigma^2_t = lam*sigma^2_{t-1} + (1-lam)*r_t^2."""
    variance = returns.pow(2).ewm(alpha=1.0 - lam, adjust=False, min_periods=5).mean()
    sigma = np.sqrt(variance)
    return sigma * np.sqrt(TRADING_DAYS_PER_YEAR) if annualize else sigma


def downside_volatility(returns: pd.DataFrame, window: int, annualize: bool = True) -> pd.DataFrame:
    r"""sqrt(mean(min(r,0)^2)) over the trailing window (semi-deviation)."""
    downside = returns.clip(upper=0.0)
    variance = downside.pow(2).rolling(window, min_periods=max(3, window // 2)).mean()
    sigma = np.sqrt(variance)
    return sigma * np.sqrt(TRADING_DAYS_PER_YEAR) if annualize else sigma


def upside_volatility(returns: pd.DataFrame, window: int, annualize: bool = True) -> pd.DataFrame:
    upside = returns.clip(lower=0.0)
    variance = upside.pow(2).rolling(window, min_periods=max(3, window // 2)).mean()
    sigma = np.sqrt(variance)
    return sigma * np.sqrt(TRADING_DAYS_PER_YEAR) if annualize else sigma


def semivariance(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    r"""DSV^{(k)}_{i,t} = (1/k) * sum min(r_{i,u}, 0)^2."""
    return returns.clip(upper=0.0).pow(2).rolling(window, min_periods=max(3, window // 2)).mean()


def historical_var(returns: pd.DataFrame, window: int, quantile: float = 0.05) -> pd.DataFrame:
    """Historical VaR as a positive loss magnitude."""
    return -returns.rolling(window, min_periods=max(5, window // 2)).quantile(quantile)


def historical_expected_shortfall(
    returns: pd.DataFrame, window: int, quantile: float = 0.05
) -> pd.DataFrame:
    """Mean loss beyond the historical VaR, as a positive magnitude."""

    def _es(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if clean.size < 5:
            return np.nan
        threshold = np.quantile(clean, quantile)
        tail = clean[clean <= threshold]
        return -float(tail.mean()) if tail.size else np.nan

    return returns.rolling(window, min_periods=max(5, window // 2)).apply(_es, raw=True)


def rolling_skewness(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    return returns.rolling(window, min_periods=max(10, window // 2)).skew()


def rolling_excess_kurtosis(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    """pandas `.kurt()` already returns the excess (Fisher) kurtosis."""
    return returns.rolling(window, min_periods=max(10, window // 2)).kurt()


def running_peak(prices: pd.DataFrame) -> pd.DataFrame:
    r"""max_{s <= t} P_{i,s}. Expanding, so never forward-looking."""
    return prices.cummax()


def drawdown_series(prices: pd.DataFrame) -> pd.DataFrame:
    r"""DD_{i,t} = P_{i,t} / max_{s<=t} P_{i,s} - 1  (<= 0)."""
    peak = running_peak(prices)
    return prices / peak - 1.0


def rolling_max_drawdown(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    """Worst peak-to-trough drawdown inside the trailing window."""

    def _mdd(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if clean.size < 2:
            return np.nan
        peak = np.maximum.accumulate(clean)
        return float(np.min(clean / peak - 1.0))

    return prices.rolling(window, min_periods=max(5, window // 2)).apply(_mdd, raw=True)


def days_since_peak(prices: pd.DataFrame) -> pd.DataFrame:
    """Trading days since the running (expanding) maximum was last set."""
    out = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for column in prices.columns:
        series = prices[column]
        peak = series.cummax()
        at_peak = series >= peak - EPS
        counter = np.zeros(len(series), dtype=float)
        count = 0.0
        values = at_peak.to_numpy()
        valid = series.notna().to_numpy()
        for i in range(len(series)):
            if not valid[i]:
                counter[i] = np.nan
                continue
            count = 0.0 if values[i] else count + 1.0
            counter[i] = count
        out[column] = counter
    return out


def drawdown_speed(drawdown: pd.DataFrame, since_peak: pd.DataFrame) -> pd.DataFrame:
    """Average drawdown accrued per day since the peak (a negative rate)."""
    return drawdown / (since_peak + 1.0)


def recovery_ratio(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    """How far price has recovered from the window's trough toward its peak.

    0 at the trough, 1 back at the window's high. Uses only the trailing window.
    """
    high = prices.rolling(window, min_periods=max(5, window // 2)).max()
    low = prices.rolling(window, min_periods=max(5, window // 2)).min()
    return (prices - low) / (high - low + EPS)


def short_term_reversal(returns: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Negative of the trailing cumulative return - the classic reversal signal."""
    return -returns.rolling(window, min_periods=max(2, window // 2)).sum()


def cumulative_return_from_recent_peak(prices: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """log(P_t / max(P) over the trailing window) - a windowed drawdown in logs."""
    peak = prices.rolling(window, min_periods=max(5, window // 2)).max()
    return np.log(prices / peak)


def zero_return_ratio(returns: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Share of zero-return days in the trailing window (illiquidity proxy)."""
    is_zero = returns.abs().le(EPS).astype(float).where(returns.notna())
    return is_zero.rolling(window, min_periods=max(3, window // 2)).mean()


def robust_zscore(frame: pd.DataFrame, axis: int = 1, clip: float | None = 5.0) -> pd.DataFrame:
    r"""z = (x - median) / (1.4826 * MAD + eps), computed along `axis`.

    axis=1 gives a cross-sectional (per-date) score.
    """
    median = frame.median(axis=axis)
    if axis == 1:
        deviation = frame.sub(median, axis=0).abs()
        mad = deviation.median(axis=1)
        z = frame.sub(median, axis=0).div(1.4826 * mad + EPS, axis=0)
    else:
        deviation = frame.sub(median, axis=1).abs()
        mad = deviation.median(axis=0)
        z = frame.sub(median, axis=1).div(1.4826 * mad + EPS, axis=1)
    return z.clip(-clip, clip) if clip is not None else z
