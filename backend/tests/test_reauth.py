from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import secrets
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token, decode_token
from app.auth.password import hash_password
from app.cache import get_redis
from app.config import Settings, settings
from app.database import get_db_session
from app.main import create_app
from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectLifecycleStatus
from app.models.reauth_grant import ReauthGrant
from app.models.user import User
from app.services.reauth import _increment_limit
from tests.fakes.fake_redis import FakeRedis


def test_reauth_settings_have_secure_fallbacks_and_prefixed_overrides(monkeypatch):
    for name in (
        "CONDUCTOR_REAUTH_GRANT_TTL_SECONDS",
        "CONDUCTOR_REAUTH_RATE_LIMIT_ATTEMPTS",
        "CONDUCTOR_REAUTH_RATE_LIMIT_WINDOW_SECONDS",
        "CONDUCTOR_TRUSTED_PROXY_CIDRS",
    ):
        monkeypatch.delenv(name, raising=False)

    defaults = Settings(_env_file=None)
    assert defaults.reauth_grant_ttl_seconds == 300
    assert defaults.reauth_rate_limit_attempts == 5
    assert defaults.reauth_rate_limit_window_seconds == 300
    assert defaults.trusted_proxy_cidrs == "127.0.0.0/8,::1/128"

    monkeypatch.setenv("CONDUCTOR_REAUTH_GRANT_TTL_SECONDS", "41")
    monkeypatch.setenv("CONDUCTOR_REAUTH_RATE_LIMIT_ATTEMPTS", "7")
    monkeypatch.setenv("CONDUCTOR_REAUTH_RATE_LIMIT_WINDOW_SECONDS", "59")
    monkeypatch.setenv(
        "CONDUCTOR_TRUSTED_PROXY_CIDRS",
        "10.20.0.0/24,2001:db8:1234::/48",
    )
    configured = Settings(_env_file=None)
    assert configured.reauth_grant_ttl_seconds == 41
    assert configured.reauth_rate_limit_attempts == 7
    assert configured.reauth_rate_limit_window_seconds == 59
    assert configured.trusted_proxy_cidrs == "10.20.0.0/24,2001:db8:1234::/48"


def test_cache_dependency_module_exists():
    assert importlib.util.find_spec("app.cache") is not None


@pytest.mark.asyncio
async def test_rate_limit_increment_is_atomic_concurrent_and_keeps_first_ttl(monkeypatch):
    clock = [100.0]
    redis = FakeRedis(now=lambda: clock[0])
    monkeypatch.setattr(settings, "reauth_rate_limit_window_seconds", 300)

    values = await asyncio.gather(
        *(_increment_limit(redis, "rate:user") for _ in range(50))
    )

    assert sorted(values) == list(range(1, 51))
    assert await redis.ttl("rate:user") == 300
    clock[0] = 250.0
    assert await _increment_limit(redis, "rate:user") == 51
    assert await redis.ttl("rate:user") == 150


@pytest.mark.asyncio
async def test_rate_limit_atomic_failure_cannot_leave_immortal_partial_counter(monkeypatch):
    redis = FakeRedis()
    redis.fail_atomic = True
    monkeypatch.setattr(settings, "reauth_rate_limit_window_seconds", 300)

    with pytest.raises(ConnectionError):
        await _increment_limit(redis, "rate:user")

    redis.fail_atomic = False
    assert await redis.ttl("rate:user") == -2
    assert await _increment_limit(redis, "rate:user") == 1
    assert await redis.ttl("rate:user") == 300


def _db_override(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override():
        async with factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    return override


@asynccontextmanager
async def _client_for(engine, redis: FakeRedis, *, host: str = "198.51.100.10"):
    app = create_app()
    app.dependency_overrides[get_db_session] = _db_override(engine)
    app.dependency_overrides[get_redis] = lambda: redis
    transport = ASGITransport(app=app, client=(host, 43123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _ready_project(db_session, *, slug: str = "reauth-project") -> Project:
    project = Project(
        name="Reauth Project",
        slug=slug,
        lifecycle_status=ProjectLifecycleStatus.READY,
    )
    db_session.add(project)
    await db_session.commit()
    return project


def _admin_auth(user_id: str = "test-admin-001", email: str = "admin@test.local") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, email, True)}"}


@pytest.mark.asyncio
async def test_existing_auth_redis_calls_use_overrideable_managed_dependency(_engine):
    redis = FakeRedis()
    async with _client_for(_engine, redis) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.local", "password": "admin"},
        )

    assert response.status_code == 200, response.text
    refresh = decode_token(response.json()["refresh_token"])
    assert refresh is not None
    assert await redis.get(f"{settings.redis_refresh_prefix}{refresh['jti']}") == "test-admin-001"


