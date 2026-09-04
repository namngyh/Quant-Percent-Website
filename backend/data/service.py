"""Backfill and incremental update orchestration.

Sits between the Binance client and the DuckDB store: decides *where* to
resume from, streams pages in, and reports progress.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.config import settings
from backend.data import store
from backend.data.binance import INTERVAL_MS, BinanceClient, now_ms, to_ms

log = logging.getLogger(__name__)

ProgressFn = Callable[["BackfillProgress"], None]


@dataclass
class BackfillProgress:
    symbol: str
    timeframe: str
    rows_written: int = 0
    pages: int = 0
    first_ms: int | None = None
    last_ms: int | None = None
    done: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "rows_written": self.rows_written,
            "pages": self.pages,
            "first_ms": self.first_ms,
            "last_ms": self.last_ms,
            "done": self.done,
            "error": self.error,
        }


@dataclass
class BackfillReport:
    results: list[BackfillProgress] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(r.rows_written for r in self.results)

    def as_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "series": [r.as_dict() for r in self.results],
        }


def _resume_point(symbol: str, timeframe: str, default_start_ms: int) -> int:
    """Where to start fetching.

    Resumes from the last stored candle's own open_time rather than the next
    one: the newest stored candle may have been saved while still forming, so
    it must be re-fetched and overwritten.
    """
    coverage = store.get_coverage(symbol, timeframe)
    if not coverage:
        return default_start_ms
    return coverage["last"]


async def backfill_series(
    client: BinanceClient,
    symbol: str,
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    progress_cb: ProgressFn | None = None,
) -> BackfillProgress:
    """Fill one (symbol, timeframe) series up to ``end_ms`` (default: now)."""
    if timeframe not in INTERVAL_MS:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    default_start = start_ms if start_ms is not None else to_ms(settings.data.start_date)
    cursor = _resume_point(symbol, timeframe, default_start)
    end = end_ms or now_ms()

    progress = BackfillProgress(symbol=symbol, timeframe=timeframe)

    try:
        async for page in client.iter_klines(symbol, timeframe, cursor, end):
            written = store.upsert_candles(symbol, timeframe, page)
            progress.rows_written += written
            progress.pages += 1
            page_first = int(page["open_time"].iloc[0])
            page_last = int(page["open_time"].iloc[-1])
            progress.first_ms = progress.first_ms or page_first
            progress.last_ms = page_last
            if progress_cb:
                progress_cb(progress)
    except Exception as exc:  # surfaced to the caller, not swallowed
        progress.error = f"{type(exc).__name__}: {exc}"
        log.exception("backfill failed for %s %s", symbol, timeframe)
    finally:
        progress.done = True
        if progress_cb:
            progress_cb(progress)

    return progress


async def backfill_all(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    start_ms: int | None = None,
    progress_cb: ProgressFn | None = None,
) -> BackfillReport:
    """Backfill every configured (symbol, timeframe) pair."""
    symbols = symbols or settings.data.symbols
    timeframes = timeframes or settings.data.timeframes

    report = BackfillReport()
    async with BinanceClient() as client:
        for symbol in symbols:
            for timeframe in timeframes:
                log.info("backfilling %s %s", symbol, timeframe)
                result = await backfill_series(
                    client, symbol, timeframe, start_ms=start_ms, progress_cb=progress_cb
                )
                report.results.append(result)
    return report
