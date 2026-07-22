from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_lifecycle_job import (
    LifecycleJobStatus,
    LifecycleOperation,
    ProjectLifecycleJob,
)
from app.services.lifecycle_errors import PermanentLifecycleError, TransientLifecycleError
from app.services.lifecycle_queue import (
    JobOwnershipError,
    claim_next_job,
    complete_job,
    heartbeat_job,
    retry_or_fail_job,
)


def _utc(hour: int = 12) -> datetime:
    return datetime(2026, 7, 22, hour, tzinfo=timezone.utc)


async def _persist_job(
    session: AsyncSession,
    *,
    suffix: str,
    operation: LifecycleOperation = LifecycleOperation.PROVISION,
    project_status: ProjectLifecycleStatus = ProjectLifecycleStatus.PROVISIONING,
    job_status: LifecycleJobStatus = LifecycleJobStatus.PENDING,
    available_at: datetime | None = None,
    max_attempts: int = 3,
    locked_by: str | None = None,
    lock_expires_at: datetime | None = None,
) -> tuple[Project, ProjectLifecycleJob]:
    project = Project(
        name=f"Queue {suffix}",
        slug=f"queue-{suffix}-{uuid4().hex[:8]}",
        lifecycle_status=project_status,
    )
    session.add(project)
    await session.flush()
    job = ProjectLifecycleJob(
        project_id=project.id,
        operation=operation,
        status=job_status,
        attempt=0,
        max_attempts=max_attempts,
        available_at=available_at or _utc(),
        locked_by=locked_by,
        lock_expires_at=lock_expires_at,
        idempotency_key=str(uuid4()),
        request_fingerprint=uuid4().hex + uuid4().hex,
        correlation_id=uuid4().hex,
    )
    session.add(job)
    await session.commit()
    return project, job


@pytest.mark.asyncio
async def test_two_concurrent_claimers_get_at_most_one_live_lease(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        _, job = await _persist_job(setup, suffix="concurrent")

    async def claim(worker_id: str):
        async with factory() as session:
            return await claim_next_job(session, worker_id, _utc(), lease_seconds=30)

    first, second = await asyncio.gather(claim("worker-a"), claim("worker-b"))

    claimed = [item for item in (first, second) if item is not None]
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].attempt == 1

    async with factory() as verification:
        persisted = await verification.get(ProjectLifecycleJob, job.id)
        assert persisted is not None
        assert persisted.status is LifecycleJobStatus.RUNNING
        assert persisted.locked_by == claimed[0].worker_id
        assert persisted.lock_expires_at == _utc() + timedelta(seconds=30)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["heartbeat", "complete", "retry"])
async def test_foreign_worker_cannot_mutate_current_attempt_lease(
    _engine,
    action: str,
) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        _, job = await _persist_job(setup, suffix=f"foreign-{action}")

    async with factory() as session:
        claimed = await claim_next_job(session, "owner", _utc(), lease_seconds=30)
    assert claimed is not None

    async with factory() as verification:
        before = await verification.get(ProjectLifecycleJob, job.id)
        assert before is not None
        expected_state = (
            before.status,
            before.attempt,
            before.locked_by,
            before.lock_expires_at,
            before.heartbeat_at,
            before.available_at,
            before.finished_at,
            before.error_code,
            before.error_message,
        )

    async with factory() as session:
        with pytest.raises(JobOwnershipError):
            if action == "heartbeat":
                await heartbeat_job(
                    session,
                    job.id,
                    "foreign-owner",
                    _utc() + timedelta(seconds=1),
                    lease_seconds=30,
                    expected_attempt=claimed.attempt,
                )
            elif action == "complete":
                await complete_job(
                    session,
                    job.id,
                    "foreign-owner",
                    _utc() + timedelta(seconds=1),
                    expected_attempt=claimed.attempt,
                )
            else:
                await retry_or_fail_job(
                    session,
                    job.id,
                    "foreign-owner",
                    _utc() + timedelta(seconds=1),
                    TransientLifecycleError("temporary outage"),
                    expected_attempt=claimed.attempt,
                    retry_base_seconds=2.0,
                    retry_cap_seconds=10.0,
                    retry_jitter_seconds=0.0,
                )

    async with factory() as verification:
        after = await verification.get(ProjectLifecycleJob, job.id)
        assert after is not None
        assert (
            after.status,
            after.attempt,
            after.locked_by,
            after.lock_expires_at,
            after.heartbeat_at,
            after.available_at,
            after.finished_at,
            after.error_code,
            after.error_message,
        ) == expected_state


@pytest.mark.asyncio
async def test_retry_wait_is_not_claimed_early_and_uses_bounded_backoff(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        _, job = await _persist_job(setup, suffix="retry")

    async with factory() as session:
        claimed = await claim_next_job(session, "worker-a", _utc(), lease_seconds=30)
    assert claimed is not None

    async with factory() as session:
        terminal = await retry_or_fail_job(
            session,
            job.id,
            "worker-a",
            _utc() + timedelta(seconds=10),
            TransientLifecycleError("temporary outage"),
            expected_attempt=claimed.attempt,
            retry_base_seconds=2.0,
            retry_cap_seconds=10.0,
            retry_jitter_seconds=0.25,
        )
    assert terminal is False

    retry_at = _utc() + timedelta(seconds=12.25)
    async with factory() as session:
        assert await claim_next_job(
            session, "worker-b", retry_at - timedelta(microseconds=1), lease_seconds=30
        ) is None
    async with factory() as session:
        reclaimed = await claim_next_job(session, "worker-b", retry_at, lease_seconds=30)
    assert reclaimed is not None
    assert reclaimed.id == job.id
    assert reclaimed.attempt == 2


@pytest.mark.asyncio
async def test_heartbeat_extends_lease_and_reclaim_fences_stale_attempt(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        _, job = await _persist_job(setup, suffix="lease")

    async with factory() as session:
        original = await claim_next_job(session, "worker-a", _utc(), lease_seconds=30)
    assert original is not None
    heartbeat_at = _utc() + timedelta(seconds=10)
    async with factory() as session:
        await heartbeat_job(
            session,
            job.id,
            "worker-a",
            heartbeat_at,
            lease_seconds=30,
            expected_attempt=original.attempt,
        )

    async with factory() as verification:
        persisted = await verification.get(ProjectLifecycleJob, job.id)
        assert persisted is not None
        assert persisted.heartbeat_at == heartbeat_at
        assert persisted.lock_expires_at == heartbeat_at + timedelta(seconds=30)

    reclaimed_at = heartbeat_at + timedelta(seconds=31)
    async with factory() as session:
        reclaimed = await claim_next_job(
            session,
            "worker-a",
            reclaimed_at,
            lease_seconds=30,
        )
    assert reclaimed is not None
    assert reclaimed.worker_id == "worker-a"
    assert reclaimed.attempt == original.attempt + 1

    async with factory() as session:
        with pytest.raises(JobOwnershipError):
            await complete_job(
                session,
                job.id,
                "worker-a",
                reclaimed_at + timedelta(seconds=1),
                expected_attempt=original.attempt,
            )
    async with factory() as session:
        await complete_job(
            session,
            job.id,
            "worker-a",
            reclaimed_at + timedelta(seconds=1),
            expected_attempt=reclaimed.attempt,
        )


@pytest.mark.asyncio
async def test_expired_final_attempt_is_terminalized_instead_of_reclaimed(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        project, job = await _persist_job(
            setup,
            suffix="exhausted-lease",
            max_attempts=1,
        )
        job.status = LifecycleJobStatus.RUNNING
        job.attempt = 1
        job.locked_by = "crashed-worker"
        job.lock_expires_at = _utc()
        job.heartbeat_at = _utc()
        job.started_at = _utc()
        await setup.commit()

    async with factory() as session:
        claimed = await claim_next_job(
            session,
            "replacement-worker",
            _utc() + timedelta(seconds=1),
            lease_seconds=30,
        )
    assert claimed is None

    async with factory() as verification:
        stored_job = await verification.get(ProjectLifecycleJob, job.id)
        stored_project = await verification.get(Project, project.id)
        events = (
            await verification.execute(
                select(AuditEvent).where(AuditEvent.project_id_snapshot == project.id)
            )
        ).scalars().all()

    assert stored_job is not None
    assert stored_project is not None
    assert stored_job.status is LifecycleJobStatus.FAILED
    assert stored_job.attempt == stored_job.max_attempts == 1
    assert stored_job.error_code == "WORKER_LEASE_EXPIRED"
    assert stored_job.locked_by is None
    assert stored_project.lifecycle_status is ProjectLifecycleStatus.PROVISION_FAILED
    assert [event.event_type for event in events] == ["project.provision.failed"]
    assert events[0].metadata_json["error_code"] == "WORKER_LEASE_EXPIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "initial_status", "terminal_status", "event_type"),
    [
        (
            LifecycleOperation.PROVISION,
            ProjectLifecycleStatus.PROVISIONING,
            ProjectLifecycleStatus.PROVISION_FAILED,
            "project.provision.failed",
        ),
        (
            LifecycleOperation.DELETE,
            ProjectLifecycleStatus.DELETING,
            ProjectLifecycleStatus.DELETION_FAILED,
            "project.delete.failed",
        ),
    ],
)
async def test_max_attempt_failure_updates_project_and_appends_sanitized_audit(
    _engine,
    operation: LifecycleOperation,
    initial_status: ProjectLifecycleStatus,
    terminal_status: ProjectLifecycleStatus,
    event_type: str,
) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        project, job = await _persist_job(
            setup,
            suffix=operation.value,
            operation=operation,
            project_status=initial_status,
            max_attempts=1,
        )

    async with factory() as session:
        claimed = await claim_next_job(session, "worker-a", _utc(), lease_seconds=30)
    assert claimed is not None
    async with factory() as session:
        terminal = await retry_or_fail_job(
            session,
            job.id,
            "worker-a",
            _utc() + timedelta(seconds=10),
            TransientLifecycleError("password=hunter2"),
            expected_attempt=claimed.attempt,
            retry_base_seconds=2.0,
            retry_cap_seconds=10.0,
            retry_jitter_seconds=0.0,
        )
    assert terminal is True

    async with factory() as verification:
        persisted_job = await verification.get(ProjectLifecycleJob, job.id)
        persisted_project = await verification.get(Project, project.id)
        events = (
            await verification.execute(
                select(AuditEvent).where(AuditEvent.project_id_snapshot == project.id)
            )
        ).scalars().all()

    assert persisted_job is not None
    assert persisted_job.status is LifecycleJobStatus.FAILED
    assert persisted_job.error_code == "TRANSIENT_LIFECYCLE_ERROR"
    assert "hunter2" not in (persisted_job.error_message or "")
    assert "[REDACTED]" in (persisted_job.error_message or "")
    assert persisted_project is not None
    assert persisted_project.lifecycle_status is terminal_status
    assert [event.event_type for event in events] == [event_type]
    assert "hunter2" not in str(events[0].metadata_json)


@pytest.mark.asyncio
async def test_permanent_error_fails_immediately_before_max_attempts(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        _, job = await _persist_job(setup, suffix="permanent", max_attempts=5)

    async with factory() as session:
        claimed = await claim_next_job(session, "worker-a", _utc(), lease_seconds=30)
    assert claimed is not None
    async with factory() as session:
        terminal = await retry_or_fail_job(
            session,
            job.id,
            "worker-a",
            _utc() + timedelta(seconds=10),
            PermanentLifecycleError("invalid desired state"),
            expected_attempt=claimed.attempt,
            retry_base_seconds=2.0,
            retry_cap_seconds=10.0,
            retry_jitter_seconds=0.0,
        )
    assert terminal is True


@pytest.mark.asyncio
async def test_terminal_job_releases_partial_unique_active_job_slot(db_session: AsyncSession) -> None:
    project, first = await _persist_job(db_session, suffix="partial-index")
    first.status = LifecycleJobStatus.SUCCEEDED
    first.finished_at = _utc()
    await db_session.commit()

    successor = ProjectLifecycleJob(
        project_id=project.id,
        operation=LifecycleOperation.RECONCILE,
        status=LifecycleJobStatus.PENDING,
        attempt=0,
        max_attempts=3,
        available_at=_utc(),
        idempotency_key=str(uuid4()),
        request_fingerprint=uuid4().hex + uuid4().hex,
        correlation_id=uuid4().hex,
    )
    db_session.add(successor)
    await db_session.commit()

    duplicate = ProjectLifecycleJob(
        project_id=project.id,
        operation=LifecycleOperation.RECONCILE,
        status=LifecycleJobStatus.RETRY_WAIT,
        attempt=1,
        max_attempts=3,
        available_at=_utc(),
        idempotency_key=str(uuid4()),
        request_fingerprint=uuid4().hex + uuid4().hex,
        correlation_id=uuid4().hex,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
