"""Paper-trading endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.routes_strategy import ExecutionSettings
from backend.config import settings
from backend.paper.engine import OrderRefused
from backend.paper.manager import manager
from backend.strategy.base import StrategyError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paper", tags=["paper"])


class StartRequest(BaseModel):
    # "manual" starts a hand-traded session with no strategy behind it.
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


class OrderRequest(BaseModel):
    """A hand order on a paper session."""

    action: str                       # "long" | "short" | "close"
    # Share of equity to stake, 0-1. Omitted means the session's own size.
    size_pct: float | None = Field(default=None, gt=0, le=1)
    # Exit levels as prices, both optional. The engine refuses a level on the
    # wrong side of the fill rather than accepting one that fires immediately.
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)


class ExitsRequest(BaseModel):
    """Move or clear the exit levels on an open position."""

    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)


@router.get("")
def list_sessions() -> dict:
    """Every paper session, running or stopped."""
    return {"sessions": manager.list()}


@router.get("/{session_id}")
def get_session(session_id: str) -> dict:
    try:
        return manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/start")
async def start(request: StartRequest) -> dict:
    symbol = request.symbol or settings.chart.default_symbol
    timeframe = request.timeframe or settings.chart.default_timeframe

    try:
        session = await manager.start(
            request.strategy_id, symbol, timeframe,
            request.params, request.execution.to_config(),
        )
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("could not start a paper session")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    return session.snapshot()


@router.post("/{session_id}/order")
async def order(session_id: str, request: OrderRequest) -> dict:
    """Buy, sell or close by hand, filled at the live price."""
    try:
        return await manager.order(
            session_id, request.action, request.size_pct,
            request.stop_loss, request.take_profit,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OrderRefused as exc:
        # Refusals here are things a person can act on — the session is
        # stopped, there is no position to close — so they travel as a stable
        # code plus both languages, never as a sentence to be pattern-matched.
        raise HTTPException(422, detail=exc.as_dict()) from exc


@router.post("/{session_id}/exits")
async def exits(session_id: str, request: ExitsRequest) -> dict:
    """Attach, move or clear the stop and target on an open position."""
    try:
        return await manager.set_exits(session_id, request.stop_loss, request.take_profit)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OrderRefused as exc:
        raise HTTPException(422, detail=exc.as_dict()) from exc


@router.post("/{session_id}/resume-strategy")
async def resume_strategy(session_id: str) -> dict:
    """Hand the position back to the strategy after a manual intervention."""
    try:
        session = await manager.resume_strategy(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OrderRefused as exc:
        raise HTTPException(422, detail=exc.as_dict()) from exc
    return session.snapshot()


@router.post("/{session_id}/stop")
async def stop(session_id: str) -> dict:
    try:
        session = await manager.stop(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return session.snapshot()


@router.post("/{session_id}/resume")
async def resume(session_id: str) -> dict:
    try:
        session = await manager.resume(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return session.snapshot()


@router.delete("/{session_id}")
async def delete(session_id: str) -> dict:
    try:
        await manager.delete(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": session_id}
