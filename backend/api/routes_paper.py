"""Paper-trading endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.routes_strategy import ExecutionSettings
from backend.config import settings
from backend.paper.manager import manager
from backend.strategy.base import StrategyError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paper", tags=["paper"])


class StartRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


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
