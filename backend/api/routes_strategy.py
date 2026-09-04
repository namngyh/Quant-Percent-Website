"""Strategy catalog, backtest and optimisation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.data import store
from backend.optimizer.grid import RANKABLE_METRICS, ParamRange, optimize
from backend.strategy import registry
from backend.strategy.base import StrategyError
from backend.strategy.engine import BacktestConfig

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ExecutionSettings(BaseModel):
    """Costs and sizing. Defaults match Binance futures taker fees."""

    initial_capital: float = Field(default=10_000.0, gt=0)
    size_pct: float = Field(default=1.0, gt=0, le=1.0)
    leverage: float = Field(default=1.0, ge=1.0, le=125.0)
    fee: float = Field(default=0.0004, ge=0, le=0.01)
    slippage: float = Field(default=0.0002, ge=0, le=0.01)

    def to_config(self) -> BacktestConfig:
        return BacktestConfig(
            initial_capital=self.initial_capital,
            size_pct=self.size_pct,
            leverage=self.leverage,
            fee=self.fee,
            slippage=self.slippage,
        )


class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    limit: int | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


class SweepRange(BaseModel):
    name: str
    start: float
    stop: float
    step: float


class OptimizeRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    ranges: list[SweepRange]
    fixed_params: dict = Field(default_factory=dict)
    limit: int | None = None
    metric: str = "sharpe"
    top_n: int = Field(default=50, ge=1, le=500)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


def _load_candles(symbol: str | None, timeframe: str | None, limit: int | None):
    symbol = symbol or settings.chart.default_symbol
    timeframe = timeframe or settings.chart.default_timeframe
    limit = min(limit or settings.chart.max_candles, settings.chart.max_candles)

    df = store.get_candles(symbol, timeframe, limit=limit)
    if df.empty:
        raise HTTPException(404, f"no candles stored for {symbol} {timeframe}")
    return df, timeframe


# Sync handlers on purpose: blocking DuckDB and pandas work belongs in
# FastAPI's threadpool, not on the event loop. See routes_indicators.py.
@router.get("")
def catalog() -> dict:
    """Every strategy found, plus any file that failed to load."""
    specs = registry.get_registry()
    items = [spec.as_dict() for spec in specs.values()]
    items.sort(key=lambda s: s["name"])
    return {
        "count": len(items),
        "strategies": items,
        "load_errors": registry.get_load_errors(),
        "rankable_metrics": list(RANKABLE_METRICS),
    }


@router.post("/backtest")
def backtest(request: BacktestRequest) -> dict:
    """Run one strategy over a stored candle series."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit)

    try:
        return registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, request.execution.to_config()
        )
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("backtest failed for %s", request.strategy_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


@router.post("/optimize")
def run_optimize(request: OptimizeRequest) -> dict:
    """Sweep parameter ranges and rank the outcomes."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit)

    if not request.ranges:
        raise HTTPException(400, "choose at least one parameter to sweep")

    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]

    try:
        return optimize(
            request.strategy_id,
            df,
            timeframe,
            ranges,
            config=request.execution.to_config(),
            metric=request.metric,
            top_n=request.top_n,
        )
    except (ValueError, StrategyError) as exc:
        # Grid too large, bad step, unknown metric, unknown strategy — all
        # things the user can fix from the form.
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("optimize failed for %s", request.strategy_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc
