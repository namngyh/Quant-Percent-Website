"""Indicator catalog and compute endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.data import store
from backend.indicators import registry
from backend.indicators.base import IndicatorError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/indicators", tags=["indicators"])


class ComputeRequest(BaseModel):
    indicator_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    limit: int | None = None
    start: str | None = None
    end: str | None = None


# These handlers are deliberately sync (`def`, not `async def`): they do
# blocking DuckDB and pandas work, and FastAPI runs sync handlers in a
# threadpool. As `async def` they would stall the event loop — and with a long
# backfill streaming on that same loop, the whole UI would freeze.
@router.get("")
def catalog() -> dict:
    """Every indicator the UI can offer, plus any plugin that failed to load."""
    reg = registry.get_registry()
    items = [spec.as_dict() for spec in reg.values()]
    items.sort(key=lambda s: (s["source"] != "plugin", s["category"], s["name"]))

    return {
        "count": len(items),
        "indicators": items,
        "categories": sorted({s["category"] for s in items}),
        "plugin_errors": registry.get_plugin_errors(),
    }


@router.post("/compute")
def compute(request: ComputeRequest) -> dict:
    """Run one indicator over a stored candle series."""
    symbol = request.symbol or settings.chart.default_symbol
    timeframe = request.timeframe or settings.chart.default_timeframe
    limit = min(request.limit or settings.chart.max_candles, settings.chart.max_candles)

    df = store.get_candles(symbol, timeframe, limit=limit)
    if df.empty:
        raise HTTPException(404, f"no candles stored for {symbol} {timeframe}")

    try:
        return registry.compute(request.indicator_id, df, request.params)
    except IndicatorError as exc:
        # Expected failure (bad params, indicator can't run on this data):
        # report it to the UI rather than as a server error.
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("indicator %s failed", request.indicator_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc
