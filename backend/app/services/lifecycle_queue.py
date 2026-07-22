"""PostgreSQL-backed lifecycle job claiming, leases, retries, and finalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Real

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_lifecycle_job import (
    LifecycleJobStatus,
    LifecycleOperation,
    ProjectLifecycleJob,
)
from app.services.lifecycle_errors import (
    ErrorDisposition,
    LifecycleError,
    classify_lifecycle_error,
    retry_delay,
)
from app.services.secret_redaction import redact_secret_text


class JobOwnershipError(RuntimeError):
    """The caller does not own a current, unexpired lease for a running job."""


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    project_id: str
    operation: LifecycleOperation
    attempt: int
    max_attempts: int
    worker_id: str
    correlation_id: str
    requested_by: str | None


def _positive_seconds(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _claimed_job(job: ProjectLifecycleJob) -> ClaimedJob:
    if job.locked_by is None:
        raise RuntimeError("Claimed lifecycle job has no worker owner")
    return ClaimedJob(
        id=job.id,
        project_id=job.project_id,
        operation=job.operation,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        worker_id=job.locked_by,
        correlation_id=job.correlation_id,
        requested_by=job.requested_by,
    )


async def claim_next_job(
    session: AsyncSession,
    worker_id: str,
    now: datetime,
    lease_seconds: float,
) -> ClaimedJob | None:
    """Claim one due job in a short transaction without blocking other workers."""

    if not worker_id:
        raise ValueError("worker_id must not be empty")
    lease = _positive_seconds(lease_seconds, name="lease_seconds")

    try:
        while True:
            job = (
                await session.execute(
                    select(ProjectLifecycleJob)
                    .where(
                        or_(
                            and_(
                                ProjectLifecycleJob.status.in_(
                                    (LifecycleJobStatus.PENDING, LifecycleJobStatus.RETRY_WAIT)
                                ),
                                ProjectLifecycleJob.available_at <= now,
                            ),
                            and_(
                                ProjectLifecycleJob.status == LifecycleJobStatus.RUNNING,
                                ProjectLifecycleJob.lock_expires_at.is_not(None),
                                ProjectLifecycleJob.lock_expires_at <= now,
                            ),
                        )
                    )
                    .order_by(
                        ProjectLifecycleJob.available_at,
                        ProjectLifecycleJob.created_at,
                        ProjectLifecycleJob.id,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if job is None:
                await session.rollback()
                return None

            if (
                job.status is LifecycleJobStatus.RUNNING
                and job.attempt >= job.max_attempts
            ):
                await _fail_job(
                    session,
                    job=job,
                    now=now,
                    error_code="WORKER_LEASE_EXPIRED",
                    error_message="Worker lease expired after the final permitted attempt",
                )
                await session.commit()
                continue

            job.status = LifecycleJobStatus.RUNNING
            job.attempt += 1
            job.locked_by = worker_id
            job.lock_expires_at = now + timedelta(seconds=lease)
            job.heartbeat_at = now
            if job.started_at is None:
                job.started_at = now
            job.finished_at = None
            claimed = _claimed_job(job)
            await session.commit()
            return claimed
    except Exception:
        await session.rollback()
        raise


async def _lock_owned_job(
    session: AsyncSession,
    *,
    job_id: str,
    worker_id: str,
    expected_attempt: int,
    now: datetime,
) -> ProjectLifecycleJob:
    job = (
        await session.execute(
            select(ProjectLifecycleJob)
            .where(ProjectLifecycleJob.id == job_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        job is None
        or job.status is not LifecycleJobStatus.RUNNING
        or job.locked_by != worker_id
        or job.attempt != expected_attempt
        or job.lock_expires_at is None
        or job.lock_expires_at <= now
    ):
        raise JobOwnershipError("Lifecycle job lease is not owned by this worker")
    return job


async def heartbeat_job(
    session: AsyncSession,
    job_id: str,
    worker_id: str,
    now: datetime,
    lease_seconds: float,
    *,
    expected_attempt: int,
) -> None:
    """Extend a currently owned live lease."""

    lease = _positive_seconds(lease_seconds, name="lease_seconds")
    try:
        job = await _lock_owned_job(
            session,
            job_id=job_id,
            worker_id=worker_id,
            expected_attempt=expected_attempt,
            now=now,
        )
        job.heartbeat_at = now
        job.lock_expires_at = now + timedelta(seconds=lease)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def complete_job(
    session: AsyncSession,
    job_id: str,
    worker_id: str,
    now: datetime,
    *,
    expected_attempt: int,
) -> None:
    """Mark a currently owned live job successful."""

    try:
        job = await _lock_owned_job(
            session,
            job_id=job_id,
            worker_id=worker_id,
            expected_attempt=expected_attempt,
            now=now,
        )
        job.status = LifecycleJobStatus.SUCCEEDED
        job.locked_by = None
        job.lock_expires_at = None
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def _error_code(error: Exception) -> str:
    code = error.code if isinstance(error, LifecycleError) else "TRANSIENT_LIFECYCLE_ERROR"
    return str(code)[:64]


async def _record_terminal_failure(
    session: AsyncSession,
    *,
    job: ProjectLifecycleJob,
    error_code: str,
) -> None:
    project = await session.get(Project, job.project_id, with_for_update=True)
    if project is None:
        raise RuntimeError("Lifecycle job has no project")

    if job.operation is LifecycleOperation.PROVISION:
        project.lifecycle_status = ProjectLifecycleStatus.PROVISION_FAILED
        event_type = "project.provision.failed"
    elif job.operation is LifecycleOperation.DELETE:
        project.lifecycle_status = ProjectLifecycleStatus.DELETION_FAILED
        event_type = "project.delete.failed"
    else:
        return

    session.add(
        AuditEvent(
            event_type=event_type,
            actor_user_id=job.requested_by,
            project_id_snapshot=project.id,
            project_name_snapshot=project.name,
            project_slug_snapshot=project.slug,
            correlation_id=job.correlation_id,
            outcome="failed",
            metadata_json={
                "operation_id": job.id,
                "operation": job.operation.value,
                "attempt": job.attempt,
                "error_code": error_code,
            },
        )
    )


async def _fail_job(
    session: AsyncSession,
    *,
    job: ProjectLifecycleJob,
    now: datetime,
    error_code: str,
    error_message: str,
) -> None:
    job.status = LifecycleJobStatus.FAILED
    job.error_code = error_code
    job.error_message = error_message
    job.locked_by = None
    job.lock_expires_at = None
    job.finished_at = now
    await _record_terminal_failure(session, job=job, error_code=error_code)


async def retry_or_fail_job(
    session: AsyncSession,
    job_id: str,
    worker_id: str,
    now: datetime,
    error: Exception,
    *,
    expected_attempt: int,
    retry_base_seconds: float,
    retry_cap_seconds: float,
    retry_jitter_seconds: float,
) -> bool:
    """Persist a sanitized retry or terminal failure.

    Returns ``True`` for a terminal failure and ``False`` when a retry was
    scheduled.
    """

    try:
        job = await _lock_owned_job(
            session,
            job_id=job_id,
            worker_id=worker_id,
            expected_attempt=expected_attempt,
            now=now,
        )
        disposition = classify_lifecycle_error(error)
        terminal = disposition is ErrorDisposition.PERMANENT or job.attempt >= job.max_attempts
        error_code = _error_code(error)
        error_message = redact_secret_text(str(error))

        if terminal:
            await _fail_job(
                session,
                job=job,
                now=now,
                error_code=error_code,
                error_message=error_message,
            )
        else:
            job.error_code = error_code
            job.error_message = error_message
            job.locked_by = None
            job.lock_expires_at = None
            delay = retry_delay(
                max(job.attempt - 1, 0),
                base=float(retry_base_seconds),
                cap=float(retry_cap_seconds),
                jitter=float(retry_jitter_seconds),
            )
            job.status = LifecycleJobStatus.RETRY_WAIT
            job.available_at = now + timedelta(seconds=delay)
            job.finished_at = None

        await session.commit()
        return terminal
    except Exception:
        await session.rollback()
        raise
