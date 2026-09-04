"""Statistical analysis endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.analysis import stats
from backend.api.routes_strategy import ExecutionSettings, _load_candles
from backend.strategy import registry
from backend.strategy.base import StrategyError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stats", tags=["stats"])


class SeriesRequest(BaseModel):
    symbol: str | None = None
    timeframe: str | None = None
    limit: int | None = None


class StrategyStatsRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    limit: int | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


@router.post("/series")
def series(request: SeriesRequest) -> dict:
    """Distribution and randomness tests on the price series itself."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit)
    try:
        result = stats.analyse_series(df)
    except Exception as exc:
        log.exception("series analysis failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    result["symbol"] = request.symbol
    result["timeframe"] = timeframe
    return result


@router.post("/strategy")
def strategy(request: StrategyStatsRequest) -> dict:
    """Inference and Bayesian tests on one strategy's trades."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit)
    config = request.execution.to_config()

    try:
        backtest = registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, config
        )
        result = stats.analyse_strategy(backtest["trades"], config.initial_capital)
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("strategy analysis failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    result["strategy_id"] = request.strategy_id
    result["metrics"] = backtest["metrics"]
    return result
