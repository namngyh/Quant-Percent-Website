from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import (
    ApiModel,
    Freshness,
    ModelStatus,
    Regime,
    RiskState,
)


class ForecastRecord(Freshness):
    """Public forecast record (spec §18).

    The forbidden fields — features, raw parameters, entry/exit logic,
    position size, internal signals — have no representation here at all,
    so they cannot leak by accident.
    """

    model_id: str
    model_name: str
    model_version: str
    symbol: str
    timeframe: str
    horizon: int
    horizon_unit: Literal["trading_days"] = "trading_days"
    forecast_value: float
    forecast_return: float
    probability_up: float
    probability_down: float
    volatility: float
    interval_level: float
    interval_lower: float
    interval_upper: float
    # A model that forecasts a distribution and makes no regime call leaves
    # these null rather than having the loader invent one.
    regime: Regime | None = None
    regime_probability: float | None = None
    risk_score: int | None = None
    risk_state: RiskState | None = None
    status: ModelStatus


class ForecastRecords(ApiModel):
    records: list[ForecastRecord]


class ForecastHistoryPoint(ApiModel):
    forecast_at: str
    horizon: int
    predicted: float
    interval_lower: float
    interval_upper: float
    actual: float
    error_percent: float
    in_interval: bool


class ForecastHistory(Freshness):
    model_id: str
    symbol: str
    interval_level: float
    coverage: float
    points: list[ForecastHistoryPoint]


class ModelSummary(ApiModel):
    slug: str
    name: str
    code: str
    markets: list[str]
    category: str
    status: ModelStatus
    version: str
    horizons: list[int]
    # Whether this visitor may open the model's output
    access: Literal["public", "members"]
    locked: bool
    featured: bool
    tagline: dict
    key_output: dict
    sparkline: list[float] | None = None
    sparkline_label: dict | None = None
    # When the catalogue entry for this model was last revised. It says
    # nothing about whether the model has run.
    updated_at: datetime
    # The timestamp of this model's most recent published output, or None when
    # it has never produced any. Kept separate from `updated_at` because the
    # card used to show that field under an "Updated" label, which read as a
    # run date on eleven models that have never run.
    last_output_at: datetime | None = None


class ModelList(Freshness):
    models: list[ModelSummary]


class ModelDetail(ModelSummary):
    show_forecast: bool
    show_performance: bool
    description: dict
    architecture: list | None
    research_profile: dict | None = None


class ModelStatusRow(ApiModel):
    model_id: str
    status: ModelStatus
    last_run_at: datetime | None
    healthy: bool


class ModelStatusReport(ApiModel):
    generated_at: datetime
    models: list[ModelStatusRow]
