"""Strategy catalog, backtest and optimisation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.data import market_vn, sources
from backend.data.binance import to_ms
from backend.optimizer.grid import (
    DEFAULT_SAMPLES,
    MAX_COMBINATIONS,
    MAX_SAMPLES,
    RANKABLE_METRICS,
    ParamRange,
    grid_size,
    optimize,
)
from typing import Literal

from backend.i18n import bi
from backend.strategy import multi, registry
from backend.strategy.base import StrategyError
from backend.strategy.engine import BacktestConfig
from backend.strategy.position_model import ContractConfig, execution_model_for, is_index_future

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ContractSettings(BaseModel):
    """Index-futures sizing and costs, applied only to VN30F/VN100F symbols.

    The margin rate, the forced-close threshold and the fee have no defaults:
    they are set by the exchange and the broker, and a guessed value would put
    an invented cost on the account.
    """

    sizing: Literal["margin", "fixed"] = "margin"
    contracts: int = Field(default=1, ge=1, le=10_000)
    multiplier: float = Field(default=100_000.0, gt=0)
    initial_margin_rate: float | None = Field(default=None, gt=0, le=1)
    maintenance_threshold: float | None = Field(default=None, ge=0, lt=1)
    fee_mode: Literal["per_contract", "notional"] = "per_contract"
    fee_per_contract: float | None = Field(default=None, ge=0)
    fee_rate: float | None = Field(default=None, ge=0, le=0.01)
    slippage_points: float = Field(default=0.0, ge=0)

    def missing(self) -> list[str]:
        names = []
        if self.initial_margin_rate is None:
            names.append("initial_margin_rate")
        if self.maintenance_threshold is None:
            names.append("maintenance_threshold")
        fee_field = "fee_per_contract" if self.fee_mode == "per_contract" else "fee_rate"
        if getattr(self, fee_field) is None:
            names.append(fee_field)
        return names


class ContractSettingsRequired(Exception):
    """A futures symbol whose contract block leaves a required value empty."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        fields = ", ".join(missing)
        self.detail = {
            "code": "contract_settings_required",
            "missing": missing,
            "message": bi(
                f"Thiếu thông số hợp đồng: {fields}.",
                f"Missing contract settings: {fields}.",
            ),
        }


class ExecutionSettings(BaseModel):
    """Costs and sizing. Defaults match Binance futures taker fees."""

    initial_capital: float = Field(default=10_000.0, gt=0)
    size_pct: float = Field(default=1.0, gt=0, le=1.0)
    leverage: float = Field(default=1.0, ge=1.0, le=125.0)
    fee: float = Field(default=0.0004, ge=0, le=0.01)
    slippage: float = Field(default=0.0002, ge=0, le=0.01)
    contract: ContractSettings | None = None

    def to_config(self, symbol: str | None = None) -> BacktestConfig:
        """The engine config for ``symbol``.

        The contract block applies only to an index future; with any other
        symbol it is ignored. Raises ContractSettingsRequired when it applies
        but leaves a required value empty.
        """
        contract = None
        if self.contract is not None and is_index_future(symbol or settings.chart.default_symbol):
            missing = self.contract.missing()
            if missing:
                raise ContractSettingsRequired(missing)
            c = self.contract
            contract = ContractConfig(
                initial_margin_rate=c.initial_margin_rate,
                maintenance_threshold=c.maintenance_threshold,
                sizing=c.sizing,
                contracts=c.contracts,
                multiplier=c.multiplier,
                fee_mode=c.fee_mode,
                fee_per_contract=c.fee_per_contract or 0.0,
                fee_rate=c.fee_rate or 0.0,
                slippage_points=c.slippage_points,
            )
        return BacktestConfig(
            initial_capital=self.initial_capital,
            size_pct=self.size_pct,
            leverage=self.leverage,
            fee=self.fee,
            slippage=self.slippage,
            contract=contract,
        )


