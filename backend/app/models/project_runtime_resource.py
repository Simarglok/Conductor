from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func, text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_uuid

if TYPE_CHECKING:
    from app.models.project import Project


class RuntimeResourceKind(StrEnum):
    CONTAINER = "container"
    VOLUME = "volume"
    NETWORK = "network"
    DATABASE = "database"
    DATABASE_ROLE = "database_role"
    PROXY_ROUTE = "proxy_route"


class ProjectRuntimeResource(Base):
    __tablename__ = "project_runtime_resources"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "generation",
            "logical_name",
            name="uq_project_runtime_resources_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_kind: Mapped[RuntimeResourceKind] = mapped_column(
        Enum(
            RuntimeResourceKind,
            name="project_runtime_resource_kind",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    logical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_status: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="runtime_resources")
