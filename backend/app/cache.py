from __future__ import annotations

from collections.abc import AsyncIterator

import redis.asyncio as aioredis

from app.config import settings


async def get_redis() -> AsyncIterator[aioredis.Redis]:
    """Yield a request-scoped Redis client and always close its connection pool."""

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()