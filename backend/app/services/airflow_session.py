from __future__ import annotations

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException

from app.config import settings
from app.models.airflow_instance import AirflowInstance


class AirflowSessionManager:
    """Manages Airflow session cookies with Redis caching (55min TTL)."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def get_session(self, instance: AirflowInstance, account_key: str) -> str:
        """Get session cookie — from Redis cache or fresh login."""
        cache_key = f"airflow_session:{instance.id}:{account_key}"
        r = await self._get_redis()
        cached = await r.get(cache_key)
        if cached:
            return cached

        # Map account_key to actual credentials
        if account_key == "admin":
            username = instance.admin_user
            password = instance.admin_password_encrypted
        elif account_key == "dev":
            username = instance.dev_user
            password = instance.dev_password_encrypted
        else:
            username = instance.viewer_user
            password = instance.viewer_password_encrypted

        if not password:
            raise HTTPException(status_code=500, detail="Airflow credentials not configured")

        # Login via Airflow REST API
        async with httpx.AsyncClient() as client:
            login_resp = await client.post(
                f"{instance.internal_url}/api/v1/login/",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if login_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to authenticate with Airflow")

            session_cookie = login_resp.cookies.get("session")
            if not session_cookie:
                for cookie in login_resp.cookies.jar:
                    if cookie.name == "session":
                        session_cookie = cookie.value
                        break

            if session_cookie:
                await r.setex(cache_key, 3300, session_cookie)  # 55 min TTL

            return session_cookie or ""