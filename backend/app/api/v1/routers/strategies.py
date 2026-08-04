from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.deps import SessionDep
from app.core.redis import cache_get, cache_set
from app.schemas.performance import (
    PerformanceSeries,
    Simulation,
    StrategyDetail,
    StrategyList,
    StrategyMetrics,
)
from app.services import performance as service

router = APIRouter(prefix="/strategies", tags=["performance"])

# Finished research runs change only when a report is republished
CACHE_TTL = 3600


async def _load(session, slug: str):
    strategy = await service.get_strategy(session, slug)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"}
        )
    return strategy


@router.get("", response_model=StrategyList)
async def list_strategies(session: SessionDep) -> StrategyList:
    cached = await cache_get("strategies:list")
    if cached:
        return StrategyList.model_validate(cached)
    result = await service.list_strategies(session)
    await cache_set("strategies:list", result.model_dump(mode="json"), CACHE_TTL)
    return result


@router.get("/{slug}", response_model=StrategyDetail)
async def strategy_detail(slug: str, session: SessionDep) -> StrategyDetail:
    key = f"strategies:{slug}:detail"
    cached = await cache_get(key)
    if cached:
        return StrategyDetail.model_validate(cached)
    result = await service.get_detail(session, await _load(session, slug))
    await cache_set(key, result.model_dump(mode="json"), CACHE_TTL)
    return result


@router.get("/{slug}/performance", response_model=PerformanceSeries)
async def performance(slug: str, session: SessionDep) -> PerformanceSeries:
    key = f"strategies:{slug}:performance"
    cached = await cache_get(key)
    if cached:
        return PerformanceSeries.model_validate(cached)
    result = await service.get_series(session, await _load(session, slug))
    await cache_set(key, result.model_dump(mode="json"), CACHE_TTL)
    return result


@router.get("/{slug}/metrics", response_model=StrategyMetrics)
async def metrics(slug: str, session: SessionDep) -> StrategyMetrics:
    key = f"strategies:{slug}:metrics"
    cached = await cache_get(key)
    if cached:
        return StrategyMetrics.model_validate(cached)
    result = await service.get_metrics(session, await _load(session, slug))
    await cache_set(key, result.model_dump(mode="json"), CACHE_TTL)
    return result


@router.get("/{slug}/simulations", response_model=Simulation)
async def simulations(slug: str, session: SessionDep) -> Simulation:
    key = f"strategies:{slug}:simulations"
    cached = await cache_get(key)
    if cached:
        return Simulation.model_validate(cached)
    result = await service.get_simulation(session, await _load(session, slug))
    if result is None:
        # Only multi-seed runs produce a distribution over seeds
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_available"},
        )
    await cache_set(key, result.model_dump(mode="json"), CACHE_TTL)
    return result
