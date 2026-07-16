from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import get_db_session
from app.main import create_app
from app.models.base import Base
from app.models.role import Role
from app.models.user import User
from app.auth.password import hash_password
from app.auth.jwt import create_access_token

TEST_DATABASE_URL = "postgresql+asyncpg://conductor:conductor@postgres:5432/conductor_test"


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_db(_engine):
    from sqlalchemy import select
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed defaults
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        for name, desc in [
            ("super_admin", "Full access"), ("project_admin", "Admin"),
            ("maintainer", "Maintainer"), ("developer", "Developer"), ("viewer", "Viewer"),
        ]:
            r = (await s.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
            if not r:
                s.add(Role(name=name, description=desc, is_system=True))
        s.add(User(id="test-admin-001", email="admin@test.local",
                   hashed_password=hash_password("admin"), display_name="Admin",
                   is_active=True, is_admin=True))
        await s.commit()


def _make_override(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    return _override


@pytest_asyncio.fixture
async def client(_engine):
    app = create_app()
    app.dependency_overrides[get_db_session] = _make_override(_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(_engine):
    token = create_access_token(user_id="test-admin-001", email="admin@test.local", is_admin=True)
    app = create_app()
    app.dependency_overrides[get_db_session] = _make_override(_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac