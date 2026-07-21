from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.models.base import Base, new_uuid
from sqlalchemy import Boolean, DateTime, Enum, String, Text, func, text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.project_deployment import ProjectDeployment
    from app.models.project_lifecycle_job import ProjectLifecycleJob
    from app.models.project_member import ProjectMember
    from app.models.project_runtime_resource import ProjectRuntimeResource
    from app.models.reauth_grant import ReauthGrant


class ProjectLifecycleStatus(StrEnum):
    PROVISIONING = "provisioning"
    READY = "ready"
    PROVISION_FAILED = "provision_failed"
    DELETING = "deleting"
    DELETION_FAILED = "deletion_failed"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    self_approve_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_text("false")
    )
    lifecycle_status: Mapped[ProjectLifecycleStatus] = mapped_column(
        Enum(
            ProjectLifecycleStatus,
            name="project_lifecycle_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=ProjectLifecycleStatus.PROVISIONING,
        server_default=sa_text("'provisioning'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    deployment: Mapped["ProjectDeployment | None"] = relationship(
        "ProjectDeployment",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    runtime_resources: Mapped[list["ProjectRuntimeResource"]] = relationship(
        "ProjectRuntimeResource",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    lifecycle_jobs: Mapped[list["ProjectLifecycleJob"]] = relationship(
        "ProjectLifecycleJob",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reauth_grants: Mapped[list["ReauthGrant"]] = relationship(
        "ReauthGrant",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    airflow_instance: Mapped["AirflowInstance | None"] = relationship(
        "AirflowInstance", back_populates="project", uselist=False
    )