from __future__ import annotations
from datetime import datetime
from app.models.base import Base, new_uuid
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class GitConfig(Base):
    __tablename__ = "git_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "https" or "ssh"
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    dbt_path: Mapped[str] = mapped_column(String(256), default="dbt/")
    dags_path: Mapped[str] = mapped_column(String(256), default="dags/")
    webhook_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )