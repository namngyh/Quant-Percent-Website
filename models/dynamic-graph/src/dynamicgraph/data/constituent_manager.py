"""Universe (constituent) resolution.

Two methods:

`static_list`
    Read `config/vn30_universe.csv`. Rows may carry `effective_from` /
    `effective_to`; when they do, membership is point-in-time. When they do not
    (the shipped default), the same 30 tickers apply to all of history, which is
    survivorship-biased and reported as such.

`liquidity_proxy`
    Rebuild the universe every `universe_rebalance_days` from a *trailing*
    window of market cap x turnover. Uses only information available at the
    rebalance date, so it introduces no look-ahead and no survivorship bias.
    This is the closest reproducible stand-in for real VN30 membership history
    when the database does not carry index membership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class UniverseResolution:
    """Resolved universe plus the provenance needed for the audit report."""

    method: str
    tickers: list[str]
    membership: pd.DataFrame  # columns: date, ticker (point-in-time)
    survivorship_bias: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    daily_coverage: pd.DataFrame = field(default_factory=pd.DataFrame)

    def members_on(self, date: pd.Timestamp) -> list[str]:
        if self.membership.empty:
            return list(self.tickers)
        subset = self.membership[self.membership["date"] == date]
        return sorted(subset["ticker"].tolist())

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "n_tickers": len(self.tickers),
            "tickers": self.tickers,
            "survivorship_bias_warning": self.survivorship_bias,
            "warnings": self.warnings,
            "notes": self.notes,
            "effective_date_convention": "effective_from and effective_to are both inclusive",
            "coverage": {
                "n_dates": int(len(self.daily_coverage)),
                "mean_coverage_ratio": (
                    float(self.daily_coverage["coverage_ratio"].mean())
                    if not self.daily_coverage.empty
                    else None
                ),
            },
        }


def read_static_universe(path: Path) -> pd.DataFrame:
    """Read the universe CSV, tolerating `#` comment lines."""
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")
    frame = pd.read_csv(path, comment="#")
    frame.columns = [c.strip().lower() for c in frame.columns]
    if "ticker" not in frame.columns:
        raise ValueError(f"{path} must contain a `ticker` column.")
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    for column in ("effective_from", "effective_to"):
        if column not in frame.columns:
            frame[column] = pd.NaT
        else:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame[frame["ticker"].str.len().between(1, 12)]


def resolve_static_universe(
    path: Path, calendar: pd.DatetimeIndex, available: set[str]
) -> UniverseResolution:
    table = read_static_universe(path)
    warnings: list[str] = []
    notes: list[str] = []

    missing = sorted(set(table["ticker"]) - available)
    if missing:
        warnings.append(f"{len(missing)} universe ticker(s) absent from the database: {missing}")
    table = table[table["ticker"].isin(available)]

    has_dates = table["effective_from"].notna().any() or table["effective_to"].notna().any()
    rows: list[pd.DataFrame] = []
    for _, row in table.iterrows():
        start = row["effective_from"] if pd.notna(row["effective_from"]) else calendar.min()
        stop = row["effective_to"] if pd.notna(row["effective_to"]) else calendar.max()
        window = calendar[(calendar >= start) & (calendar <= stop)]
        if len(window):
            rows.append(pd.DataFrame({"date": window, "ticker": row["ticker"]}))
    membership = (
        pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "ticker"])
    )

    if has_dates:
        notes.append(
            "Universe file carries point-in-time effective dates; effective_from and "
            "effective_to are both inclusive."
        )
        survivorship = False
    else:
        warnings.append(
            "SURVIVORSHIP BIAS: the universe file has no effective dates, so today's "
            "VN30 membership is applied to the whole history. Stocks that were removed "
            "from the index are absent and current members are present before they "
            "joined. Network statistics and any model trained on them are optimistically "
            "biased. Use `data.universe_method: liquidity_proxy` for a point-in-time "
            "alternative, or add effective dates to config/vn30_universe.csv."
        )
        survivorship = True

    tickers = sorted(table["ticker"].unique().tolist())
    return UniverseResolution(
        method="static_list",
        tickers=tickers,
        membership=membership,
        survivorship_bias=survivorship,
        warnings=warnings,
        notes=notes,
    )


def resolve_liquidity_universe(
    panel: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    size: int = 30,
    lookback: int = 120,
    rebalance_days: int = 63,
    exclude: set[str] | None = None,
) -> UniverseResolution:
    """Point-in-time top-N by trailing liquidity x size.

    Score at rebalance date t (all inputs strictly <= t):
        score = median(turnover over the trailing `lookback` days)
                * sqrt(median(market_cap over the same window))

    Market cap falls back to close price when shares outstanding are absent, in
    which case the score degenerates to a pure liquidity ranking.
    """
    exclude = exclude or set()
    stocks = panel[~panel["ticker"].isin(exclude)]
    if "is_index" in stocks.columns:
        stocks = stocks[~stocks["is_index"].astype(bool)]

    turnover = stocks.pivot_table(index="date", columns="ticker", values="turnover", aggfunc="last")
    if "market_cap" in stocks.columns and stocks["market_cap"].notna().any():
        cap = stocks.pivot_table(index="date", columns="ticker", values="market_cap", aggfunc="last")
        cap_available = True
    else:
        cap = stocks.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
        cap_available = False

    turnover = turnover.reindex(calendar)
    cap = cap.reindex(calendar).reindex(columns=turnover.columns)

    rebalance_points = list(range(lookback, len(calendar), max(1, rebalance_days)))
    rows: list[pd.DataFrame] = []
    for pos in rebalance_points:
        window = slice(pos - lookback, pos)  # strictly before the rebalance date
        med_turnover = turnover.iloc[window].median(skipna=True)
        med_cap = cap.iloc[window].median(skipna=True)
        coverage = turnover.iloc[window].notna().mean()
        score = med_turnover.fillna(0.0) * np.sqrt(med_cap.fillna(0.0).clip(lower=0.0))
        score = score.where(coverage >= 0.8, 0.0)
        chosen = score.sort_values(ascending=False).head(size).index.tolist()

        stop = rebalance_points[rebalance_points.index(pos) + 1] if pos != rebalance_points[-1] else len(calendar)
        window_dates = calendar[pos:stop]
        for ticker in chosen:
            rows.append(pd.DataFrame({"date": window_dates, "ticker": ticker}))

    membership = (
        pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "ticker"])
    )
    tickers = sorted(membership["ticker"].unique().tolist())
    notes = [
        "Universe rebuilt point-in-time from trailing liquidity x size; no look-ahead, "
        "no survivorship selection.",
        f"Rebalanced every {rebalance_days} trading days with a {lookback}-day trailing window.",
    ]
    warnings: list[str] = []
    if not cap_available:
        warnings.append(
            "Shares outstanding unavailable; the liquidity proxy ranks on turnover x sqrt(price) "
            "only, which is a weaker stand-in for index membership."
        )
    warnings.append(
        "The liquidity proxy approximates VN30 membership; it is not the official HOSE "
        "constituent list and will differ around index reviews."
    )
    return UniverseResolution(
        method="liquidity_proxy",
        tickers=tickers,
        membership=membership,
        survivorship_bias=False,
        warnings=warnings,
        notes=notes,
    )


def resolve_universe(
    config: Any,
    panel: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    index_ticker: str,
) -> UniverseResolution:
    """Dispatch on `data.universe_method`."""
    available = set(panel["ticker"].unique())
    method = str(config.data.universe_method or "static_list").lower()

    if method == "liquidity_proxy":
        resolution = resolve_liquidity_universe(
            panel,
            calendar,
            size=int(config.data.universe_size),
            lookback=int(config.data.liquidity_lookback_days),
            rebalance_days=int(config.data.universe_rebalance_days),
            exclude={index_ticker},
        )
    else:
        from dynamicgraph.config import REPO_ROOT

        path = Path(config.data.universe_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        resolution = resolve_static_universe(path, calendar, available - {index_ticker})

    for message in resolution.warnings:
        logger.warning("%s", message)
    logger.info(
        "Universe resolved via `%s`: %d ticker(s).", resolution.method, len(resolution.tickers)
    )
    return resolution


def constituent_count_over_time(membership: pd.DataFrame) -> pd.Series:
    """Number of members per date - used by the data-quality checks."""
    if membership.empty:
        return pd.Series(dtype="int64")
    return membership.groupby("date")["ticker"].nunique().sort_index()
