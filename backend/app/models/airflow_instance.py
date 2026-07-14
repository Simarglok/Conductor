from __future__ import annotations
import enum
from datetime import datetime
from app.models.base import Base, new_uuid
from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class AirflowInstanceStatus(str, enum.Enum):
    creating = "creating"
    running = "running"
    stopped = "stopped"
    failed = "failed"


class AirflowInstance(Base):
    __tablename__ = "airflow_instances"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    internal_url: Mapped[str] = mapped_column(String(256), nullable=False)
    external_url: Mapped[str] = mapped_column(String(256), nullable=True)
    db_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AirflowInstanceStatus] = mapped_column(
        SQLEnum(AirflowInstanceStatus, name="airflowstatus"),
        default=AirflowInstanceStatus.creating,
        server_default="creating",
    )
    admin_user: Mapped[str] = mapped_column(String(128), nullable=False)
    admin_password_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    dev_user: Mapped[str] = mapped_column(String(128), nullable=False)
    dev_password_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    viewer_user: Mapped[str] = mapped_column(String(128), nullable=False)
    viewer_password_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )