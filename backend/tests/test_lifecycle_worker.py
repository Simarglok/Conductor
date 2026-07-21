from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_lifecycle_job import (
    LifecycleJobStatus,
    LifecycleOperation,
    ProjectLifecycleJob,
)
from app.services.lifecycle_errors import TransientLifecycleError
from app.services.lifecycle_queue import ClaimedJob, JobOwnershipError
from app.services.lifecycle_runner import LifecycleRunnerRegistry, RunnerNotConfiguredError
from app.workers import lifecycle as lifecycle_worker
from app.workers.lifecycle import WorkerOptions, process_one_job, run_worker


async def _persist_job(session: AsyncSession, suffix: str) -> ProjectLifecycleJob:
    project = Project(
        name=f"Worker {suffix}",
        slug=f"worker-{suffix}-{uuid4().hex[:8]}",
        lifecycle_status=ProjectLifecycleStatus.PROVISIONING,
    )
    session.add(project)
    await session.flush()
    job = ProjectLifecycleJob(
        project_id=project.id,
        operation=LifecycleOperation.PROVISION,
        status=LifecycleJobStatus.PENDING,
        attempt=0,
        max_attempts=3,
        available_at=datetime.now(timezone.utc),
        idempotency_key=str(uuid4()),
        request_fingerprint=uuid4().hex + uuid4().hex,
        correlation_id=uuid4().hex,
    )
    session.add(job)
    await session.commit()
    return job


def _options(*, heartbeat_seconds: float = 10.0) -> WorkerOptions:
    return WorkerOptions(
        poll_seconds=0.01,
        lease_seconds=30,
        heartbeat_seconds=heartbeat_seconds,
        retry_base_seconds=2.0,
        retry_cap_seconds=10.0,
        retry_jitter_seconds=0.0,
    )


def test_runner_registry_is_keyed_by_operation_and_rejects_missing_runner() -> None:
    registry = LifecycleRunnerRegistry()

    async def provision(_job) -> None:
        return None

    registry.register(LifecycleOperation.PROVISION, provision)

    assert registry.resolve(LifecycleOperation.PROVISION) is provision
    with pytest.raises(RunnerNotConfiguredError):
        registry.resolve(LifecycleOperation.DELETE)


