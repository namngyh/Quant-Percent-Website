from __future__ import annotations

from datetime import date

from app.schemas.common import (
    ApiModel,
    Freshness,
    PublicSignal,
    Regime,
    RiskState,
)


class Quote(Freshness):
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    volume: int
    currency: str


class OhlcvBar(ApiModel):
    time: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class History(Freshness):
    symbol: str
    timeframe: str
    bars: list[OhlcvBar]


class MarketOverview(Freshness):
    """Index quotes plus the model's read on the market.

    Quotes come from the ingestion feed and are always present. Everything
    below them is produced by the model pipeline and is null until a run has
    written to quant.market_state — a missing regime must read as missing,
    never as a neutral-looking default (spec: a metric the run did not
    produce serialises as null, never 0).
    """

    quotes: list[Quote]
    regime: Regime | None = None
    regime_probability: float | None = None
    probability_up: float | None = None
    probability_down: float | None = None
    volatility: float | None = None
    risk_state: RiskState | None = None
    risk_score: int | None = None
    model_consensus: float | None = None
    public_signal: PublicSignal | None = None


class StockRow(ApiModel):
    ticker: str
    price: float
    change_percent: float
    regime: Regime
    probability_up: float
    volatility: float
    risk_state: RiskState
    rank: int


class Constituents(Freshness):
    rows: list[StockRow]


class McBucket(ApiModel):
    bucket: float
    probability: float


class StressScenario(ApiModel):
    id: str
    impact_percent: float


class RiskDashboard(Freshness):
    current_drawdown: float
    rolling_drawdown_60d: float
    volatility: float
    var_95: float | None
    es_95: float | None
    downside_probability: float
    risk_state: RiskState
    mc_drawdown_distribution: list[McBucket]
    mc_paths: int
    stress_scenarios: list[StressScenario]


class TradableSymbol(ApiModel):
    """A stock the portfolio tools can price, with the depth of its history."""

    symbol: str
    name: str
    exchange: str
    sector: str | None
    sessions: int


class TradableSymbols(Freshness):
    rows: list[TradableSymbol]
