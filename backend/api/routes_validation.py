"""Walk-forward validation, Monte Carlo, and side-by-side comparison."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.routes_strategy import ExecutionSettings, SweepRange, _load_candles, config_for
from backend.config import settings
from backend.optimizer.grid import ParamRange
from backend.optimizer.validation import (
    DEFAULT_SIMULATIONS,
    MAX_SIMULATIONS,
    monte_carlo,
    walk_forward,
)
from backend.strategy import registry
from backend.strategy.base import StrategyError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/validate", tags=["validation"])


class WalkForwardRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    ranges: list[SweepRange] = Field(default_factory=list)
    limit: int | None = None
    # Inclusive ISO instants. Omitted means "the most recent `limit` bars".
    start: str | None = None
    end: str | None = None
    metric: str = "sharpe"
    train_bars: int = Field(default=1000, ge=50, le=100_000)
    test_bars: int = Field(default=250, ge=50, le=100_000)
    # Bars dropped between training and test. An indicator with a lookback of L
    # carries training information L bars into the test window; purging removes
    # the overlap instead of assuming it is negligible.
    purge_bars: int = Field(default=0, ge=0, le=10_000)
    # "rolling" slides a fixed window; "anchored" starts at bar zero and grows,
    # which is the harder test because the parameters must survive regimes
    # rather than track the latest one.
    fold_mode: str = "rolling"
    mode: str = "grid"
    samples: int = Field(default=200, ge=10, le=2000)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


class MonteCarloRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    limit: int | None = None
    # Inclusive ISO instants. Omitted means "the most recent `limit` bars".
    start: str | None = None
    end: str | None = None
    simulations: int = Field(default=DEFAULT_SIMULATIONS, ge=100, le=MAX_SIMULATIONS)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


class CompareEntry(BaseModel):
    strategy_id: str
    params: dict = Field(default_factory=dict)
    label: str | None = None


class CompareRequest(BaseModel):
    entries: list[CompareEntry]
    symbol: str | None = None
    timeframe: str | None = None
    limit: int | None = None
    # Inclusive ISO instants. Omitted means "the most recent `limit` bars".
    start: str | None = None
    end: str | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


@router.post("/walk-forward")
def run_walk_forward(request: WalkForwardRequest) -> dict:
    """Optimise on each window, score only the window that follows it."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit,
                                  request.start, request.end)
    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]
    config = config_for(request.execution, request.symbol)

    try:
        return walk_forward(
            request.strategy_id, df, timeframe, ranges,
            config=config,
            metric=request.metric,
            train_bars=request.train_bars,
            test_bars=request.test_bars,
            purge_bars=request.purge_bars,
            fold_mode=request.fold_mode,
            mode=request.mode,
            samples=request.samples,
        )
    except (ValueError, StrategyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("walk-forward failed for %s", request.strategy_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


@router.post("/monte-carlo")
def run_monte_carlo(request: MonteCarloRequest) -> dict:
    """Resample the trades of one backtest to show the range of outcomes."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit,
                                  request.start, request.end)
    config = config_for(request.execution, request.symbol)

    try:
        backtest = registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, config
        )
        result = monte_carlo(
            backtest["trades"], config.initial_capital, request.simulations
        )
    except (ValueError, StrategyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("monte carlo failed for %s", request.strategy_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    # The realised path is shown against the distribution: seeing where the
    # single history sits among the alternatives is the point.
    result["actual_return_pct"] = backtest["metrics"]["total_return_pct"]
    result["actual_max_drawdown_pct"] = backtest["metrics"]["max_drawdown_pct"]
    result["strategy_id"] = request.strategy_id
    return result


@router.post("/compare")
def compare(request: CompareRequest) -> dict:
    """Run several strategies over identical data and line the results up.

    Same candles, same costs, same window for every entry — otherwise the
    comparison measures the setup rather than the strategies.
    """
    if not request.entries:
        raise HTTPException(400, "Chọn ít nhất một chiến lược để so sánh.")
    if len(request.entries) > 8:
        raise HTTPException(422, "So sánh tối đa 8 chiến lược một lần.")

    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit,
                                  request.start, request.end)
    config = config_for(request.execution, request.symbol)

    rows, failures = [], []
    for entry in request.entries:
        try:
            result = registry.run_strategy(
                entry.strategy_id, df, timeframe, entry.params, config
            )
        except Exception as exc:
            failures.append({
                "strategy_id": entry.strategy_id,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        m = result["metrics"]
        rows.append({
            "strategy_id": entry.strategy_id,
            "label": entry.label or result["name"],
            "params": result["params"],
            "metrics": m,
            "equity": result["equity"],
            "times": result["times"],
            "trades": result["trades"],
        })

    if not rows:
        raise HTTPException(422, f"Không chiến lược nào chạy được: {failures}")

    benchmark = rows[0]["metrics"]["buy_hold_return_pct"]
    best = max(rows, key=lambda r: r["metrics"]["total_return_pct"])

    return {
        "symbol": request.symbol or settings.chart.default_symbol,
        "timeframe": timeframe,
        "bars": len(df),
        "config": config.as_dict(),
        "buy_hold_return_pct": benchmark,
        "best_strategy_id": best["strategy_id"],
        "beat_buy_hold": [
            r["strategy_id"] for r in rows
            if r["metrics"]["total_return_pct"] > benchmark
        ],
        "results": rows,
        "failures": failures,
    }
