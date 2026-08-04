"""Data validation.

Every check returns a structured `ValidationCheck`; nothing raises unless the
panel is unusable. Warnings are surfaced in the audit report and propagated to
the website payload so a consumer can see the data caveats.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.data.calendar import business_day_gaps, infer_trading_calendar, missing_trading_dates
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    severity: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    checks: list[ValidationCheck] = field(default_factory=list)
    n_rows: int = 0
    n_tickers: int = 0
    date_min: str | None = None
    date_max: str | None = None
    excluded_tickers: list[str] = field(default_factory=list)

    def add(
        self,
        name: str,
        passed: bool,
        severity: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.checks.append(ValidationCheck(name, passed, severity, message, detail or {}))

    @property
    def errors(self) -> list[ValidationCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[ValidationCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_tickers": self.n_tickers,
            "date_min": self.date_min,
            "date_max": self.date_max,
            "excluded_tickers": self.excluded_tickers,
            "n_errors": len(self.errors),
            "n_warnings": len(self.warnings),
            "checks": [asdict(c) for c in self.checks],
        }

    def summary_lines(self) -> list[str]:
        lines = []
        for check in self.checks:
            mark = "PASS" if check.passed else check.severity.upper()
            lines.append(f"[{mark}] {check.name}: {check.message}")
        return lines


def validate_panel(
    panel: pd.DataFrame,
    config: Any,
    index_ticker: str = "VN30",
    calendar: pd.DatetimeIndex | None = None,
) -> ValidationReport:
    """Run every data-quality check described in the project brief."""
    report = ValidationReport(
        n_rows=len(panel),
        n_tickers=int(panel["ticker"].nunique()),
        date_min=str(panel["date"].min().date()) if len(panel) else None,
        date_max=str(panel["date"].max().date()) if len(panel) else None,
    )
    if panel.empty:
        report.add("non_empty", False, "error", "Panel is empty.")
        return report

    data_cfg = config.data
    calendar = calendar if calendar is not None else infer_trading_calendar(panel, index_ticker)

    # ---- 1. duplicates -------------------------------------------------
    duplicates = panel.duplicated(subset=["ticker", "date"]).sum()
    report.add(
        "duplicate_ticker_date",
        duplicates == 0,
        "error",
        f"{duplicates} duplicate (ticker, date) row(s)." if duplicates else "No duplicates.",
        {"n_duplicates": int(duplicates)},
    )

    # ---- 2. missing trading dates --------------------------------------
    missing = missing_trading_dates(panel, calendar)
    worst = missing.sort_values("missing_ratio", ascending=False).head(10)
    high_missing = missing[missing["missing_ratio"] > data_cfg.max_missing_ratio_per_window]
    report.add(
        "missing_trading_dates",
        high_missing.empty,
        "warning",
        (
            f"{len(high_missing)} ticker(s) miss more than "
            f"{data_cfg.max_missing_ratio_per_window:.0%} of their in-range trading days."
            if not high_missing.empty
            else "All tickers cover their in-range trading days."
        ),
        {"worst": worst.to_dict(orient="records")},
    )

    # ---- 3. non-positive prices ---------------------------------------
    price_columns = [c for c in ("open", "high", "low", "close", "adjusted_close") if c in panel.columns]
    non_positive = int(sum((panel[c] <= 0).sum() for c in price_columns))
    report.add(
        "non_positive_prices",
        non_positive == 0,
        "error",
        f"{non_positive} non-positive price value(s)." if non_positive else "All prices positive.",
        {"n": non_positive},
    )

    # ---- 4. negative volume -------------------------------------------
    if "volume" in panel.columns:
        negative = int((panel["volume"] < 0).sum())
        report.add(
            "negative_volume",
            negative == 0,
            "error",
            f"{negative} negative volume value(s)." if negative else "No negative volume.",
            {"n": negative},
        )

    # ---- 5. OHLC coherence ---------------------------------------------
    if {"open", "high", "low", "close"}.issubset(panel.columns):
        valid = panel[["open", "high", "low", "close"]].notna().all(axis=1)
        broken = int(
            (
                valid
                & (
                    (panel["high"] < panel["low"])
                    | (panel["high"] < panel["close"])
                    | (panel["high"] < panel["open"])
                    | (panel["low"] > panel["close"])
                    | (panel["low"] > panel["open"])
                )
            ).sum()
        )
        report.add(
            "ohlc_coherence",
            broken == 0,
            "warning",
            f"{broken} row(s) violate low <= {{open, close}} <= high." if broken else "OHLC coherent.",
            {"n": broken},
        )

    # ---- 6. abnormal jumps / corporate-action-like moves ---------------
    price = "adjusted_close" if "adjusted_close" in panel.columns else "close"
    wide = panel.pivot_table(index="date", columns="ticker", values=price, aggfunc="last").sort_index()
    log_returns = np.log(wide).diff()
    sigma = log_returns.rolling(60, min_periods=20).std()
    z = (log_returns / (sigma + 1e-12)).abs()
    jumps = z > data_cfg.jump_sigma_threshold
    jump_counts = jumps.sum().sort_values(ascending=False)
    total_jumps = int(jump_counts.sum())
    report.add(
        "abnormal_price_jumps",
        total_jumps == 0,
        "warning",
        (
            f"{total_jumps} return(s) exceed {data_cfg.jump_sigma_threshold} rolling sigma - "
            "possible unadjusted corporate actions or data errors."
            if total_jumps
            else "No abnormal price jumps."
        ),
        {"by_ticker": jump_counts[jump_counts > 0].head(15).to_dict()},
    )

    # Daily price limits on HOSE are +/-7%; anything far beyond that on a stock
    # is a corporate action the adjustment did not capture.
    stock_returns = log_returns.drop(columns=[index_ticker], errors="ignore")
    extreme = (stock_returns.abs() > 0.20).sum()
    n_extreme = int(extreme.sum())
    report.add(
        "corporate_action_like_jumps",
        n_extreme == 0,
        "warning",
        (
            f"{n_extreme} single-day |log return| > 20% on individual stocks. HOSE's daily band "
            "is +/-7%, so these are almost certainly unadjusted corporate actions."
            if n_extreme
            else "No corporate-action-like jumps beyond the daily price band."
        ),
        {"by_ticker": extreme[extreme > 0].head(15).to_dict()},
    )

    # ---- 7. short history ----------------------------------------------
    history = panel.groupby("ticker")["date"].count()
    short = history[history < data_cfg.minimum_history_days]
    report.add(
        "minimum_history",
        short.empty,
        "warning",
        (
            f"{len(short)} ticker(s) have fewer than {data_cfg.minimum_history_days} observations."
            if not short.empty
            else "All tickers meet the minimum history requirement."
        ),
        {"tickers": short.to_dict()},
    )
    report.excluded_tickers = sorted(short.index.tolist())

    # ---- 8. stale prices ------------------------------------------------
    stale_runs: dict[str, int] = {}
    for ticker in wide.columns:
        series = wide[ticker].dropna()
        if series.empty:
            continue
        unchanged = series.diff().eq(0)
        run, longest = 0, 0
        for flag in unchanged.to_numpy():
            run = run + 1 if flag else 0
            longest = max(longest, run)
        if longest >= data_cfg.stale_price_max_run:
            stale_runs[str(ticker)] = int(longest)
    report.add(
        "stale_prices",
        not stale_runs,
        "warning",
        (
            f"{len(stale_runs)} ticker(s) have a run of >= {data_cfg.stale_price_max_run} "
            "identical consecutive closes."
            if stale_runs
            else "No stale price runs."
        ),
        {"longest_runs": dict(sorted(stale_runs.items(), key=lambda kv: -kv[1])[:15])},
    )

    # ---- 9. zero-return ratio -------------------------------------------
    zero_ratio = (log_returns == 0).sum() / log_returns.notna().sum().replace(0, np.nan)
    illiquid = zero_ratio[zero_ratio > 0.30].dropna()
    report.add(
        "zero_return_ratio",
        illiquid.empty,
        "warning",
        (
            f"{len(illiquid)} ticker(s) have >30% zero-return days (illiquid or stale)."
            if not illiquid.empty
            else "Zero-return ratios are within a normal range."
        ),
        {"ratios": illiquid.round(3).to_dict()},
    )

    # ---- 10. forward-fill intensity --------------------------------------
    if "is_filled" in panel.columns:
        filled = panel.groupby("ticker")["is_filled"].mean()
        heavy = filled[filled > 0.05]
        report.add(
            "excess_forward_fill",
            heavy.empty,
            "warning",
            (
                f"{len(heavy)} ticker(s) have >5% forward-filled rows."
                if not heavy.empty
                else "Forward-fill usage is minimal."
            ),
            {"ratios": heavy.round(4).to_dict()},
        )

    # ---- 11. calendar alignment ------------------------------------------
    per_date = panel.groupby("date")["ticker"].nunique()
    n_tickers = panel["ticker"].nunique()
    ragged = per_date[per_date < 0.5 * n_tickers]
    report.add(
        "calendar_alignment",
        len(ragged) <= 0.02 * len(per_date),
        "warning",
        (
            f"{len(ragged)} date(s) have fewer than half of the tickers reporting - "
            "sources may not share a trading calendar."
            if len(ragged)
            else "Tickers share a common trading calendar."
        ),
        {"n_ragged_dates": int(len(ragged))},
    )

    gaps = business_day_gaps(calendar, max_gap=10)
    report.add(
        "calendar_gaps",
        gaps.empty,
        "info",
        (
            f"{len(gaps)} calendar gap(s) longer than 10 days (holidays or data outages)."
            if not gaps.empty
            else "No unusual calendar gaps."
        ),
        {"gaps": [
            {"from": str(a.date()), "to": str(b.date()), "days": int(d)}
            for a, b, d in zip(gaps["from"], gaps["to"], gaps["calendar_days"])
        ][:10]},
    )

    # ---- 12. timestamp normalisation --------------------------------------
    non_midnight = int((panel["date"] != panel["date"].dt.normalize()).sum())
    report.add(
        "timestamp_normalisation",
        non_midnight == 0,
        "warning",
        f"{non_midnight} timestamp(s) carry an intraday component." if non_midnight else "All timestamps are dates.",
        {"n": non_midnight},
    )

    # ---- 13. constituent count over time ----------------------------------
    counts = per_date
    report.add(
        "constituent_count",
        True,
        "info",
        f"Ticker count per date ranges {int(counts.min())}..{int(counts.max())} "
        f"(median {int(counts.median())}).",
        {
            "min": int(counts.min()),
            "max": int(counts.max()),
            "median": int(counts.median()),
            "first_date_count": int(counts.iloc[0]),
            "last_date_count": int(counts.iloc[-1]),
        },
    )

    # ---- 14. index presence ------------------------------------------------
    report.add(
        "index_present",
        index_ticker in set(panel["ticker"]),
        "error",
        f"Index `{index_ticker}` {'present' if index_ticker in set(panel['ticker']) else 'MISSING'}.",
    )

    for check in report.checks:
        if not check.passed:
            log = logger.error if check.severity == "error" else logger.warning
            log("[%s] %s", check.name, check.message)
    return report


def apply_exclusions(
    panel: pd.DataFrame, report: ValidationReport, index_ticker: str, enforce: bool = True
) -> pd.DataFrame:
    """Drop tickers flagged as having insufficient history (never the index)."""
    if not enforce or not report.excluded_tickers:
        return panel
    drop = [t for t in report.excluded_tickers if t != index_ticker]
    if not drop:
        return panel
    logger.warning("Excluding %d ticker(s) with insufficient history: %s", len(drop), drop)
    return panel[~panel["ticker"].isin(drop)].reset_index(drop=True)


def rolling_window_validity(
    returns: pd.DataFrame, window: int, max_missing_ratio: float
) -> pd.DataFrame:
    """Boolean date x ticker mask: is this ticker usable in the window ending at t?

    A ticker is valid when at most `max_missing_ratio` of the window's returns
    are missing. Used to drop nodes from a graph snapshot without invalidating
    the whole snapshot.
    """
    observed = returns.notna().astype(float)
    coverage = observed.rolling(window, min_periods=window).mean()
    return coverage >= (1.0 - max_missing_ratio)
