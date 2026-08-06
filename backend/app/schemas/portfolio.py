"""Quant Portfolio request and response shapes.

Everything here is computed from price history the database already holds.
Nothing on this endpoint comes from a fitted model: the four research models
are published with the caveat that none has beaten a simple baseline, so
building a portfolio product on their forecasts would contradict what the
model pages say about them. Volatility, VaR, drawdown and risk contribution
are arithmetic on observed returns and stand on their own.

The optional forward-looking block is the one exception, and it is fed by the
VN-Index Monte-Carlo run that already backs /market/risk. It is scaled to the
portfolio by its estimated beta, which is stated on the response rather than
hidden, and the whole block is absent when that run is unavailable.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ApiModel, Freshness, RiskState


class Holding(BaseModel):
    """One position. `quantity` is in shares; `cost_basis` is per share."""

    symbol: str = Field(min_length=1, max_length=20)
    quantity: float = Field(gt=0)
    # Optional: a reader analysing a hypothetical portfolio has no cost basis,
    # and the spec calls for that case explicitly. Profit fields stay null.
    cost_basis: float | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class PortfolioRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=50)
    cash: float = Field(default=0.0, ge=0)
    # 21 / 63 / 126 / 252 sessions, the trading-day count behind the
    # 1-month, 3-month, 6-month and 1-year choices on the form.
    horizon_days: int = Field(default=63, ge=21, le=252)
    # How far back realised risk is measured. One year of sessions by
    # default; a shorter window reacts faster but estimates correlation
    # from fewer observations.
    lookback_days: int = Field(default=252, ge=60, le=1000)

    @model_validator(mode="after")
    def _unique_symbols(self) -> "PortfolioRequest":
        seen = [h.symbol for h in self.holdings]
        if len(seen) != len(set(seen)):
            raise ValueError("each symbol may appear only once")
        return self


class PositionRisk(ApiModel):
    """Per-holding valuation and its share of total portfolio risk."""

    symbol: str
    quantity: float
    price: float
    market_value: float
    weight: float
    cost_basis: float | None
    profit: float | None
    profit_percent: float | None
    volatility: float
    beta: float | None
    # Marginal contribution to risk times weight, normalised so the column
    # sums to 1. This is the number that shows a position carrying more risk
    # than its size suggests.
    risk_contribution: float
    sector: str | None
    observations: int


class Concentration(ApiModel):
    """How much of the portfolio depends on a small number of bets."""

    positions: int
    largest_weight: float
    top_three_weight: float
    herfindahl: float
    effective_assets: float
    # Effective assets after accounting for correlation, so ten names that
    # move together do not count as ten.
    effective_bets: float
    average_correlation: float
    max_pair_correlation: float | None
    max_pair: list[str] | None
    sector_weights: dict[str, float]


class DrawdownBucket(ApiModel):
    threshold: float
    probability: float


class ForwardRisk(ApiModel):
    """VN-Index Monte-Carlo distribution scaled to the portfolio by beta."""

    source_model: str
    forecast_origin: date
    horizon_days: int
    paths: int
    portfolio_beta: float
    var_95: float
    expected_shortfall_95: float
    drawdown_probabilities: list[DrawdownBucket]


class PortfolioAnalysis(Freshness):
    total_value: float
    invested_value: float
    cash: float
    cash_weight: float
    total_cost: float | None
    profit: float | None
    profit_percent: float | None

    # Realised risk, measured on the observed return series of this exact
    # basket over the window below.
    lookback_days: int
    observations: int
    volatility: float
    downside_deviation: float
    max_drawdown: float
    beta: float | None
    var_95: float
    expected_shortfall_95: float
    risk_state: RiskState

    positions: list[PositionRisk]
    concentration: Concentration
    forward: ForwardRisk | None
    # Symbols the caller asked for that have no usable price history. Reported
    # rather than silently dropped: a portfolio missing a position is not the
    # portfolio the reader entered.
    unpriced: list[str]
