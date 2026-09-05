"""Candle and dataset endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.config import settings
from backend.data import market_vn, service, sources, store
from backend.data.binance import INTERVAL_MS, now_ms, to_ms

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["data"])

# Guards against two backfills writing the same series at once.
_backfill_lock = asyncio.Lock()


class BackfillRequest(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    start_date: str | None = Field(
        default=None, description="ISO date; defaults to config data.start_date"
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
async def get_config() -> dict:
    """Everything the UI needs to populate its selectors.

    The Vietnam symbol list is not included here: it is 389 rows behind a VPN,
    and a config call that blocks or fails when the VPN is off would stop the
    whole app loading. The UI fetches it separately, on demand.
    """
    return {
        "symbols": settings.data.symbols,
        "timeframes": settings.data.timeframes,
        "default_symbol": settings.chart.default_symbol,
        "default_timeframe": settings.chart.default_timeframe,
        "max_candles": settings.chart.max_candles,
        "markets": [
            {
                "id": sources.CRYPTO,
                "label": "Crypto · Binance",
                "symbols": settings.data.symbols,
                "timeframes": settings.data.timeframes,
                "live": True,
                "backfill": True,
                "available": True,
            },
            {
                "id": sources.VIETNAM,
                "label": "Việt Nam · HOSE",
                "symbols": [],           # fetched from /api/markets/vn/symbols
                "timeframes": market_vn.SUPPORTED_TIMEFRAMES,
                "live": False,
                "backfill": False,
                "available": market_vn.configured(),
            },
        ],
    }


@router.get("/coverage")
def coverage() -> dict:
    """What is actually stored, per (symbol, timeframe)."""
    return {"series": store.list_coverage()}


# Sync on purpose — see the note in routes_indicators.py: blocking DuckDB reads
# belong in FastAPI's threadpool, not on the event loop the backfill runs on.
@router.get("/candles")
def candles(
    symbol: str = Query(default=None),
    timeframe: str = Query(default=None),
    limit: int = Query(default=None, ge=1),
    start: str | None = Query(default=None, description="ISO date, inclusive"),
    end: str | None = Query(default=None, description="ISO date, inclusive"),
) -> dict:
    """Candles shaped for Lightweight Charts (time in epoch *seconds*)."""
    symbol = symbol or settings.chart.default_symbol
    timeframe = timeframe or settings.chart.default_timeframe

    allowed = sources.timeframes_for(symbol)
    if timeframe not in allowed:
        raise HTTPException(
            400,
            f"Khung `{timeframe}` không có cho {symbol}. Hỗ trợ: {', '.join(allowed)}.",
        )

    max_candles = settings.chart.max_candles
    limit = min(limit or max_candles, max_candles)

    try:
        start_ms = to_ms(start) if start else None
        end_ms = to_ms(end) if end else None
    except ValueError as exc:
        raise HTTPException(400, f"bad date: {exc}") from exc

    try:
        df = sources.get_candles(symbol, timeframe, start_ms, end_ms, limit)
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    if df.empty:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": 0,
            "candles": [],
            "volumes": [],
            "message": "No data stored for this series yet: run a backfill.",
        }

    times = (df["open_time"] // 1000).astype("int64").tolist()

    # How stale is the newest bar, in whole bars? The Vietnam database is read
    # live and is never behind; only the local crypto store can fall behind
    # while the machine is off.
    last_ms = int(df["open_time"].iloc[-1])
    interval = INTERVAL_MS.get(timeframe)
    if interval and sources.supports_backfill(symbol):
        bars_behind = max(0, int((now_ms() - last_ms) // interval) - 1)
    else:
        bars_behind = 0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(df),
        "last_ms": last_ms,
        "bars_behind": bars_behind,
        "can_backfill": sources.supports_backfill(symbol),
        "candles": [
            {"time": t, "open": o, "high": h, "low": l, "close": c}
            for t, o, h, l, c in zip(
                times, df["open"], df["high"], df["low"], df["close"], strict=True
            )
        ],
        "volumes": [
            {"time": t, "value": v, "up": c >= o}
            for t, v, c, o in zip(times, df["volume"], df["close"], df["open"], strict=True)
        ],
    }


@router.post("/backfill")
async def backfill(request: BackfillRequest) -> dict:
    """Fetch missing candles from Binance. Resumes from what is already stored."""
    for symbol in request.symbols or settings.data.symbols:
        if not sources.supports_backfill(symbol):
            raise HTTPException(
                400,
                f"{symbol} đến từ database của team và chỉ đọc, không backfill được.",
            )

    if _backfill_lock.locked():
        raise HTTPException(409, "a backfill is already running")

    async with _backfill_lock:
        start_ms = to_ms(request.start_date) if request.start_date else None
        try:
            report = await service.backfill_all(
                symbols=request.symbols,
                timeframes=request.timeframes,
                start_ms=start_ms,
            )
        except Exception as exc:
            log.exception("backfill request failed")
            raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    return report.as_dict()
