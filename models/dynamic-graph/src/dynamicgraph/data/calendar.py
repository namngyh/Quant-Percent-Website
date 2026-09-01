"""Trading-calendar utilities.

The calendar is inferred from the data itself (the index series is the
reference), never from a hard-coded holiday table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def infer_trading_calendar(
    panel: pd.DataFrame,
    reference_ticker: str | None = None,
    min_coverage: float = 0.5,
) -> pd.DatetimeIndex:
    """Infer the trading calendar.

    If `reference_ticker` is present its dates define the calendar. Otherwise
    any date on which at least `min_coverage` of the tickers traded counts as a
    trading day.
    """
    if reference_ticker and reference_ticker in set(panel["ticker"]):
        dates = panel.loc[panel["ticker"] == reference_ticker, "date"]
        return pd.DatetimeIndex(sorted(dates.unique()))

    counts = panel.groupby("date")["ticker"].nunique()
    n_tickers = panel["ticker"].nunique()
    keep = counts[counts >= max(1, int(min_coverage * n_tickers))]
    return pd.DatetimeIndex(sorted(keep.index))


def missing_trading_dates(
    panel: pd.DataFrame, calendar: pd.DatetimeIndex
) -> pd.DataFrame:
    """Per-ticker count of calendar days with no observation, within the
    ticker's own listed range (so pre-IPO gaps are not counted as missing)."""
    rows = []
    calendar_set = pd.Index(calendar)
    for ticker, group in panel.groupby("ticker", sort=False):
        own = pd.DatetimeIndex(sorted(group["date"].unique()))
        if len(own) == 0:
            continue
        window = calendar_set[(calendar_set >= own.min()) & (calendar_set <= own.max())]
        missing = window.difference(own)
        rows.append(
            {
                "ticker": ticker,
                "first_date": own.min(),
                "last_date": own.max(),
                "n_observations": len(own),
                "n_expected": len(window),
                "n_missing": len(missing),
                "missing_ratio": (len(missing) / len(window)) if len(window) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def align_to_calendar(
    panel: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    max_forward_fill_days: int = 1,
    price_columns: tuple[str, ...] = ("open", "high", "low", "close", "adjusted_close"),
    active_membership: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Reindex every ticker onto the calendar.

    Prices may be forward-filled up to `max_forward_fill_days` consecutive days
    (0 disables it). Volume/turnover are NEVER forward-filled: a non-trading day
    has zero traded quantity, not yesterday's. `is_filled` marks synthetic rows.

    When `active_membership` is supplied, it must contain daily `(date, ticker)`
    pairs. A ticker is emitted only on active dates and each contiguous membership
    spell is filled independently. This prevents prices from being carried across
    an entry, exit, or re-entry boundary.
    """
    frames: list[pd.DataFrame] = []
    flow_columns = [c for c in ("volume", "turnover", "foreign_buy_value", "foreign_sell_value")
                    if c in panel.columns]
    membership_by_ticker: dict[str, pd.DatetimeIndex] | None = None
    if active_membership is not None:
        required = {"date", "ticker"}
        if not required.issubset(active_membership.columns):
            raise ValueError("active_membership must contain `date` and `ticker` columns.")
        active = active_membership.loc[:, ["date", "ticker"]].drop_duplicates().copy()
        active["date"] = pd.to_datetime(active["date"])
        membership_by_ticker = {
            str(ticker): pd.DatetimeIndex(sorted(group["date"].unique()))
            for ticker, group in active.groupby("ticker", sort=False)
        }

    for ticker, group in panel.groupby("ticker", sort=False):
        group = group.sort_values("date").drop_duplicates("date", keep="last")
        if membership_by_ticker is None:
            own = pd.DatetimeIndex(group["date"])
            windows = [calendar[(calendar >= own.min()) & (calendar <= own.max())]]
        else:
            active_dates = membership_by_ticker.get(str(ticker), pd.DatetimeIndex([]))
            active_dates = active_dates[active_dates.isin(calendar)]
            if active_dates.empty:
                continue
            positions = calendar.get_indexer(active_dates)
            segment = np.r_[0, np.cumsum(np.diff(positions) != 1)]
            windows = [
                active_dates[segment == segment_id]
                for segment_id in np.unique(segment)
            ]

        indexed = group.set_index("date")
        for window in windows:
            if len(window) == 0:
                continue
            # Restrict source observations before reindexing. In particular, the
            # first missing day of a new membership spell cannot inherit a price
            # from the previous inactive spell.
            source = indexed[indexed.index.isin(window)]
            reindexed = source.reindex(window)
            reindexed.index.name = "date"

            observed = reindexed["close"].notna()
            reindexed["is_filled"] = ~observed

            if max_forward_fill_days > 0:
                present = [c for c in price_columns if c in reindexed.columns]
                reindexed[present] = reindexed[present].ffill(limit=max_forward_fill_days)
            for column in flow_columns:
                reindexed[column] = reindexed[column].where(observed, 0.0)

            reindexed["ticker"] = ticker
            for static in ("sector", "is_index"):
                if static in reindexed.columns:
                    reindexed[static] = reindexed[static].ffill().bfill()
            frames.append(reindexed.reset_index())

    if not frames:
        return panel.assign(is_filled=False)
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)


def to_wide(panel: pd.DataFrame, value_column: str = "adjusted_close") -> pd.DataFrame:
    """Pivot the long panel into a date x ticker matrix."""
    wide = panel.pivot_table(
        index="date", columns="ticker", values=value_column, aggfunc="last"
    )
    return wide.sort_index()


def trading_day_offsets(calendar: pd.DatetimeIndex) -> dict[pd.Timestamp, int]:
    """Map each trading date to its integer position (used for purging)."""
    return {date: i for i, date in enumerate(calendar)}


def business_day_gaps(calendar: pd.DatetimeIndex, max_gap: int = 10) -> pd.DataFrame:
    """Report unusually long gaps in the calendar (holiday clusters, outages)."""
    if len(calendar) < 2:
        return pd.DataFrame(columns=["from", "to", "calendar_days"])
    deltas = np.diff(calendar.values).astype("timedelta64[D]").astype(int)
    idx = np.where(deltas > max_gap)[0]
    return pd.DataFrame(
        {
            "from": calendar[idx],
            "to": calendar[idx + 1],
            "calendar_days": deltas[idx],
        }
    )
