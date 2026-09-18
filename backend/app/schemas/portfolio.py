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
from enum import StrEnum

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


class MarginInput(BaseModel):
    """The reader's margin loan, as they read it off their broker's app.

    Self-reported, like the holdings. The two thresholds are the broker's
    own; the defaults are the common Vietnamese figures — the regulator's
    minimum maintenance ratio is 30%, and brokers set their warning level
    above it — and the page says to check them rather than trust them.
    """

    debt: float = Field(gt=0)
    # Annual, as a fraction. 12%/year is the usual retail margin rate.
    rate: float = Field(default=0.12, ge=0, le=1)
    call_ratio: float = Field(default=0.30, gt=0, lt=1)
    force_ratio: float = Field(default=0.28, gt=0, lt=1)

    @model_validator(mode="after")
    def _force_below_call(self) -> MarginInput:
        if self.force_ratio >= self.call_ratio:
            raise ValueError("force_ratio must be below call_ratio")
        return self


class PortfolioRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=50)
    cash: float = Field(default=0.0, ge=0)
    # Absent when the reader is not borrowing; the response then carries no
    # margin block at all rather than one full of zeros.
    margin: MarginInput | None = None
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


class UnmeasuredPosition(ApiModel):
    """A holding with a price but too little history for any risk figure.

    It counts towards the portfolio's value and profit — the reader owns
    it — and towards nothing else. No weight, because weight pairs with
    risk contribution and that is undefined here; no volatility or beta,
    because a number from a few sessions would be noise with a label.
    """

    symbol: str
    quantity: float
    price: float
    market_value: float
    cost_basis: float | None
    profit: float | None
    profit_percent: float | None
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
    """VN-Index Monte-Carlo distribution mapped onto the portfolio.

    The run is a fixed-length simulation of the index. Two transformations
    bring it onto this book — beta, for how much of the index's move the
    holdings take, and square-root-of-time, for the horizon the reader picked.
    Both are reported here so the page can name them instead of presenting a
    stretched number as if it were simulated directly.

    `threshold` is a fall in this portfolio and is the same on every response;
    `probability` is what carries the portfolio and the horizon.
    """

    source_model: str
    forecast_origin: date
    horizon_days: int
    # The simulation's own length, and the factor the reader's horizon implies
    # against it. Stated so a 1-year answer cannot be mistaken for a 1-year
    # simulation.
    base_horizon_days: int
    horizon_scale: float
    paths: int
    portfolio_beta: float
    var_95: float
    expected_shortfall_95: float
    drawdown_probabilities: list[DrawdownBucket]


class MarginStatus(StrEnum):
    """Where the account sits against the broker's two thresholds.

    Only three states, and all three come from the ratios the reader typed.
    There is deliberately no "comfortable" or "danger" band above or below
    them: that would need a buffer this service made up.
    """

    above_call = "above_call"
    between = "between"
    below_force = "below_force"
    # Debt exceeds assets. Nothing below is meaningful and the page says so.
    negative_equity = "negative_equity"


class MarginDistance(ApiModel):
    """How far the stocks can fall before a threshold is hit.

    `drop` is a fraction of the stock value (cash does not fall), clamped at
    zero when the account is already past the threshold. `amount` is that
    fall in dong.
    """

    drop: float
    amount: float


class MarginHorizon(ApiModel):
    """The same loan, held for one of the four horizons the form offers.

    Two independent estimates of hitting the warning threshold sit side by
    side: the model's, from the VN-Index Monte-Carlo run scaled by beta and
    time, and the historical frequency of an index fall that deep over a
    window this long since 2000. Neither is null without the other, and
    both are null when the book has no beta to scale by.
    """

    horizon_days: int
    hit_call_probability: float | None
    historical_frequency: float | None
    historical_windows: int
    interest: float
    interest_pct_equity: float | None
    # What the stocks must return over the horizon just to pay the interest.
    breakeven_return: float | None


class MarginScenario(ApiModel):
    """The account after the stocks fall by `drop`, cash unchanged."""

    drop: float
    assets: float
    equity: float
    margin_ratio: float
    status: MarginStatus
    # Cash that would bring the ratio back to the warning threshold. Zero
    # when it is already above it.
    top_up: float


class MarginRisk(ApiModel):
    """The book seen from the reader's own money rather than from the stocks.

    `margin_ratio` is equity over assets, the simple form. Brokers compute
    it on collateral discounted per stock, which is always lower, so every
    distance here is optimistic and the page says so next to the number.
    """

    assets: float
    equity: float
    debt: float
    rate: float
    call_ratio: float
    force_ratio: float
    leverage: float | None
    margin_ratio: float
    status: MarginStatus
    distance_to_call: MarginDistance | None
    distance_to_force: MarginDistance | None
    # Interest paid each year on cash that is sitting next to the loan.
    idle_cash_cost_per_year: float | None
    # The portfolio's realised risk figures re-expressed on equity.
    equity_var_95: float | None
    equity_expected_shortfall_95: float | None
    equity_max_drawdown: float | None
    by_horizon: list[MarginHorizon]
    scenarios: list[MarginScenario]


class PortfolioAnalysis(Freshness):
    # Three sizes of the same book. `total_value` is everything including
    # cash; `invested_value` is every holding that has a price; and
    # `measured_value` is the part the risk figures below describe. A
    # percentage loss is turned into money against `measured_value`, not
    # `invested_value`: VaR measured on 900m of stock does not scale to the
    # extra 100m sitting in a recent listing it was never measured on.
    total_value: float
    invested_value: float
    measured_value: float
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
    # Present only when the request carried a margin loan.
    margin: MarginRisk | None
    # Holdings with a price but not enough sessions to measure: in the
    # totals above, absent from every risk figure.
    unmeasured: list[UnmeasuredPosition]
    # Symbols the caller asked for that have no price at all. Reported
    # rather than silently dropped: a portfolio missing a position is not the
    # portfolio the reader entered.
    unpriced: list[str]
