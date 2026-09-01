"""Cross-sectional ranking metrics for node-level predictions.

Rank IC and long-short spread answer "can the model order stocks?", which RMSE
cannot. Turnover and transaction-cost-adjusted spread are reported alongside,
because a spread that only exists before costs is not a result.

A portfolio backtest here is an evaluation device, not evidence of causality.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def information_coefficient(
    predictions: pd.DataFrame, realized: pd.DataFrame, method: str = "spearman"
) -> pd.Series:
    """Per-date cross-sectional rank correlation between prediction and outcome."""
    shared_dates = predictions.index.intersection(realized.index)
    shared_columns = predictions.columns.intersection(realized.columns)
    out = {}
    for date in shared_dates:
        p = predictions.loc[date, shared_columns]
        r = realized.loc[date, shared_columns]
        mask = p.notna() & r.notna()
        if mask.sum() < 5:
            continue
        if p[mask].nunique() < 2 or r[mask].nunique() < 2:
            out[date] = np.nan
            continue
        out[date] = float(p[mask].corr(r[mask], method=method))
    return pd.Series(out, name=f"ic_{method}").sort_index()


def newey_west_se(values: np.ndarray, lag: int) -> float:
    r"""Newey-West HAC standard error of the mean.

        Var = [gamma_0 + 2 sum_{l=1..L} (1 - l/(L+1)) gamma_l] / T

    Required here because h-day forward returns computed daily overlap by h-1
    days: consecutive IC observations are mechanically correlated (~0.86 at
    lag 1 for h=20), so the i.i.d. standard error understates uncertainty by a
    factor of 3-4 and inflates the t-statistic correspondingly.
    """
    x = np.asarray(values, dtype=float)
    x = x[~np.isnan(x)]
    n = x.size
    if n < 3:
        return float("nan")
    centered = x - x.mean()
    lag = int(max(0, min(lag, n - 2)))
    variance = float(centered @ centered) / n
    for lag_index in range(1, lag + 1):
        weight = 1.0 - lag_index / (lag + 1.0)
        variance += (
            2.0
            * weight
            * float(centered[lag_index:] @ centered[:-lag_index])
            / n
        )
    if variance <= 0:
        return float("nan")
    return float(np.sqrt(variance / n))


def ic_summary(ic: pd.Series, horizon: int = 1) -> dict[str, Any]:
    """IC mean, dispersion, information ratio and an overlap-aware t-statistic.

    `horizon` is the forecast horizon in trading days. When it exceeds 1 the IC
    series overlaps, and the reported `ic_t_stat` uses a Newey-West HAC standard
    error with `horizon - 1` lags. The naive i.i.d. t-statistic is kept as
    `ic_t_stat_iid` so the difference is visible rather than hidden.
    """
    values = ic.dropna()
    if values.empty:
        return {"ic_mean": np.nan, "ic_std": np.nan, "ic_ir": np.nan, "n": 0}

    mean = float(values.mean())
    std = float(values.std(ddof=1))
    n = int(len(values))
    horizon = max(1, int(horizon))

    iid_se = std / np.sqrt(n) if std > 0 else np.nan
    hac_se = newey_west_se(values.to_numpy(), lag=horizon - 1) if horizon > 1 else iid_se
    # Independent-observation count implied by non-overlapping windows.
    effective_n = n / horizon

    return {
        "ic_mean": mean,
        "ic_std": std,
        # Annualised IR on the *effective* number of rebalances, not on 252
        # daily observations that are 95% redundant at h=20.
        "ic_ir": float(mean / std * np.sqrt(252.0 / horizon)) if std > 0 else np.nan,
        "ic_positive_rate": float((values > 0).mean()),
        "ic_t_stat": float(mean / hac_se) if hac_se and np.isfinite(hac_se) else np.nan,
        "ic_t_stat_iid": float(mean / iid_se) if iid_se and np.isfinite(iid_se) else np.nan,
        "ic_autocorr_lag1": float(values.autocorr(1)) if n > 2 else np.nan,
        "n": n,
        "n_effective": float(effective_n),
        "horizon": horizon,
    }


def decile_portfolios(
    predictions: pd.DataFrame,
    realized_returns: pd.DataFrame,
    n_buckets: int = 5,
) -> pd.DataFrame:
    """Equal-weight bucket returns plus the long-short spread, per date."""
    shared_dates = predictions.index.intersection(realized_returns.index)
    shared_columns = predictions.columns.intersection(realized_returns.columns)
    rows = []
    for date in shared_dates:
        p = predictions.loc[date, shared_columns].dropna()
        r = realized_returns.loc[date, p.index].dropna()
        p = p.reindex(r.index).dropna()
        if len(p) < n_buckets * 2:
            continue
        buckets = pd.qcut(p.rank(method="first"), n_buckets, labels=False, duplicates="drop")
        row: dict[str, Any] = {"date": date, "n_assets": len(p)}
        for bucket in range(n_buckets):
            members = p.index[buckets == bucket]
            row[f"bucket_{bucket + 1}"] = float(r.loc[members].mean()) if len(members) else np.nan
        row["long_short_spread"] = row.get(f"bucket_{n_buckets}", np.nan) - row.get("bucket_1", np.nan)
        row["top_bucket_members"] = list(p.index[buckets == n_buckets - 1])
        row["bottom_bucket_members"] = list(p.index[buckets == 0])
        rows.append(row)
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def portfolio_turnover(portfolios: pd.DataFrame, column: str = "top_bucket_members") -> pd.Series:
    """Weight-based one-way turnover between consecutive portfolios.

    When both top and bottom member lists are available, the evaluated book is
    one unit long the top bucket and one unit short the bottom bucket. Turnover
    is half the L1 weight change, so a complete reversal of both legs is 2.0.
    For a top-only frame the same definition is applied to a unit long book.
    """
    if portfolios.empty or column not in portfolios.columns:
        return pd.Series(dtype=float)
    out = {}
    previous: pd.Series | None = None
    has_short_leg = "bottom_bucket_members" in portfolios.columns
    for date, row in portfolios.iterrows():
        top = list(row[column])
        bottom = list(row["bottom_bucket_members"]) if has_short_leg else []
        current = pd.Series(dtype=float)
        if top:
            current = pd.concat(
                [current, pd.Series(1.0 / len(top), index=top, dtype=float)]
            )
        if bottom:
            short = pd.Series(-1.0 / len(bottom), index=bottom, dtype=float)
            current = current.add(short, fill_value=0.0)
        if previous is not None:
            assets = previous.index.union(current.index)
            out[date] = 0.5 * float(
                (
                    current.reindex(assets, fill_value=0.0)
                    - previous.reindex(assets, fill_value=0.0)
                ).abs().sum()
            )
        previous = current
    return pd.Series(out, name="turnover").sort_index()


def ranking_metrics(
    predictions: pd.DataFrame,
    realized: pd.DataFrame,
    n_buckets: int = 5,
    cost_bps: float = 25.0,
    horizon: int = 20,
) -> dict[str, Any]:
    """Full ranking evaluation.

    `cost_bps` is a round-trip cost applied to the realised turnover -- VN
    equities typically cost 15-30 bps per side including impact, so 25 bps
    round trip is a mild assumption.
    """
    spearman_ic = information_coefficient(predictions, realized, "spearman")
    pearson_ic = information_coefficient(predictions, realized, "pearson")
    horizon = max(1, int(horizon))
    # Forward h-day returns overlap when formed daily. Portfolio evaluation uses
    # non-overlapping rebalance dates; IC keeps all dates and uses HAC inference.
    portfolio_predictions = predictions.iloc[::horizon]
    portfolio_realized = realized.reindex(portfolio_predictions.index)
    portfolios = decile_portfolios(
        portfolio_predictions, portfolio_realized, n_buckets=n_buckets
    )

    out: dict[str, Any] = {
        f"spearman_{k}": v for k, v in ic_summary(spearman_ic, horizon=horizon).items()
    }
    out.update(
        {
            f"pearson_{k}": v
            for k, v in ic_summary(pearson_ic, horizon=horizon).items()
        }
    )

    if not portfolios.empty:
        spread = portfolios["long_short_spread"].dropna()
        turnover = portfolio_turnover(portfolios)
        mean_turnover = float(turnover.mean()) if not turnover.empty else np.nan
        # Rebalances per year given the holding horizon.
        rebalances = 252.0 / horizon
        annual_cost = (
            mean_turnover * (cost_bps / 1e4) * rebalances * 2.0
            if np.isfinite(mean_turnover) else np.nan
        )
        mean_spread = float(spread.mean())
        out.update(
            {
                "top_bucket_return": float(portfolios[f"bucket_{n_buckets}"].mean()),
                "bottom_bucket_return": float(portfolios["bucket_1"].mean()),
                "long_short_spread": mean_spread,
                "long_short_spread_t": (
                    float(mean_spread / newey_west_se(spread.to_numpy(), lag=0))
                    if spread.std(ddof=1) > 0
                    else np.nan
                ),
                "mean_turnover": mean_turnover,
                "assumed_cost_bps_round_trip": cost_bps,
                "estimated_annual_cost": annual_cost,
                "cost_adjusted_spread_annualized": (
                    mean_spread * rebalances - annual_cost
                    if np.isfinite(annual_cost) else np.nan
                ),
                "n_rebalances": int(len(portfolios)),
            }
        )
    out["ic_series"] = spearman_ic
    out["caveat"] = (
        "Portfolio spreads are an evaluation device. They demonstrate cross-sectional ordering, "
        "not a causal effect and not a tradable strategy."
    )
    return out
