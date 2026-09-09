"""Statistical analysis endpoints."""

from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.routes_strategy import ExecutionSettings, _load_candles
from backend.strategy import registry
from backend.strategy.base import StrategyError
from backend.strategy.metrics import BARS_PER_YEAR

log = logging.getLogger(__name__)
def _stats():
    """backend.analysis.stats, imported on first use rather than at start-up.

    It pulls scipy.stats and statsmodels, which measured 561 ms of the 1 244 ms
    the whole app took to import. Nothing in this module needs them until a
    request actually asks for a statistical test, and the server should be
    answering /api/health long before then.
    """
    from backend.analysis import stats
    return stats


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
    # How many parameter combinations were tried to arrive at these params.
    # This is the single most important number for honest inference: picking
    # the best of 2 000 sweeps and reporting its Sharpe as if it were the only
    # one ever tested is how a strategy with no edge ends up looking excellent.
    # The frontend passes the size of the last sweep; 1 means "typed by hand".
    n_trials: int = Field(default=1, ge=1, le=1_000_000)


@router.post("/series")
def series(request: SeriesRequest) -> dict:
    """Distribution and randomness tests on the price series itself."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit)
    try:
        result = _stats().analyse_series(df)
    except Exception as exc:
        log.exception("series analysis failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    result["symbol"] = request.symbol
    result["timeframe"] = timeframe
    return result


@router.post("/strategy")
def strategy(request: StrategyStatsRequest) -> dict:
    """Inference on one strategy's trades, and on its equity curve."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit)
    config = request.execution.to_config()

    try:
        backtest = registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, config
        )
        equity = np.asarray(backtest["equity"], dtype="float64")
        # Per-bar returns of the equity curve. The Sharpe tests need these
        # rather than per-trade returns: Sharpe is defined on a return series
        # sampled at a fixed frequency, and the trade sequence is not.
        with np.errstate(divide="ignore", invalid="ignore"):
            bar_returns = np.diff(equity) / np.where(equity[:-1] > 0, equity[:-1], np.nan)
        bar_returns = bar_returns[np.isfinite(bar_returns)]

        result = _stats().analyse_strategy(
            backtest["trades"],
            config.initial_capital,
            bar_returns=bar_returns,
            periods_per_year=BARS_PER_YEAR.get(timeframe, 365.0),
            n_trials=request.n_trials,
        )
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("strategy analysis failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    result["strategy_id"] = request.strategy_id
    result["timeframe"] = timeframe
    result["metrics"] = backtest["metrics"]
    return result
