from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import SessionDep
from app.core.redis import cache_get, cache_set
from app.schemas.market import (
    Constituents,
    History,
    MarketOverview,
    Quote,
    RiskDashboard,
)
from app.services import market as service

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverview)
async def overview(session: SessionDep) -> MarketOverview:
    cached = await cache_get("market:overview")
    if cached:
        return MarketOverview.model_validate(cached)
    result = await service.get_overview(session)
    await cache_set("market:overview", result.model_dump(mode="json"), 15)
    return result


@router.get("/vn30/constituents", response_model=Constituents)
async def constituents(session: SessionDep) -> Constituents:
    cached = await cache_get("market:vn30")
    if cached:
        return Constituents.model_validate(cached)
    result = await service.get_constituents(session)
    await cache_set("market:vn30", result.model_dump(mode="json"), 60)
    return result


@router.get("/risk", response_model=RiskDashboard)
async def risk(session: SessionDep) -> RiskDashboard:
    cached = await cache_get("market:risk")
    if cached:
        return RiskDashboard.model_validate(cached)
    result = await service.get_risk(session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "risk_metrics_unavailable"},
        )
    await cache_set("market:risk", result.model_dump(mode="json"), 60)
    return result


# Declared after the fixed paths so "vn30" and "risk" are never captured
# as a symbol
@router.get("/{symbol}/quote", response_model=Quote)
async def quote(symbol: str, session: SessionDep) -> Quote:
    key = f"market:quote:{symbol.upper()}"
    cached = await cache_get(key)
    if cached:
        return Quote.model_validate(cached)
    result = await service.get_quote(session, symbol)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "symbol_not_found"},
        )
    await cache_set(key, result.model_dump(mode="json"), 10)
    return result


@router.get("/{symbol}/history", response_model=History)
async def history(
    symbol: str,
    session: SessionDep,
    count: int = Query(250, ge=1, le=1000),
) -> History:
    key = f"market:history:{symbol.upper()}:{count}"
    cached = await cache_get(key)
    if cached:
        return History.model_validate(cached)
    result = await service.get_history(session, symbol, count)
    await cache_set(key, result.model_dump(mode="json"), 60)
    return result
