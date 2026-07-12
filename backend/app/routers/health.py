from __future__ import annotations

from fastapi import APIRouter

from app.database import async_session_factory
from app.schemas import Message

router = APIRouter()


@router.get("/health", response_model=Message)
async def health_check() -> dict:
    """Liveness probe — also verifies DB connectivity."""
    db_ok = False
    try:
        async with async_session_factory() as session:
            await session.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
            db_ok = True
        status = "ok"
    except Exception:
        status = "degraded"

    return {
        "message": status,
        "database": "connected" if db_ok else "disconnected",
    }
