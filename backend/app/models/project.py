from __future__ import annotations
from datetime import datetime
from app.models.base import Base, new_uuid
from sqlalchemy import Boolean, DateTime, String, Text, func, text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    self_approve_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_text("false")
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
    airflow_instance: Mapped["AirflowInstance | None"] = relationship(
        "AirflowInstance", back_populates="project", uselist=False
    )