@pytest.mark.asyncio
async def test_reauth_returns_token_once_and_persists_only_bound_hash(
    _engine,
    db_session,
    monkeypatch,
    caplog,
):
    project = await _ready_project(db_session)
    redis = FakeRedis()
    opaque_token = "reauth-opaque-token-never-persist-or-log"
    monkeypatch.setattr(secrets, "token_urlsafe", lambda size: opaque_token if size == 32 else "unexpected")

    async with _client_for(_engine, redis) as client:
        response = await client.post(
            "/api/v1/auth/reauth",
            headers={**_admin_auth(), "X-Forwarded-For": "203.0.113.250"},
            json={
                "password": "admin",
                "action": "project.delete",
                "project_id": project.id,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"token": opaque_token, "expires_in": 300}
    grant = (await db_session.execute(select(ReauthGrant))).scalar_one()
    assert grant.token_hash == hashlib.sha256(opaque_token.encode()).hexdigest()
    assert opaque_token not in grant.token_hash
    assert grant.user_id == "test-admin-001"
    assert grant.action == "project.delete"
    assert grant.project_id == project.id
    assert grant.consumed_at is None

    audit = (await db_session.execute(select(AuditEvent))).scalar_one()
    assert audit.event_type == "auth.reauth"
    assert audit.actor_user_id == "test-admin-001"
    assert audit.outcome == "succeeded"
    assert audit.metadata_json == {"reason_code": "granted"}
    assert opaque_token not in json.dumps(audit.metadata_json)
    assert opaque_token not in caplog.text
    assert await redis.get("reauth:rate:ip:198.51.100.10") == "1"
    assert await redis.get("reauth:rate:ip:203.0.113.250") is None


@pytest.mark.asyncio
async def test_reauth_trusted_proxy_resolves_distinct_clients_and_safe_multi_hop_chain(
    _engine,
    db_session,
    monkeypatch,
):
    project = await _ready_project(db_session)
    redis = FakeRedis()
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.20.0.0/24")

    async with _client_for(_engine, redis, host="10.20.0.5") as client:
        for forwarded_for in (
            "198.51.100.11",
            "198.51.100.12",
            "192.0.2.250, 203.0.113.77, 10.20.0.6",
            "198.51.100.44, malformed",
        ):
            response = await client.post(
                "/api/v1/auth/reauth",
                headers={**_admin_auth(), "X-Forwarded-For": forwarded_for},
                json={
                    "password": "wrong",
                    "action": "project.delete",
                    "project_id": project.id,
                },
            )
            assert response.status_code == 401

    assert await redis.get("reauth:rate:ip:198.51.100.11") == "1"
    assert await redis.get("reauth:rate:ip:198.51.100.12") == "1"
    assert await redis.get("reauth:rate:ip:203.0.113.77") == "1"
    assert await redis.get("reauth:rate:ip:192.0.2.250") is None
    assert await redis.get("reauth:rate:ip:10.20.0.5") == "1"
    assert await redis.get("reauth:rate:ip:malformed") is None


@pytest.mark.asyncio
async def test_reauth_wrong_password_is_generic_audited_and_secret_free(
    _engine,
    db_session,
    caplog,
):
    project = await _ready_project(db_session)
    password = "wrong-password-secret-never-exposed"

    async with _client_for(_engine, FakeRedis()) as client:
        response = await client.post(
            "/api/v1/auth/reauth",
            headers=_admin_auth(),
            json={"password": password, "action": "project.delete", "project_id": project.id},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Re-authentication failed"}
    audit = (await db_session.execute(select(AuditEvent))).scalar_one()
    assert audit.outcome == "failed"
    assert audit.metadata_json == {"reason_code": "invalid_password"}
    exposed = response.text + caplog.text + json.dumps(audit.metadata_json)
    assert password not in exposed
    assert await db_session.scalar(select(ReauthGrant)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_active", "is_admin", "reason"),
    [(False, True, "inactive_actor"), (True, False, "not_super_admin")],
)
async def test_reauth_reloads_and_rejects_inactive_or_demoted_actor(
    _engine,
    db_session,
    is_active,
    is_admin,
    reason,
):
    project = await _ready_project(db_session)
    actor = await db_session.get(User, "test-admin-001")
    actor.is_active = is_active
    actor.is_admin = is_admin
    await db_session.commit()

    async with _client_for(_engine, FakeRedis()) as client:
        response = await client.post(
            "/api/v1/auth/reauth",
            headers=_admin_auth(),
            json={"password": "admin", "action": "project.delete", "project_id": project.id},
        )

    assert response.status_code == 403
    audit = (await db_session.execute(select(AuditEvent))).scalar_one()
    assert audit.metadata_json == {"reason_code": reason}
    assert await db_session.scalar(select(ReauthGrant)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "project_id", "reason", "status_code"),
    [
        ("project.update", None, "invalid_action", 400),
        ("project.delete", "missing-project-id", "project_not_found", 404),
    ],
)
async def test_reauth_rejects_invalid_action_or_project(
    _engine,
    db_session,
    action,
    project_id,
    reason,
    status_code,
):
    project = await _ready_project(db_session)

    async with _client_for(_engine, FakeRedis()) as client:
        response = await client.post(
            "/api/v1/auth/reauth",
            headers=_admin_auth(),
            json={
                "password": "admin",
                "action": action,
                "project_id": project_id or project.id,
            },
        )

    assert response.status_code == status_code
    audit = (await db_session.execute(select(AuditEvent))).scalar_one()
    assert audit.metadata_json == {"reason_code": reason}
    assert await db_session.scalar(select(ReauthGrant)) is None


@pytest.mark.asyncio
async def test_reauth_rate_limits_both_user_and_trusted_source_ip_with_first_attempt_expiry(
    _engine,
    db_session,
    monkeypatch,
):
    project = await _ready_project(db_session)
    clock = [10.0]
    redis = FakeRedis(now=lambda: clock[0])
    monkeypatch.setattr(settings, "reauth_rate_limit_attempts", 2)
    monkeypatch.setattr(settings, "reauth_rate_limit_window_seconds", 30)

    async with _client_for(_engine, redis, host="192.0.2.44") as client:
        for _ in range(2):
            response = await client.post(
                "/api/v1/auth/reauth",
                headers=_admin_auth(),
                json={"password": "wrong", "action": "project.delete", "project_id": project.id},
            )
            assert response.status_code == 401
        limited = await client.post(
            "/api/v1/auth/reauth",
            headers={**_admin_auth(), "Forwarded": "for=203.0.113.77"},
            json={"password": "admin", "action": "project.delete", "project_id": project.id},
        )

    assert limited.status_code == 429
    assert await redis.ttl("reauth:rate:user:test-admin-001") == 30
    assert await redis.ttl("reauth:rate:ip:192.0.2.44") == 30
    clock[0] = 25.0
    assert await redis.ttl("reauth:rate:user:test-admin-001") == 15

    second_admin = User(
        email="second-reauth-admin@test.local",
        hashed_password=hash_password("second-password"),
        display_name="Second Admin",
        is_active=True,
        is_admin=True,
    )
    third_admin = User(
        email="third-reauth-admin@test.local",
        hashed_password=hash_password("third-password"),
        display_name="Third Admin",
        is_active=True,
        is_admin=True,
    )
    db_session.add_all([second_admin, third_admin])
    await db_session.commit()
    async with _client_for(_engine, redis, host="192.0.2.99") as client:
        for actor in (second_admin, third_admin):
            response = await client.post(
                "/api/v1/auth/reauth",
                headers=_admin_auth(actor.id, actor.email),
                json={"password": "wrong", "action": "project.delete", "project_id": project.id},
            )
            assert response.status_code == 401
        ip_limited = await client.post(
            "/api/v1/auth/reauth",
            headers=_admin_auth(second_admin.id, second_admin.email),
            json={"password": "second-password", "action": "project.delete", "project_id": project.id},
        )
    assert ip_limited.status_code == 429


@pytest.mark.asyncio
async def test_reauth_redis_failure_fails_closed_with_redacted_503_and_audit(
    _engine,
    db_session,
    caplog,
):
    project = await _ready_project(db_session)
    redis = FakeRedis()
    redis.fail = True

    async with _client_for(_engine, redis) as client:
        response = await client.post(
            "/api/v1/auth/reauth",
            headers=_admin_auth(),
            json={"password": "admin", "action": "project.delete", "project_id": project.id},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Re-authentication temporarily unavailable"}
    audit = (await db_session.execute(select(AuditEvent))).scalar_one()
    assert audit.metadata_json == {"reason_code": "rate_limit_unavailable"}
    assert "secret-like-value" not in response.text
    assert "secret-like-value" not in caplog.text
    assert "secret-like-value" not in json.dumps(audit.metadata_json)
    assert await db_session.scalar(select(ReauthGrant)) is None


@pytest.mark.asyncio
async def test_reauth_unexpected_commit_failure_rolls_back_with_generic_secret_free_error(
    _engine,
    db_session,
    monkeypatch,
    caplog,
):
    project = await _ready_project(db_session)
    redis = FakeRedis()
    opaque_token = "reauth-generated-token-must-not-escape-on-failure"
    leaked_error = "reauth-database-secret-must-not-escape"
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _size: opaque_token)

    async def fail_commit(_session):
        raise RuntimeError(leaked_error)

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    app = create_app()
    app.dependency_overrides[get_db_session] = _db_override(_engine)
    app.dependency_overrides[get_redis] = lambda: redis
    transport = ASGITransport(
        app=app,
        client=("198.51.100.10", 43123),
        raise_app_exceptions=False,
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/reauth",
            headers=_admin_auth(),
            json={
                "password": "admin",
                "action": "project.delete",
                "project_id": project.id,
            },
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Re-authentication request failed"}
    exposed = response.text + caplog.text
    assert opaque_token not in exposed
    assert leaked_error not in exposed
    assert await db_session.scalar(select(ReauthGrant)) is None
    assert await db_session.scalar(select(AuditEvent)) is None
