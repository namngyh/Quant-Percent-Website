"""One strategy across many markets.

The obvious use is "does this edge exist anywhere else", and the obvious
failure is to run it over twenty symbols, sort by Sharpe, and keep the top
one. That is a search, and the winner of a search is biased upward by the
search itself — exactly the trap the optimizer already documents (§4,
2026-09-09). Twenty markets is twenty trials whether or not anyone calls it a
sweep.

So this module reports the table people want and, beside it, the two things
that make the table readable:

* the **breadth** of the result — how many markets were profitable, and the
  median rather than the maximum. A strategy that works on one of twenty is a
  strategy that works on nothing, and the median says so where a ranked list
  does not.
* the **deflated Sharpe** of the best market, using the dispersion measured
  across these very markets. `sharpe_tests` normally has to approximate that
  dispersion because a single backtest cannot see the other trials; here the
  other trials are right there, which is the same reason the optimizer feeds
  it its own grid.

Comparability is the other trap. Markets do not share a calendar: 2,000 daily
bars of a Vietnamese equity and 2,000 hourly bars of BTC cover different
years, and a common `limit` hides that behind one number. Every row therefore
carries its own bar count and date span, and the summary refuses to compare
returns when the spans differ enough to matter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from statistics import median, pstdev

from backend.i18n import bi

log = logging.getLogger(__name__)

# Two spans are treated as comparable when the shorter covers at least this
# much of the longer. Below it, returns are measuring different years rather
# than different markets.
_SPAN_AGREEMENT = 0.75

# Sharpe dispersion needs more than a couple of numbers before its standard
# deviation means anything.
_MIN_MARKETS_FOR_DEFLATION = 3


@dataclass
class MarketRun:
    """One market's outcome, or the reason it produced none."""

    symbol: str
    timeframe: str
    result: dict | None = None
    error: str | None = None


def _span_ms(result: dict) -> int | None:
    times = result.get("times") or []
    if len(times) < 2:
        return None
    try:
        return int(times[-1]) - int(times[0])
    except (TypeError, ValueError):
        return None


def summarise(runs: list[MarketRun], metric: str = "sharpe") -> dict:
    """Fold per-market runs into a table plus the caveats it needs.

    `metric` only decides which market is called best; every row carries the
    full metric set either way.
    """
    rows: list[dict] = []
    failed: list[dict] = []

    for run in runs:
        if run.result is None:
            failed.append({"symbol": run.symbol, "error": run.error or "unknown"})
            continue
        metrics = run.result.get("metrics") or {}
        times = run.result.get("times") or []
        rows.append(
            {
                "symbol": run.symbol,
                "timeframe": run.timeframe,
                "bars": metrics.get("bars"),
                "first_time": int(times[0]) if times else None,
                "last_time": int(times[-1]) if times else None,
                "span_ms": _span_ms(run.result),
                "metrics": metrics,
                # Kept for the deflated-Sharpe step, which needs the winning
                # market's bar returns; stripped before the payload is sent.
                "equity": run.result.get("equity"),
            }
        )

    if not rows:
        return {
            "markets": 0,
            "rows": [],
            "failed": failed,
            "note": bi(
                "Không thị trường nào chạy được.",
                "No market produced a run.",
            ),
        }

    def value(row: dict, name: str) -> float | None:
        raw = row["metrics"].get(name)
        return float(raw) if isinstance(raw, (int, float)) else None

    sharpes = [v for v in (value(r, "sharpe") for r in rows) if v is not None]
    returns = [v for v in (value(r, "total_return_pct") for r in rows) if v is not None]
    scores = [(value(r, metric), r) for r in rows]
    ranked = sorted(
        (pair for pair in scores if pair[0] is not None),
        key=lambda pair: pair[0],
        reverse=True,
    )

    payload: dict = {
        "markets": len(rows),
        "metric": metric,
        "rows": [r for _, r in ranked] + [r for s, r in scores if s is None],
        "failed": failed,
        "best_symbol": ranked[0][1]["symbol"] if ranked else None,
        "worst_symbol": ranked[-1][1]["symbol"] if ranked else None,
    }

    # Breadth, which is the honest headline. One winner among twenty is noise;
    # fifteen among twenty is a result, and the median separates them where a
    # ranked table does not.
    if returns:
        payload["profitable_markets"] = sum(1 for v in returns if v > 0)
        payload["median_return_pct"] = median(returns)
        payload["best_return_pct"] = max(returns)
        payload["worst_return_pct"] = min(returns)
    if sharpes:
        payload["median_sharpe"] = median(sharpes)
        payload["best_sharpe"] = max(sharpes)

    payload["comparability"] = _comparability(rows)
    payload["deflated"] = _deflated(sharpes, rows)

    # The equity curves were only needed to deflate the winner. Twenty markets
    # times two thousand points is megabytes of JSON nobody reads, so they go
    # no further than this function.
    for row in rows:
        row.pop("equity", None)
    return payload


