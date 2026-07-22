"""Standalone PostgreSQL-backed lifecycle worker process."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
import random
import signal
import socket
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import async_session_factory
from app.services.lifecycle_errors import LifecycleError
from app.services.lifecycle_queue import (
    JobOwnershipError,
    claim_next_job,
    complete_job,
    heartbeat_job,
    retry_or_fail_job,
)
from app.services.lifecycle_runner import LifecycleRunnerRegistry, build_default_registry
from app.services.secret_redaction import redact_secret_text

logger = logging.getLogger(__name__)
Clock = Callable[[], datetime]
JitterSource = Callable[[float], float]


@dataclass(frozen=True)
class WorkerOptions:
    poll_seconds: float
    lease_seconds: int
    heartbeat_seconds: float
    retry_base_seconds: float
    retry_cap_seconds: float
    retry_jitter_seconds: float

    @classmethod
    def from_settings(cls) -> WorkerOptions:
        return cls(
            poll_seconds=settings.lifecycle_worker_poll_seconds,
            lease_seconds=settings.lifecycle_worker_lease_seconds,
            heartbeat_seconds=settings.lifecycle_worker_heartbeat_seconds,
            retry_base_seconds=settings.lifecycle_retry_base_seconds,
            retry_cap_seconds=settings.lifecycle_retry_cap_seconds,
            retry_jitter_seconds=settings.lifecycle_retry_jitter_seconds,
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sample_jitter(maximum: float) -> float:
    return random.uniform(0.0, maximum)


def _worker_id(label: str | None = None) -> str:
    prefix = label or f"{socket.gethostname()}:{os.getpid()}"
    return f"{prefix[:222]}:{uuid4().hex}"


def _error_code(error: Exception) -> str:
    if isinstance(error, LifecycleError):
        return error.code
    return "TRANSIENT_LIFECYCLE_ERROR"


def _log(event: str, **fields: object) -> None:
    logger.info(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


async def _heartbeat_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    job_id: str,
    worker_id: str,
    attempt: int,
    options: WorkerOptions,
    clock: Clock,
) -> None:
    while True:
        await asyncio.sleep(options.heartbeat_seconds)
        async with session_factory() as session:
            await heartbeat_job(
                session,
                job_id,
                worker_id,
                clock(),
                options.lease_seconds,
                expected_attempt=attempt,
            )
        _log("lifecycle_job_heartbeat", job_id=job_id, worker_id=worker_id)


async def _run_with_heartbeats(
    session_factory: async_sessionmaker[AsyncSession],
    registry: LifecycleRunnerRegistry,
    *,
    claimed,
    worker_id: str,
    options: WorkerOptions,
    clock: Clock,
) -> None:
    runner_task = asyncio.create_task(registry.resolve(claimed.operation)(claimed))
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(
            session_factory,
            job_id=claimed.id,
            worker_id=worker_id,
            attempt=claimed.attempt,
            options=options,
            clock=clock,
        )
    )
    try:
        done, _ = await asyncio.wait(
            {runner_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if heartbeat_task in done:
            await heartbeat_task
            raise JobOwnershipError("Lifecycle job heartbeat stopped before runner completion")

        await runner_task
    finally:
        for task in (runner_task, heartbeat_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(runner_task, heartbeat_task, return_exceptions=True)


async def process_one_job(
    session_factory: async_sessionmaker[AsyncSession],
    registry: LifecycleRunnerRegistry,
    *,
    worker_id: str,
    options: WorkerOptions,
    clock: Clock = _utcnow,
    jitter_source: JitterSource = _sample_jitter,
) -> bool:
    """Claim and process at most one job; return whether a job was claimed."""

    async with session_factory() as session:
        claimed = await claim_next_job(
            session,
            worker_id,
            clock(),
            options.lease_seconds,
        )
    if claimed is None:
        return False

    _log(
        "lifecycle_job_claimed",
        job_id=claimed.id,
        operation=claimed.operation.value,
        attempt=claimed.attempt,
        worker_id=worker_id,
    )

    try:
        await _run_with_heartbeats(
            session_factory,
            registry,
            claimed=claimed,
            worker_id=worker_id,
            options=options,
            clock=clock,
        )
    except JobOwnershipError:
        _log(
            "lifecycle_job_ownership_lost",
            job_id=claimed.id,
            operation=claimed.operation.value,
            worker_id=worker_id,
        )
        return True
    except Exception as error:
        sanitized_message = redact_secret_text(str(error))
        jitter = jitter_source(options.retry_jitter_seconds)
        try:
            async with session_factory() as session:
                terminal = await retry_or_fail_job(
                    session,
                    claimed.id,
                    worker_id,
                    clock(),
                    error,
                    expected_attempt=claimed.attempt,
                    retry_base_seconds=options.retry_base_seconds,
                    retry_cap_seconds=options.retry_cap_seconds,
                    retry_jitter_seconds=jitter,
                )
        except JobOwnershipError:
            _log(
                "lifecycle_job_ownership_lost",
                job_id=claimed.id,
                operation=claimed.operation.value,
                worker_id=worker_id,
            )
            return True
        _log(
            "lifecycle_job_failed" if terminal else "lifecycle_job_retry_scheduled",
            job_id=claimed.id,
            operation=claimed.operation.value,
            attempt=claimed.attempt,
            error_code=_error_code(error),
            error_message=sanitized_message,
            worker_id=worker_id,
        )
        return True

    try:
        async with session_factory() as session:
            await complete_job(
                session,
                claimed.id,
                worker_id,
                clock(),
                expected_attempt=claimed.attempt,
            )
    except JobOwnershipError:
        _log(
            "lifecycle_job_ownership_lost",
            job_id=claimed.id,
            operation=claimed.operation.value,
            worker_id=worker_id,
        )
        return True

    _log(
        "lifecycle_job_succeeded",
        job_id=claimed.id,
        operation=claimed.operation.value,
        attempt=claimed.attempt,
        worker_id=worker_id,
    )
    return True


async def run_worker(
    session_factory: async_sessionmaker[AsyncSession],
    registry: LifecycleRunnerRegistry,
    *,
    worker_id: str,
    options: WorkerOptions,
    stop_event: asyncio.Event,
    once: bool,
) -> None:
    """Poll until stopped, or inspect one queue slot in ``once`` mode."""

    _log("lifecycle_worker_started", worker_id=worker_id, once=once)
    while not stop_event.is_set():
        processed = await process_one_job(
            session_factory,
            registry,
            worker_id=worker_id,
            options=options,
        )
        if once:
            break
        if not processed:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=options.poll_seconds)
            except TimeoutError:
                pass
    _log("lifecycle_worker_stopped", worker_id=worker_id)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Conductor lifecycle worker")
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    parser.add_argument("--worker-id", help="Explicit unique worker identity")
    return parser.parse_args(argv)


async def async_main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    registry: LifecycleRunnerRegistry | None = None,
) -> int:
    args = _parse_args(argv)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signum, stop_event.set)

    await run_worker(
        session_factory,
        registry or build_default_registry(),
        worker_id=_worker_id(args.worker_id),
        options=WorkerOptions.from_settings(),
        stop_event=stop_event,
        once=args.once,
    )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
