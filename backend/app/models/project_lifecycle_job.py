from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_uuid

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class LifecycleOperation(StrEnum):
    PROVISION = "provision"
    DELETE = "delete"
    RECONCILE = "reconcile"


class LifecycleJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProjectLifecycleJob(Base):
    __tablename__ = "project_lifecycle_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[LifecycleOperation] = mapped_column(
        Enum(
            LifecycleOperation,
            name="project_lifecycle_operation",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    status: Mapped[LifecycleJobStatus] = mapped_column(
        Enum(
            LifecycleJobStatus,
            name="project_lifecycle_job_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=LifecycleJobStatus.PENDING,
        server_default=sa_text("'pending'"),
    )
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="lifecycle_jobs")
    requester: Mapped[User | None] = relationship(foreign_keys=[requested_by])

    __table_args__ = (
        Index(
            "uq_project_lifecycle_jobs_active_project",
            "project_id",
            unique=True,
            postgresql_where=sa_text("status IN ('pending', 'running', 'retry_wait')"),
        ),
    )
