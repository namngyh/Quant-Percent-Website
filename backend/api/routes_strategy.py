"""Strategy catalog, backtest and optimisation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.data import market_vn, sources
from backend.optimizer.grid import (
    DEFAULT_SAMPLES,
    MAX_COMBINATIONS,
    MAX_SAMPLES,
    RANKABLE_METRICS,
    ParamRange,
    grid_size,
    optimize,
)
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
    mode: str = "grid"
    samples: int = Field(default=DEFAULT_SAMPLES, ge=1, le=MAX_SAMPLES)
    seed: int | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


class SizeRequest(BaseModel):
    ranges: list[SweepRange]
    bars: int = 2000


def _load_candles(symbol: str | None, timeframe: str | None, limit: int | None):
    symbol = symbol or settings.chart.default_symbol
    timeframe = timeframe or settings.chart.default_timeframe
    limit = min(limit or settings.chart.max_candles, settings.chart.max_candles)

    try:
        df = sources.get_candles(symbol, timeframe, limit=limit)
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    if df.empty:
        raise HTTPException(404, f"Không có nến cho {symbol} {timeframe}")
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
        "max_combinations": MAX_COMBINATIONS,
        "max_samples": MAX_SAMPLES,
        "default_samples": DEFAULT_SAMPLES,
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
            mode=request.mode,
            samples=request.samples,
            seed=request.seed,
        )
    except (ValueError, StrategyError) as exc:
        # Grid too large, bad step, unknown metric, unknown strategy — all
        # things the user can fix from the form.
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("optimize failed for %s", request.strategy_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


# Rough per-combination cost, measured on this machine: ~10 ms over 2 000
# candles and ~37 ms over 20 000. Linear in bar count is close enough for a
# "this will take about a minute" hint.
MS_PER_COMBO_PER_1K_BARS = 5.0


@router.post("/optimize/size")
def optimize_size(request: SizeRequest) -> dict:
    """How big a sweep would be, so the UI can say so before it is launched."""
    try:
        ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]
        total = grid_size(ranges) if ranges else 0
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    per_combo_ms = MS_PER_COMBO_PER_1K_BARS * max(request.bars, 1) / 1000.0
    return {
        "combinations": total,
        "estimated_seconds": round(total * per_combo_ms / 1000.0, 1),
        "max_combinations": MAX_COMBINATIONS,
        "exceeds_limit": total > MAX_COMBINATIONS,
        "per_axis": [
            {"name": r.name, "values": len(r.values())} for r in ranges
        ],
    }
