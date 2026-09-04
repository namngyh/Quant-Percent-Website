from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import OptionalUser, SessionDep
from app.schemas.models import (
    ForecastHistory,
    ForecastRecords,
    ModelDetail,
    ModelList,
)
from app.services import models as service

router = APIRouter(prefix="/models", tags=["models"])


async def _load(session, slug: str):
    model = await service.get_model(session, slug)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"}
        )
    return model


def _guard(model, user) -> None:
    """Members-only models return 403 rather than data — the lock lives
    here, not in the browser."""
    if service.is_locked(model, user is not None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "members_only"},
        )


@router.get("", response_model=ModelList)
async def list_models(session: SessionDep, user: OptionalUser) -> ModelList:
    return await service.list_models(session, authenticated=user is not None)


@router.get("/{slug}", response_model=ModelDetail)
async def model_detail(
    slug: str, session: SessionDep, user: OptionalUser
) -> ModelDetail:
    model = await _load(session, slug)
    last_output = (await service.last_output_by_model(session)).get(slug)
    # Metadata stays public so the page keeps its context and SEO;
    # the model's output is what requires a session.
    return service.to_detail(
        model, authenticated=user is not None, last_output_at=last_output
    )


@router.get("/{slug}/latest", response_model=ForecastRecords)
async def latest(
    slug: str,
    session: SessionDep,
    user: OptionalUser,
    symbol: str | None = Query(None),
) -> ForecastRecords:
    model = await _load(session, slug)
    _guard(model, user)
    if not model.show_forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_available"},
        )
    return ForecastRecords(
        records=await service.latest_forecasts(session, model, symbol)
    )


@router.get("/{slug}/history", response_model=ForecastHistory)
async def history(
    slug: str,
    session: SessionDep,
    user: OptionalUser,
    symbol: str | None = Query(None),
) -> ForecastHistory:
    model = await _load(session, slug)
    _guard(model, user)
    if not model.show_forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_available"},
        )
    return await service.forecast_history(session, model, symbol)
