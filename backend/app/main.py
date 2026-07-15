from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.models.base import Base
from app.routers import admin, airflow_lifecycle, airflow_proxy, airflow_widgets, auth, codeserver, health, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (dev convenience — Alembic is the prod path)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Conductor API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS: allow the React dashboard + code-server iframe ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1", tags=["projects"])
app.include_router(airflow_lifecycle.router, prefix="/api/v1", tags=["airflow"])
app.include_router(airflow_proxy.router, prefix="/api/v1", tags=["airflow"])
app.include_router(airflow_widgets.router, prefix="/api/v1", tags=["airflow"])
app.include_router(codeserver.router, prefix="/api/v1", tags=["codeserver"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
