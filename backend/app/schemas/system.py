from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import ApiModel


class ServiceStatus(ApiModel):
    id: str
    name: str
    status: Literal["operational", "degraded", "down"]


class SystemStatus(ApiModel):
    generated_at: datetime
    services: list[ServiceStatus]


class FeedFreshness(ApiModel):
    id: str
    symbol: str
    data_as_of: datetime
    is_stale: bool
    delay_minutes: int


class DataFreshnessReport(ApiModel):
    generated_at: datetime
    feeds: list[FeedFreshness]
