"""Background jobs.

Runs as its own container with a single replica so the jobs cannot
double-fire across API workers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, text

from app.core.logging import configure_logging
from app.core.redis import cache_delete_prefix, close_redis
from app.db.models import OneTimeToken, RefreshToken
from app.db.session import SessionLocal, engine

configure_logging()
log = logging.getLogger("worker")


async def purge_expired_tokens() -> None:
    """Expired credentials are dead weight and a liability if leaked."""
    cutoff = datetime.now(UTC) - timedelta(days=7)
    async with SessionLocal() as session:
        refresh = await session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        )
        one_time = await session.execute(
            delete(OneTimeToken).where(OneTimeToken.expires_at < cutoff)
        )
        await session.commit()
    log.info(
        "purged tokens: %s refresh, %s one-time",
        refresh.rowcount,
        one_time.rowcount,
    )


async def refresh_market_cache() -> None:
    """Drop cached market payloads so the next request re-reads the DB."""
    await cache_delete_prefix("market:")


async def check_feed_health() -> None:
    """Log when a feed stops updating during the trading session, so a
    stalled pipeline is visible without waiting for a user to notice."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT symbol, data_as_of FROM api.v_data_freshness"
                )
            )
        ).mappings().all()
    now = datetime.now(UTC)
    for row in rows:
        age = now - row["data_as_of"]
        if age > timedelta(hours=2):
            log.warning(
                "feed %s has not updated for %s", row["symbol"], age
            )


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(purge_expired_tokens, "cron", hour=3, minute=15)
    scheduler.add_job(refresh_market_cache, "interval", seconds=30)
    scheduler.add_job(check_feed_health, "interval", minutes=10)
    return scheduler


async def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    log.info("worker started with %s jobs", len(scheduler.get_jobs()))
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)
        await engine.dispose()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
