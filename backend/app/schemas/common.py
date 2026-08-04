"""Response schemas mirroring the frontend's Zod contract in
`quantpercent/lib/api/types.ts`. Field names and enum values must match
exactly — `scripts/check-api.ts` validates every endpoint against them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SourceStatus(StrEnum):
    ok = "ok"
    delayed = "delayed"
    unavailable = "unavailable"


class Regime(StrEnum):
    bullish = "bullish"
    bullish_transition = "bullish_transition"
    bearish = "bearish"
    bearish_transition = "bearish_transition"
    sideways = "sideways"
    turbulent = "turbulent"


class RiskState(StrEnum):
    low = "low"
    moderate = "moderate"
    elevated = "elevated"
    high = "high"


class PublicSignal(StrEnum):
    bullish = "bullish"
    neutral = "neutral"
    defensive = "defensive"
    high_risk = "high_risk"
    low_conviction = "low_conviction"


class ModelStatus(StrEnum):
    active = "active"
    paper_trading = "paper_trading"
    experimental = "experimental"
    archived = "archived"


class ResultType(StrEnum):
    backtest = "backtest"
    out_of_sample = "out_of_sample"
    walk_forward = "walk_forward"
    paper_trading = "paper_trading"
    live = "live"


class Freshness(ApiModel):
    data_as_of: datetime
    generated_at: datetime
    source_status: SourceStatus
    is_stale: bool
    delay_minutes: int
