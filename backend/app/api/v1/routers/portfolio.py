from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import CurrentUser, SessionDep, require_csrf
from app.db.models import SavedPortfolio as SavedPortfolioRow
from app.schemas.auth import SuccessResponse
from app.schemas.portfolio import (
    PortfolioAnalysis,
    PortfolioRequest,
    SavedPortfolio,
    SavedPortfolioInput,
    SavedPortfolioList,
)
from app.services import portfolio as service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Enough for a reader to keep a real account and a few what-ifs; small enough
# that the list stays a list and the table stays a footnote in the backup.
MAX_SAVED = 10


@router.post("/analyze", response_model=PortfolioAnalysis)
async def analyze(
    request: PortfolioRequest, session: SessionDep
) -> PortfolioAnalysis:
    """Measure an entered portfolio against its own price history.

    POST rather than GET: the holdings are the reader's own position data.
    Keeping them out of the URL keeps them out of access logs, browser
    history and referrer headers. Nothing is stored — the request is
    analysed and discarded, and the response is not cached.
    """
    try:
        return await service.analyze(session, request)
    except ValueError as exc:
        # The portfolio itself cannot be measured (no priced holding, or the
        # holdings share too few trading days). That is a property of the
        # request, so it is a 422 with the reason, not a 500.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "portfolio_not_analysable", "reason": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# Saved portfolios. Members only; the row is the request body under a name.
# ---------------------------------------------------------------------------


def _to_schema(row: SavedPortfolioRow) -> SavedPortfolio:
    body = PortfolioRequest.model_validate(row.payload)
    return SavedPortfolio(
        id=row.id,
        name=row.name,
        holdings=body.holdings,
        cash=body.cash,
        margin=body.margin,
        horizon_days=body.horizon_days,
        updated_at=row.updated_at,
    )


async def _owned(
    session: SessionDep, user: CurrentUser, portfolio_id: uuid.UUID
) -> SavedPortfolioRow:
    row = await session.scalar(
        select(SavedPortfolioRow).where(
            SavedPortfolioRow.id == portfolio_id,
            SavedPortfolioRow.user_id == user.id,
        )
    )
    # 404 for someone else's row as well as for a missing one: the id must
    # not reveal that another member's portfolio exists.
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "portfolio_not_found"},
        )
    return row


@router.get("/saved", response_model=SavedPortfolioList)
async def list_saved(session: SessionDep, user: CurrentUser) -> SavedPortfolioList:
    rows = (
        await session.scalars(
            select(SavedPortfolioRow)
            .where(SavedPortfolioRow.user_id == user.id)
            .order_by(SavedPortfolioRow.updated_at.desc())
        )
    ).all()
    return SavedPortfolioList(
        items=[_to_schema(r) for r in rows],
        remaining=max(0, MAX_SAVED - len(rows)),
    )


@router.post(
    "/saved",
    response_model=SavedPortfolio,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_saved(
    payload: SavedPortfolioInput, session: SessionDep, user: CurrentUser
) -> SavedPortfolio:
    count = await session.scalar(
        select(func.count())
        .select_from(SavedPortfolioRow)
        .where(SavedPortfolioRow.user_id == user.id)
    )
    if (count or 0) >= MAX_SAVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "portfolio_limit", "limit": MAX_SAVED},
        )
    row = SavedPortfolioRow(
        user_id=user.id,
        name=payload.name,
        payload=PortfolioRequest.model_validate(payload.model_dump()).model_dump(
            mode="json"
        ),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_schema(row)


@router.put(
    "/saved/{portfolio_id}",
    response_model=SavedPortfolio,
    dependencies=[Depends(require_csrf)],
)
async def update_saved(
    portfolio_id: uuid.UUID,
    payload: SavedPortfolioInput,
    session: SessionDep,
    user: CurrentUser,
) -> SavedPortfolio:
    row = await _owned(session, user, portfolio_id)
    row.name = payload.name
    row.payload = PortfolioRequest.model_validate(payload.model_dump()).model_dump(
        mode="json"
    )
    row.updated_at = func.now()
    await session.commit()
    await session.refresh(row)
    return _to_schema(row)


@router.delete(
    "/saved/{portfolio_id}",
    response_model=SuccessResponse,
    dependencies=[Depends(require_csrf)],
)
async def delete_saved(
    portfolio_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SuccessResponse:
    row = await _owned(session, user, portfolio_id)
    await session.delete(row)
    await session.commit()
    return SuccessResponse()
