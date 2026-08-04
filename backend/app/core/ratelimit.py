from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.redis import get_redis

log = logging.getLogger(__name__)

# Fallback used when Redis is unavailable, so a Redis outage cannot turn
# into an open door on the login endpoint.
_local_hits: dict[str, list[float]] = {}


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


# Contracts the frontend already expects (429 handled in its forms)
LOGIN = RateLimit(5, 15 * 60)
REGISTER = RateLimit(3, 60 * 60)
PASSWORD_RESET = RateLimit(3, 60 * 60)
CONTACT = RateLimit(5, 10 * 60)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _hit_local(key: str, rule: RateLimit) -> bool:
    now = time.time()
    hits = [t for t in _local_hits.get(key, []) if now - t < rule.window_seconds]
    if len(hits) >= rule.limit:
        _local_hits[key] = hits
        return False
    hits.append(now)
    _local_hits[key] = hits
    if len(_local_hits) > 10_000:
        _local_hits.clear()
    return True


async def check_rate_limit(key: str, rule: RateLimit) -> bool:
    """Sliding window over Redis; returns False when the caller is over."""
    redis_key = f"rl:{key}"
    try:
        client = get_redis()
        now = time.time()
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - rule.window_seconds)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {f"{now}:{id(now)}": now})
        pipe.expire(redis_key, rule.window_seconds)
        _, count, _, _ = await pipe.execute()
        return int(count) < rule.limit
    except Exception as exc:  # pragma: no cover - depends on Redis being down
        log.warning("rate limit falling back to memory for %s: %s", key, exc)
        return await _hit_local(redis_key, rule)


async def enforce(key: str, rule: RateLimit) -> None:
    if not await check_rate_limit(key, rule):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited"},
        )
