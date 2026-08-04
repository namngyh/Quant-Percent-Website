from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.schemas.common import Freshness, SourceStatus


def build_freshness(
    data_as_of: datetime | None,
    generated_at: datetime | None = None,
    *,
    delay_minutes: int | None = None,
    stale_after_minutes: int | None = None,
) -> Freshness:
    """Every public payload carries provenance (spec §20).

    Staleness is derived from the data timestamp rather than declared, so
    a stalled feed cannot be presented as live.
    """
    now = datetime.now(UTC)
    if data_as_of is None:
        return Freshness(
            data_as_of=now,
            generated_at=generated_at or now,
            source_status=SourceStatus.unavailable,
            is_stale=True,
            delay_minutes=0,
        )

    if data_as_of.tzinfo is None:
        data_as_of = data_as_of.replace(tzinfo=UTC)

    threshold = timedelta(
        minutes=stale_after_minutes
        if stale_after_minutes is not None
        else settings.stale_after_minutes
    )
    age = now - data_as_of
    is_stale = age > threshold

    return Freshness(
        data_as_of=data_as_of,
        generated_at=generated_at or now,
        source_status=SourceStatus.delayed if is_stale else SourceStatus.ok,
        is_stale=is_stale,
        delay_minutes=(
            delay_minutes
            if delay_minutes is not None
            else settings.market_delay_minutes
        ),
    )
