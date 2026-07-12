from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.models.base import Base
from app.routers import health

app = FastAPI(
    title="Conductor API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS: allow the React dashboard + code-server iframe ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(health.router, prefix="/api/v1", tags=["health"])


@app.on_event("startup")
async def startup() -> None:
    """Create tables on startup (dev convenience — Alembic is the prod path)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.on_event("shutdown")
async def shutdown() -> None:
    await engine.dispose()
