from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.deps import SessionDep
from app.schemas.portfolio import PortfolioAnalysis, PortfolioRequest
from app.services import portfolio as service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


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
