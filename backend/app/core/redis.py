from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings

log = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def cache_get(key: str) -> Any | None:
    """Cache reads never break a request: a Redis outage degrades to a
    cache miss, not a 500."""
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # pragma: no cover - depends on Redis being down
        log.warning("cache get failed for %s: %s", key, exc)
        return None
    return json.loads(raw) if raw else None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception as exc:  # pragma: no cover
        log.warning("cache set failed for %s: %s", key, exc)


async def cache_delete_prefix(prefix: str) -> None:
    try:
        client = get_redis()
        async for key in client.scan_iter(match=f"{prefix}*", count=200):
            await client.delete(key)
    except Exception as exc:  # pragma: no cover
        log.warning("cache purge failed for %s: %s", prefix, exc)