def _comparability(rows: list[dict]) -> dict:
    """Whether these rows are measuring the same stretch of time."""
    spans = [r["span_ms"] for r in rows if r["span_ms"]]
    timeframes = sorted({r["timeframe"] for r in rows})

    if len(spans) < 2:
        return {"comparable": True, "timeframes": timeframes}

    shortest, longest = min(spans), max(spans)
    ratio = shortest / longest if longest else 1.0
    comparable = ratio >= _SPAN_AGREEMENT and len(timeframes) == 1

    note = None
    if len(timeframes) > 1:
        note = bi(
            "Các thị trường chạy trên khung thời gian khác nhau "
            f"({', '.join(timeframes)}), nên lợi nhuận không so trực tiếp được.",
            "These markets ran on different timeframes "
            f"({', '.join(timeframes)}), so the returns are not directly comparable.",
        )
    elif not comparable:
        note = bi(
            f"Khoảng thời gian lệch nhau: thị trường ngắn nhất chỉ phủ "
            f"{ratio * 100:.0f}% thời gian của thị trường dài nhất. Lợi nhuận "
            "đang đo những quãng khác nhau chứ không chỉ những thị trường khác nhau.",
            f"The windows disagree: the shortest market covers only "
            f"{ratio * 100:.0f}% of the longest one's span. The returns are "
            "measuring different stretches of time, not just different markets.",
        )

    return {
        "comparable": comparable,
        "span_ratio": ratio,
        "timeframes": timeframes,
        "note": note,
    }


def _deflated(sharpes: list[float], rows: list[dict]) -> dict:
    """Deflate the best Sharpe by the breadth of the search that found it.

    Scanning N markets and keeping the best is N trials. The dispersion needed
    by the deflated Sharpe ratio is normally approximated, because one
    backtest cannot see its siblings; across markets the siblings are the
    other rows, so it is measured here exactly as the optimizer measures it
    across its grid.
    """
    if len(sharpes) < _MIN_MARKETS_FOR_DEFLATION:
        return {
            "available": False,
            "reason": bi(
                f"Cần ít nhất {_MIN_MARKETS_FOR_DEFLATION} thị trường thì độ phân tán "
                "Sharpe mới có nghĩa.",
                f"At least {_MIN_MARKETS_FOR_DEFLATION} markets are needed before the "
                "Sharpe dispersion means anything.",
            ),
        }

    best = max(sharpes)
    best_row = next(r for r in rows if r["metrics"].get("sharpe") == best)

    # Imported here: backend.analysis.stats pulls scipy, and that import was
    # measured at 557ms on the start-up path (§4, 2026-09-09).
    import numpy as np

    from backend.strategy.metrics import BARS_PER_YEAR
    from backend.analysis.stats import sharpe_tests

    # PSR and DSR are computed from the winning market's own bar returns, so
    # the equity curve has to be differenced back into them. The metrics block
    # carries summary numbers only.
    equity = np.asarray(best_row.get("equity") or [], dtype=float)
    if equity.size < 3:
        return {
            "available": False,
            "reason": bi(
                "Thị trường tốt nhất không có đủ đường vốn để tính PSR.",
                "The best market has too short an equity curve for PSR.",
            ),
        }
    bar_returns = np.diff(equity) / equity[:-1]
    bar_returns = bar_returns[np.isfinite(bar_returns)]

    dispersion = pstdev(sharpes) if len(sharpes) > 1 else 0.0
    periods = BARS_PER_YEAR.get(best_row["timeframe"], 365.0)

    try:
        tests = sharpe_tests(
            bar_returns,
            periods,
            n_trials=len(sharpes),
            trial_dispersion=dispersion,
        )
    except Exception as exc:                      # a stats failure is not fatal
        log.warning("deflated sharpe across markets failed: %s", exc)
        return {"available": False, "reason": bi(str(exc), str(exc))}

    return {
        "available": True,
        "symbol": best_row["symbol"],
        "sharpe": best,
        "trials": len(sharpes),
        "trial_dispersion": dispersion,
        "tests": tests,
        "note": bi(
            f"Sharpe tốt nhất ({best:.3f} ở {best_row['symbol']}) là kết quả của việc "
            f"quét {len(sharpes)} thị trường. Độ phân tán dùng để khử phồng được **đo** "
            "từ chính các thị trường này, không phải xấp xỉ.",
            f"The best Sharpe ({best:.3f} on {best_row['symbol']}) is the outcome of "
            f"scanning {len(sharpes)} markets. The dispersion used to deflate it is "
            "**measured** across those markets rather than approximated.",
        ),
    }