def config_for(execution: ExecutionSettings, symbol: str | None) -> BacktestConfig:
    """`to_config`, with a missing contract setting turned into HTTP 422.

    Call it before an endpoint's try block: a broad `except Exception` there
    would report the 422 as a 500.
    """
    try:
        return execution.to_config(symbol)
    except ContractSettingsRequired as exc:
        raise HTTPException(422, detail=exc.detail) from exc


class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    limit: int | None = None
    # Inclusive ISO instants. Omitted means "the most recent `limit` bars".
    start: str | None = None
    end: str | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


@router.post("/report")
def report(request: BacktestRequest) -> dict:
    """The full AmiBroker-style report for one backtest.

    Separate from ``/backtest`` because it is an order of magnitude more data —
    monthly tables, per-trade excursions, chart series — and the results panel
    refreshes on every parameter change. Paying that cost only when the report
    window is actually opened keeps the panel responsive.
    """
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit,
                                  request.start, request.end)
    config = config_for(request.execution, request.symbol)

    try:
        spec, resolved, result, probability = registry.simulate(
            request.strategy_id, df, timeframe, request.params, config
        )
        # Imported on first use, not at start-up. backend.analysis.report pulls
        # scipy.stats, measured at 557 ms of the 1 244 ms the app took to
        # import; a report is requested at most a few times per session, so the
        # cost belongs there rather than in every server start.
        from backend.analysis.report import build_report

        payload = build_report(result, df, timeframe, probability=probability)
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("report failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    payload["strategy_id"] = spec.id
    payload["strategy_name"] = spec.name
    payload["params"] = resolved
    payload["symbol"] = request.symbol
    payload["execution_model"] = execution_model_for(
        request.symbol or settings.chart.default_symbol, config)
    return payload


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
    # Inclusive ISO instants. Omitted means "the most recent `limit` bars".
    start: str | None = None
    end: str | None = None
    metric: str = "sharpe"
    top_n: int = Field(default=50, ge=1, le=500)
    mode: str = "grid"
    samples: int = Field(default=DEFAULT_SAMPLES, ge=1, le=MAX_SAMPLES)
    seed: int | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)


class SizeRequest(BaseModel):
    ranges: list[SweepRange]
    bars: int = 2000


def _load_candles(
    symbol: str | None,
    timeframe: str | None,
    limit: int | None,
    start: str | None = None,
    end: str | None = None,
):
    """Candles for a run, optionally restricted to a date window.

    `start` and `end` are ISO instants, inclusive. Testing a strategy over a
    named period is the difference between "it worked on the last 2 000 bars"
    and "it worked through 2022" — one of those is a claim about a strategy and
    the other is a claim about whatever the data happened to end on.

    `limit` still applies inside the window and still counts backwards from the
    newest bar in it, so a window plus a limit means "the last N bars of that
    period" rather than the first N.
    """
    symbol = symbol or settings.chart.default_symbol
    timeframe = timeframe or settings.chart.default_timeframe
    limit = min(limit or settings.chart.max_candles, settings.chart.max_candles)

    try:
        start_ms = to_ms(start) if start else None
        end_ms = to_ms(end) if end else None
    except ValueError as exc:
        raise HTTPException(400, f"Ngày không hợp lệ: {exc}") from exc
    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise HTTPException(400, "Ngày bắt đầu nằm sau ngày kết thúc.")

    try:
        df = sources.get_candles(symbol, timeframe, start_ms, end_ms, limit)
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    if df.empty:
        window = ""
        if start or end:
            window = f" trong khoảng {start or '…'} → {end or '…'}"
        raise HTTPException(404, f"Không có nến cho {symbol} {timeframe}{window}")
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
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit,
                                  request.start, request.end)

    config = config_for(request.execution, request.symbol)
    try:
        result = registry.run_strategy(
            request.strategy_id, df, timeframe, request.params, config
        )
        result["execution_model"] = execution_model_for(
            request.symbol or settings.chart.default_symbol, config)
        return result
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception("backtest failed for %s", request.strategy_id)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


