from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import insert, select

from app.auth.password import hash_password
from app.config import settings
from app.database import engine
from app.models.base import Base
from app.models.role import Role
from app.models.user import User
from app.routers import admin, airflow_lifecycle, airflow_proxy, airflow_widgets, auth, codeserver, git, health, projects, workspace

DEFAULT_ROLES: dict[str, str] = {
    "super_admin": "Full system access",
    "project_admin": "Admin of a specific project",
    "maintainer": "Can manage DAGs and resources",
    "developer": "Can develop and test pipelines",
    "viewer": "Read-only access",
}


async def seed_defaults() -> None:
    """Create default roles and super admin on first startup."""
    async with engine.begin() as conn:
        for name, desc in DEFAULT_ROLES.items():
            result = await conn.execute(select(Role).where(Role.name == name))
            if not result.scalar_one_or_none():
                await conn.execute(
                    insert(Role).values(name=name, description=desc, is_system=True)
                )

        result = await conn.execute(
            select(User).where(User.email == settings.admin_email)
        )
        if not result.scalar_one_or_none():
            await conn.execute(
                insert(User).values(
                    email=settings.admin_email,
                    hashed_password=hash_password(settings.admin_password),
                    display_name=settings.admin_name,
                    is_active=True,
                    is_admin=True,
                )
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (dev convenience — Alembic is the prod path)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_defaults()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
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
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://frontend:3000",
        ],
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
    app.include_router(workspace.router, prefix="/api/v1", tags=["codeserver"])
    app.include_router(git.router, prefix="/api/v1", tags=["git"])
    app.include_router(admin.router, prefix="/api/v1", tags=["admin"])

    return app


app = create_app()