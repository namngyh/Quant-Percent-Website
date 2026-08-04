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
    quotes: list[Quote]
    regime: Regime
    regime_probability: float
    probability_up: float
    probability_down: float
    volatility: float
    risk_state: RiskState
    risk_score: int
    model_consensus: float
    public_signal: PublicSignal


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