@pytest.mark.asyncio
async def test_worker_processes_one_job_with_fake_runner_and_heartbeats(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        job = await _persist_job(setup, "success")

    ran = asyncio.Event()
    registry = LifecycleRunnerRegistry()

    async def provision(claimed) -> None:
        assert claimed.id == job.id
        async with asyncio.timeout(1):
            while True:
                async with factory() as probe:
                    persisted = await probe.get(ProjectLifecycleJob, job.id)
                assert persisted is not None
                if (
                    persisted.started_at is not None
                    and persisted.heartbeat_at is not None
                    and persisted.heartbeat_at > persisted.started_at
                ):
                    break
                await asyncio.sleep(0.005)
        ran.set()

    registry.register(LifecycleOperation.PROVISION, provision)

    processed = await process_one_job(
        factory,
        registry,
        worker_id="worker-success",
        options=_options(heartbeat_seconds=0.01),
    )

    assert processed is True
    assert ran.is_set()
    async with factory() as verification:
        persisted = await verification.get(ProjectLifecycleJob, job.id)
    assert persisted is not None
    assert persisted.status is LifecycleJobStatus.SUCCEEDED
    assert persisted.heartbeat_at is not None
    assert persisted.started_at is not None
    assert persisted.heartbeat_at > persisted.started_at


@pytest.mark.asyncio
async def test_worker_retries_fake_runner_failure_and_redacts_structured_logs(
    _engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        job = await _persist_job(setup, "failure")

    registry = LifecycleRunnerRegistry()

    async def provision(_claimed) -> None:
        raise TransientLifecycleError("password=hunter2")

    registry.register(LifecycleOperation.PROVISION, provision)
    caplog.set_level(logging.INFO, logger="app.workers.lifecycle")

    processed = await process_one_job(
        factory,
        registry,
        worker_id="worker-failure",
        options=_options(),
        jitter_source=lambda _maximum: 0.0,
    )

    assert processed is True
    async with factory() as verification:
        persisted = await verification.get(ProjectLifecycleJob, job.id)
    assert persisted is not None
    assert persisted.status is LifecycleJobStatus.RETRY_WAIT
    assert "hunter2" not in caplog.text
    assert "[REDACTED]" in caplog.text
    assert '"event": "lifecycle_job_retry_scheduled"' in caplog.text


@pytest.mark.asyncio
async def test_worker_loop_exits_cleanly_when_stop_is_already_requested(_engine) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    stop_event = asyncio.Event()
    stop_event.set()

    await run_worker(
        factory,
        LifecycleRunnerRegistry(),
        worker_id="worker-stop",
        options=_options(),
        stop_event=stop_event,
        once=False,
    )


def test_worker_process_identity_is_unique_for_a_reused_operator_label() -> None:
    first = lifecycle_worker._worker_id("operator-label")
    second = lifecycle_worker._worker_id("operator-label")

    assert first != second
    assert first.startswith("operator-label:")
    assert second.startswith("operator-label:")
    assert len(first) <= 255
    assert len(second) <= 255


@pytest.mark.asyncio
async def test_run_with_heartbeats_cancels_children_when_parent_is_cancelled(
    _engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    runner_started = asyncio.Event()
    runner_cancelled = asyncio.Event()
    heartbeat_started = asyncio.Event()
    heartbeat_cancelled = asyncio.Event()
    never_finishes = asyncio.Event()

    async def provision(_claimed) -> None:
        runner_started.set()
        try:
            await never_finishes.wait()
        finally:
            runner_cancelled.set()

    async def heartbeat_loop(*_args, **_kwargs) -> None:
        heartbeat_started.set()
        try:
            await never_finishes.wait()
        finally:
            heartbeat_cancelled.set()

    monkeypatch.setattr(lifecycle_worker, "_heartbeat_loop", heartbeat_loop)
    registry = LifecycleRunnerRegistry({LifecycleOperation.PROVISION: provision})
    claimed = ClaimedJob(
        id="job-id",
        project_id="project-id",
        operation=LifecycleOperation.PROVISION,
        attempt=1,
        max_attempts=3,
        worker_id="operator-label:incarnation",
        correlation_id="correlation-id",
        requested_by=None,
    )
    parent = asyncio.create_task(
        lifecycle_worker._run_with_heartbeats(
            factory,
            registry,
            claimed=claimed,
            worker_id=claimed.worker_id,
            options=_options(),
            clock=lambda: datetime.now(timezone.utc),
        )
    )
    async with asyncio.timeout(1):
        await runner_started.wait()
        await heartbeat_started.wait()

    parent.cancel()
    with pytest.raises(asyncio.CancelledError):
        await parent

    assert runner_cancelled.is_set()
    assert heartbeat_cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("heartbeat_error", "expected_status", "expected_error_code"),
    [
        (
            JobOwnershipError("lease lost"),
            LifecycleJobStatus.RUNNING,
            None,
        ),
        (
            RuntimeError("heartbeat transport failed"),
            LifecycleJobStatus.RETRY_WAIT,
            "TRANSIENT_LIFECYCLE_ERROR",
        ),
    ],
    ids=["ownership-loss", "transient-heartbeat-error"],
)
async def test_heartbeat_failure_cancels_runner_and_preserves_error_semantics(
    _engine,
    monkeypatch: pytest.MonkeyPatch,
    heartbeat_error: Exception,
    expected_status: LifecycleJobStatus,
    expected_error_code: str | None,
) -> None:
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        job = await _persist_job(setup, f"heartbeat-{expected_status.value}")

    runner_started = asyncio.Event()
    runner_cancelled = asyncio.Event()
    never_finishes = asyncio.Event()

    async def provision(_claimed) -> None:
        runner_started.set()
        try:
            await never_finishes.wait()
        finally:
            runner_cancelled.set()

    async def failing_heartbeat_loop(*_args, **_kwargs) -> None:
        await runner_started.wait()
        raise heartbeat_error

    monkeypatch.setattr(lifecycle_worker, "_heartbeat_loop", failing_heartbeat_loop)
    registry = LifecycleRunnerRegistry({LifecycleOperation.PROVISION: provision})

    processed = await process_one_job(
        factory,
        registry,
        worker_id="worker-heartbeat-failure",
        options=_options(),
        jitter_source=lambda _maximum: 0.0,
    )

    assert processed is True
    assert runner_cancelled.is_set()
    async with factory() as verification:
        persisted = await verification.get(ProjectLifecycleJob, job.id)
    assert persisted is not None
    assert persisted.status is expected_status
    assert persisted.error_code == expected_error_code
    if expected_status is LifecycleJobStatus.RUNNING:
        assert persisted.locked_by == "worker-heartbeat-failure"
    else:
        assert persisted.locked_by is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"lifecycle_worker_poll_seconds": 0},
        {"lifecycle_worker_lease_seconds": 0},
        {"lifecycle_worker_heartbeat_seconds": 0},
        {
            "lifecycle_worker_lease_seconds": 30,
            "lifecycle_worker_heartbeat_seconds": 30,
        },
        {
            "lifecycle_worker_lease_seconds": 30,
            "lifecycle_worker_heartbeat_seconds": 31,
        },
        {"lifecycle_retry_base_seconds": 0},
        {"lifecycle_retry_cap_seconds": 0},
        {"lifecycle_retry_jitter_seconds": -1},
        {
            "lifecycle_retry_base_seconds": 20,
            "lifecycle_retry_cap_seconds": 10,
        },
    ],
)
def test_settings_reject_invalid_worker_timing(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Settings(**overrides)


@pytest.mark.parametrize(
    "field",
    [
        "lifecycle_worker_poll_seconds",
        "lifecycle_worker_heartbeat_seconds",
        "lifecycle_retry_base_seconds",
        "lifecycle_retry_cap_seconds",
        "lifecycle_retry_jitter_seconds",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_settings_reject_non_finite_worker_timing(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_worker_timing_defaults_are_documented_values() -> None:
    assert {
        field: Settings.model_fields[field].default
        for field in (
            "lifecycle_worker_poll_seconds",
            "lifecycle_worker_lease_seconds",
            "lifecycle_worker_heartbeat_seconds",
            "lifecycle_retry_base_seconds",
            "lifecycle_retry_cap_seconds",
            "lifecycle_retry_jitter_seconds",
        )
    } == {
        "lifecycle_worker_poll_seconds": 1.0,
        "lifecycle_worker_lease_seconds": 30,
        "lifecycle_worker_heartbeat_seconds": 10.0,
        "lifecycle_retry_base_seconds": 5.0,
        "lifecycle_retry_cap_seconds": 300.0,
        "lifecycle_retry_jitter_seconds": 1.0,
    }
