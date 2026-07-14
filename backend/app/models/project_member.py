from __future__ import annotations
from datetime import datetime
from app.models.base import Base, new_uuid
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ProjectMember(Base):
    __tablename__ = "project_members"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()
    role: Mapped["Role"] = relationship()