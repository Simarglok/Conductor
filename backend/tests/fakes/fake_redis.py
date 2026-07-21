from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Value:
    value: str
    expires_at: float | None = None


class FakeRedis:
    """Deterministic async Redis subset with atomic operations for API tests."""

    def __init__(self, *, now: Callable[[], float] | None = None) -> None:
        self._now = now or (lambda: 0.0)
        self._values: dict[str, _Value] = {}
        self._lock = asyncio.Lock()
        self.closed = False
        self.fail = False
        self.fail_atomic = False

    def _ensure_available(self) -> None:
        if self.fail:
            raise ConnectionError("fake redis unavailable with secret-like-value")

    def _purge_expired(self, key: str) -> None:
        item = self._values.get(key)
        if item is not None and item.expires_at is not None and item.expires_at <= self._now():
            self._values.pop(key, None)

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> int:
        """Atomically emulate the rate-counter Lua script used by the API."""
        if numkeys != 1 or len(keys_and_args) != 2:
            raise ValueError("unsupported fake Redis EVAL shape")
        key = str(keys_and_args[0])
        seconds = int(str(keys_and_args[1]))
        async with self._lock:
            self._ensure_available()
            if self.fail_atomic:
                raise ConnectionError("fake atomic redis failure with secret-like-value")
            self._purge_expired(key)
            item = self._values.get(key)
            value = int(item.value) + 1 if item else 1
            expires_at = item.expires_at if item else self._now() + seconds
            self._values[key] = _Value(str(value), expires_at)
            return value

    async def incr(self, key: str) -> int:
        async with self._lock:
            self._ensure_available()
            self._purge_expired(key)
            item = self._values.get(key)
            value = int(item.value) + 1 if item else 1
            expires_at = item.expires_at if item else None
            self._values[key] = _Value(str(value), expires_at)
            return value

    async def expire(self, key: str, seconds: int) -> bool:
        async with self._lock:
            self._ensure_available()
            self._purge_expired(key)
            item = self._values.get(key)
            if item is None:
                return False
            item.expires_at = self._now() + seconds
            return True

    async def ttl(self, key: str) -> int:
        async with self._lock:
            self._ensure_available()
            self._purge_expired(key)
            item = self._values.get(key)
            if item is None:
                return -2
            if item.expires_at is None:
                return -1
            return max(0, int(item.expires_at - self._now()))

    async def get(self, key: str) -> str | None:
        async with self._lock:
            self._ensure_available()
            self._purge_expired(key)
            item = self._values.get(key)
            return item.value if item else None

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        async with self._lock:
            self._ensure_available()
            self._values[key] = _Value(str(value), self._now() + seconds)
            return True

    async def delete(self, key: str) -> int:
        async with self._lock:
            self._ensure_available()
            self._purge_expired(key)
            return int(self._values.pop(key, None) is not None)

    async def aclose(self) -> None:
        self.closed = True
