"""Rate limiting must hold even when Redis is unavailable, otherwise a
Redis outage would open the login endpoint to brute force.
"""

import pytest

from app.core import ratelimit
from app.core.ratelimit import RateLimit, check_rate_limit, enforce


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_redis", boom)
    ratelimit._local_hits.clear()


async def test_limit_blocks_after_threshold() -> None:
    rule = RateLimit(limit=3, window_seconds=60)
    assert await check_rate_limit("k1", rule)
    assert await check_rate_limit("k1", rule)
    assert await check_rate_limit("k1", rule)
    assert not await check_rate_limit("k1", rule)


async def test_limits_are_per_key() -> None:
    rule = RateLimit(limit=1, window_seconds=60)
    assert await check_rate_limit("user-a", rule)
    assert await check_rate_limit("user-b", rule)
    assert not await check_rate_limit("user-a", rule)


async def test_enforce_raises_429() -> None:
    from fastapi import HTTPException

    rule = RateLimit(limit=1, window_seconds=60)
    await enforce("k2", rule)
    with pytest.raises(HTTPException) as exc:
        await enforce("k2", rule)
    # The frontend forms already handle exactly this status
    assert exc.value.status_code == 429
    assert exc.value.detail == {"error": "rate_limited"}


async def test_window_expiry_releases(monkeypatch) -> None:
    rule = RateLimit(limit=1, window_seconds=1)
    assert await check_rate_limit("k3", rule)
    assert not await check_rate_limit("k3", rule)

    real_time = ratelimit.time.time

    monkeypatch.setattr(ratelimit.time, "time", lambda: real_time() + 5)
    assert await check_rate_limit("k3", rule)