class MultiMarketRequest(BaseModel):
    """One strategy, one timeframe, many symbols."""

    strategy_id: str
    symbols: list[str]
    timeframe: str | None = None
    params: dict = Field(default_factory=dict)
    limit: int | None = None
    start: str | None = None
    end: str | None = None
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    # Which column decides "best". Only affects ranking; every row carries the
    # full metric set regardless.
    metric: str = "sharpe"


# Scanning more than this in one request is a different kind of job — it would
# hold a worker for minutes and the table stops being readable well before the
# limit bites.
MAX_MARKETS = 25


@router.post("/backtest/markets")
def backtest_markets(request: MultiMarketRequest) -> dict:
    """Run one strategy across several markets and rank the outcomes.

    Deliberately not a loop the frontend could run itself: doing it here is
    what makes the result honest. Twenty markets is twenty trials, so the best
    Sharpe gets deflated by the dispersion measured across them, and the
    summary leads with how many markets worked rather than with the winner.
    See backend/strategy/multi.py.
    """
    symbols = [s.strip() for s in request.symbols if s and s.strip()]
    # Same symbol twice would count as two trials and deflate the winner by a
    # search that never happened.
    seen: set[str] = set()
    symbols = [s for s in symbols if not (s in seen or seen.add(s))]

    if not symbols:
        raise HTTPException(400, "Chưa chọn thị trường nào.")
    if len(symbols) > MAX_MARKETS:
        raise HTTPException(
            400, f"Tối đa {MAX_MARKETS} thị trường một lần (đã chọn {len(symbols)})."
        )
    if request.metric not in RANKABLE_METRICS:
        raise HTTPException(
            400,
            f"Chỉ số `{request.metric}` không xếp hạng được. "
            f"Dùng một trong: {', '.join(sorted(RANKABLE_METRICS))}.",
        )

    runs: list[multi.MarketRun] = []
    for symbol in symbols:
        # One market failing is normal — a VN symbol with the VPN down, a
        # series with no bars in the window — and must not take the rest of
        # the scan with it. The reason travels with the row instead.
        try:
            df, timeframe = _load_candles(
                symbol, request.timeframe, request.limit, request.start, request.end
            )
        except HTTPException as exc:
            runs.append(multi.MarketRun(symbol, request.timeframe or "?",
                                        error=str(exc.detail)))
            continue

        try:
            config = request.execution.to_config(symbol)
        except ContractSettingsRequired as exc:
            # Only this market lacks what it needs; the rest of the scan runs.
            runs.append(multi.MarketRun(symbol, timeframe, error=exc.detail["message"]))
            continue

        try:
            result = registry.run_strategy(
                request.strategy_id, df, timeframe, request.params, config,
            )
            result["execution_model"] = execution_model_for(symbol, config)
        except StrategyError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            log.exception("multi-market backtest failed on %s", symbol)
            runs.append(multi.MarketRun(symbol, timeframe,
                                        error=f"{type(exc).__name__}: {exc}"))
            continue

        runs.append(multi.MarketRun(symbol, timeframe, result=result))

    payload = multi.summarise(runs, request.metric)
    payload["strategy_id"] = request.strategy_id
    payload["params"] = request.params
    return payload


@router.post("/optimize")
def run_optimize(request: OptimizeRequest) -> dict:
    """Sweep parameter ranges and rank the outcomes."""
    df, timeframe = _load_candles(request.symbol, request.timeframe, request.limit,
                                  request.start, request.end)

    if not request.ranges:
        raise HTTPException(400, "choose at least one parameter to sweep")

    ranges = [ParamRange(r.name, r.start, r.stop, r.step) for r in request.ranges]
    config = config_for(request.execution, request.symbol)

    try:
        return optimize(
            request.strategy_id,
            df,
            timeframe,
            ranges,
            config=config,
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
