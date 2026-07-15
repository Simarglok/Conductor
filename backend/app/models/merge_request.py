from __future__ import annotations

from datetime import datetime

from app.models.base import Base, new_uuid
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import User


class MergeRequest(Base):
    __tablename__ = "merge_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False
    )
    source_branch: Mapped[str] = mapped_column(String(128), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    merge_commit_sha: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    author: Mapped["User"] = relationship()