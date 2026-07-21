from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.auth.password import hash_password
from app.cache import get_redis
from app.database import get_db_session
from app.main import create_app
from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_lifecycle_job import (
    LifecycleJobStatus,
    LifecycleOperation,
    ProjectLifecycleJob,
)
from app.models.project_member import ProjectMember
from app.models.reauth_grant import ReauthGrant
from app.models.role import Role
from app.models.user import User
from tests.fakes.fake_redis import FakeRedis


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
async def _client_for(engine, redis: FakeRedis | None = None):
    app = create_app()
    app.dependency_overrides[get_db_session] = _db_override(engine)
    app.dependency_overrides[get_redis] = lambda: redis or FakeRedis()
    transport = ASGITransport(app=app, client=("198.51.100.25", 53211))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = (
            f"Bearer {create_access_token('test-admin-001', 'admin@test.local', True)}"
        )
        yield client


async def _project(
    db_session,
    *,
    slug: str = "delete-project",
    status: ProjectLifecycleStatus = ProjectLifecycleStatus.READY,
    with_admin_member: bool = False,
) -> Project:
    project = Project(name=f"Project {slug}", slug=slug, lifecycle_status=status)
    db_session.add(project)
    await db_session.flush()
    if with_admin_member:
        role = (
            await db_session.execute(select(Role).where(Role.name == "project_admin"))
        ).scalar_one()
        db_session.add(
            ProjectMember(
                project_id=project.id,
                user_id="test-admin-001",
                role_id=role.id,
            )
        )
    await db_session.commit()
    return project


async def _grant(client: AsyncClient, project: Project) -> str:
    response = await client.post(
        "/api/v1/auth/reauth",
        json={
            "password": "admin",
            "action": "project.delete",
            "project_id": project.id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _delete_headers(token: str | None, key: str | None = None) -> dict[str, str]:
    headers = {"Idempotency-Key": key or str(uuid4())}
    if token is not None:
        headers["X-Reauth-Token"] = token
    return headers


async def _delete(
    client: AsyncClient,
    project: Project,
    token: str | None,
    *,
    key: str | None = None,
    confirmation_slug: str | None = None,
):
    return await client.request(
        "DELETE",
        f"/api/v1/admin/projects/{project.slug}",
        headers=_delete_headers(token, key),
        json={"confirmation_slug": confirmation_slug or project.slug},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_value", ["ready", "provision_failed"])
async def test_delete_atomically_consumes_bound_grant_transitions_and_enqueues(
    _engine,
    db_session,
    status_value,
    caplog,
):
    project = await _project(db_session, status=ProjectLifecycleStatus(status_value))
    redis = FakeRedis()
    key = str(uuid4())

    async with _client_for(_engine, redis) as client:
        token = await _grant(client, project)
        response = await _delete(client, project, token, key=key)

    assert response.status_code == 202, response.text
    payload = response.json()
    assert set(payload) == {"id", "operation", "status"}
    assert payload["operation"] == "delete"
    assert payload["status"] == "pending"

    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.DELETING
    grant = (
        await db_session.execute(
            select(ReauthGrant).where(
                ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert grant.consumed_at is not None
    operation = (
        await db_session.execute(
            select(ProjectLifecycleJob).where(ProjectLifecycleJob.id == payload["id"])
        )
    ).scalar_one()
    assert operation.operation is LifecycleOperation.DELETE
    assert operation.status is LifecycleJobStatus.PENDING
    assert operation.requested_by == "test-admin-001"
    assert operation.idempotency_key == key
    assert len(operation.request_fingerprint) == 64
    assert operation.correlation_id

    audit = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "project.delete.requested")
        )
    ).scalar_one()
    assert audit.actor_user_id == "test-admin-001"
    assert audit.project_id_snapshot == project.id
    assert audit.correlation_id == operation.correlation_id
    assert audit.metadata_json == {"operation_id": operation.id}
    exposed = response.text + caplog.text + json.dumps(audit.metadata_json)
    assert token not in exposed
    assert grant.token_hash not in exposed


@pytest.mark.asyncio
async def test_delete_requires_exact_confirmation_without_consuming_grant(
    _engine,
    db_session,
):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        response = await _delete(
            client,
            project,
            token,
            confirmation_slug=project.slug.upper(),
        )

    assert response.status_code == 400
    grant = (
        await db_session.execute(
            select(ReauthGrant).where(
                ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert grant.consumed_at is None
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.READY
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "invalid-opaque-grant"])
async def test_delete_rejects_missing_or_invalid_grant(_engine, db_session, token):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        response = await _delete(client, project, token)

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid re-authentication grant"}
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.READY
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["action", "project"])
async def test_delete_enforces_grant_action_and_project_binding(
    _engine,
    db_session,
    binding,
):
    project = await _project(db_session)
    other = await _project(db_session, slug="other-delete-project")
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        if binding == "action":
            grant = (
                await db_session.execute(
                    select(ReauthGrant).where(
                        ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
                    )
                )
            ).scalar_one()
            grant.action = "project.update"
            await db_session.commit()
            target = project
        else:
            target = other
        response = await _delete(client, target, token)

    assert response.status_code == 403
    await db_session.refresh(target)
    assert target.lifecycle_status is ProjectLifecycleStatus.READY
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 0


@pytest.mark.asyncio
async def test_delete_rejects_expired_grant_without_consuming_it(_engine, db_session):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        grant = (
            await db_session.execute(
                select(ReauthGrant).where(
                    ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
                )
            )
        ).scalar_one()
        grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.commit()
        response = await _delete(client, project, token)

    assert response.status_code == 403
    await db_session.refresh(grant)
    assert grant.consumed_at is None
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.READY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation_status", "project_status"),
    [
        (LifecycleJobStatus.PENDING, ProjectLifecycleStatus.DELETING),
        (LifecycleJobStatus.RUNNING, ProjectLifecycleStatus.DELETING),
        (LifecycleJobStatus.RETRY_WAIT, ProjectLifecycleStatus.DELETING),
        (LifecycleJobStatus.FAILED, ProjectLifecycleStatus.DELETION_FAILED),
    ],
)
async def test_same_key_replay_returns_current_operation_across_delete_states_without_grant(
    _engine,
    db_session,
    operation_status,
    project_status,
):
    project = await _project(db_session)
    key = str(uuid4())
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        first = await _delete(client, project, token, key=key)
        operation = await db_session.get(ProjectLifecycleJob, first.json()["id"])
        operation.status = operation_status
        operation.current_step = "stop_public_and_ide_entrypoints"
        if operation_status is LifecycleJobStatus.FAILED:
            operation.finished_at = datetime.now(timezone.utc)
        project.lifecycle_status = project_status
        await db_session.commit()
        replay = await _delete(client, project, None, key=key)

    assert first.status_code == replay.status_code == 202
    assert replay.json() == {
        "id": first.json()["id"],
        "operation": "delete",
        "status": operation_status.value,
    }
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "project.delete.requested")
        )
        == 1
    )

    if operation_status is LifecycleJobStatus.FAILED:
        async with _client_for(_engine) as client:
            different_key = await _delete(client, project, None)
            different_request = await _delete(
                client,
                project,
                None,
                key=key,
                confirmation_slug=f"{project.slug}-different",
            )
        assert different_key.status_code == 403
        assert different_request.status_code in {400, 409}


@pytest.mark.asyncio
async def test_different_key_replay_with_consumed_grant_is_denied(_engine, db_session):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        first = await _delete(client, project, token)
        second = await _delete(client, project, token)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {"detail": "Project deletion already has a different request"}
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 1


@pytest.mark.asyncio
async def test_concurrent_same_key_replay_creates_one_operation_and_consumes_once(
    _engine,
    db_session,
):
    project = await _project(db_session)
    key = str(uuid4())
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        first, second = await asyncio.gather(
            _delete(client, project, token, key=key),
            _delete(client, project, token, key=key),
        )

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 1
    grant = (
        await db_session.execute(
            select(ReauthGrant).where(
                ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert grant.consumed_at is not None


@pytest.mark.asyncio
async def test_concurrent_different_keys_cannot_consume_one_grant_twice(
    _engine,
    db_session,
):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        first, second = await asyncio.gather(
            _delete(client, project, token, key=str(uuid4())),
            _delete(client, project, token, key=str(uuid4())),
        )

    assert sorted([first.status_code, second.status_code]) == [202, 409]
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary_source", ["finished_at", "project_updated_at"])
async def test_deletion_failed_manual_retry_rejects_preissued_unused_grant_then_accepts_fresh(
    _engine,
    db_session,
    boundary_source,
):
    project = await _project(db_session)

    async with _client_for(_engine) as client:
        first_token = await _grant(client, project)
        preissued_spare = await _grant(client, project)
        first = await _delete(client, project, first_token)
        assert first.status_code == 202

        operation = await db_session.get(ProjectLifecycleJob, first.json()["id"])
        boundary = datetime.now(timezone.utc)
        operation.status = LifecycleJobStatus.FAILED
        operation.finished_at = boundary if boundary_source == "finished_at" else None
        project.lifecycle_status = ProjectLifecycleStatus.DELETION_FAILED
        project.updated_at = (
            boundary - timedelta(days=1)
            if boundary_source == "finished_at"
            else boundary
        )
        await db_session.commit()

        denied = await _delete(client, project, preissued_spare)
        assert denied.status_code == 403
        assert denied.json() == {"detail": "Invalid re-authentication grant"}

        spare_grant = (
            await db_session.execute(
                select(ReauthGrant).where(
                    ReauthGrant.token_hash
                    == hashlib.sha256(preissued_spare.encode()).hexdigest()
                )
            )
        ).scalar_one()
        assert spare_grant.consumed_at is None
        assert await db_session.scalar(
            select(func.count()).select_from(ProjectLifecycleJob)
        ) == 1

        fresh_token = await _grant(client, project)
        accepted = await _delete(client, project, fresh_token)

    assert accepted.status_code == 202
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 2
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.DELETING


@pytest.mark.asyncio
async def test_delete_transaction_rolls_back_and_redacts_unexpected_commit_failure(
    _engine,
    db_session,
    monkeypatch,
    caplog,
):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        leaked = "delete-commit-secret-token-value"

        async def fail_commit(_session):
            raise RuntimeError(leaked)

        monkeypatch.setattr(AsyncSession, "commit", fail_commit)
        response = await _delete(client, project, token)

    assert response.status_code == 500
    assert response.json() == {"detail": "Project deletion request failed"}
    assert leaked not in response.text
    assert leaked not in caplog.text
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.READY
    grant = (
        await db_session.execute(
            select(ReauthGrant).where(
                ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert grant.consumed_at is None
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "project.delete.requested")
        )
        == 0
    )


@pytest.mark.asyncio
async def test_delete_unrelated_integrity_failure_is_not_misclassified_as_idempotency(
    _engine,
    db_session,
    monkeypatch,
    caplog,
):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        leaked = "delete-integrity-secret-value"

        async def fail_commit(_session):
            raise IntegrityError("unrelated constraint", {}, RuntimeError(leaked))

        monkeypatch.setattr(AsyncSession, "commit", fail_commit)
        response = await _delete(client, project, token)

    assert response.status_code == 500
    assert response.json() == {"detail": "Project deletion request failed"}
    assert leaked not in response.text
    assert leaked not in caplog.text
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.READY
    assert await db_session.scalar(select(func.count()).select_from(ProjectLifecycleJob)) == 0


@pytest.mark.asyncio
async def test_project_is_hidden_from_ordinary_routes_immediately_after_acceptance(
    _engine,
    db_session,
):
    project = await _project(db_session, with_admin_member=True)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        accepted = await _delete(client, project, token)
        detail = await client.get(f"/api/v1/projects/{project.slug}")
        listing = await client.get("/api/v1/projects")

    assert accepted.status_code == 202
    assert detail.status_code == 404
    assert all(item["id"] != project.id for item in listing.json())


@pytest.mark.asyncio
async def test_legacy_project_delete_route_cannot_bypass_reauth(_engine, db_session):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        response = await client.delete(f"/api/v1/projects/{project.slug}")

    assert response.status_code in {404, 405}
    assert await db_session.get(Project, project.id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": "not-a-uuid"}])
async def test_delete_requires_uuid_idempotency_key(_engine, db_session, headers):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        request_headers = {"X-Reauth-Token": token, **headers}
        response = await client.request(
            "DELETE",
            f"/api/v1/admin/projects/{project.slug}",
            headers=request_headers,
            json={"confirmation_slug": project.slug},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_active", "is_admin", "status_code"),
    [(False, True, 401), (True, False, 403)],
)
async def test_delete_reloads_and_requires_current_active_super_admin(
    _engine,
    db_session,
    is_active,
    is_admin,
    status_code,
):
    project = await _project(db_session)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        actor = await db_session.get(User, "test-admin-001")
        actor.is_active = is_active
        actor.is_admin = is_admin
        await db_session.commit()
        response = await _delete(client, project, token)

    assert response.status_code == status_code
    await db_session.refresh(project)
    assert project.lifecycle_status is ProjectLifecycleStatus.READY
    grant = (
        await db_session.execute(
            select(ReauthGrant).where(
                ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert grant.consumed_at is None


@pytest.mark.asyncio
async def test_delete_rejects_non_deletable_state_without_consuming_grant(
    _engine,
    db_session,
):
    project = await _project(db_session, status=ProjectLifecycleStatus.PROVISIONING)
    async with _client_for(_engine) as client:
        token = await _grant(client, project)
        response = await _delete(client, project, token)

    assert response.status_code == 409
    grant = (
        await db_session.execute(
            select(ReauthGrant).where(
                ReauthGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
    ).scalar_one()
    assert grant.consumed_at is None
