from __future__ import annotations
from datetime import datetime
from app.models.base import Base, new_uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func, text as sa_text
from sqlalchemy.orm import Mapped, mapped_column


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_protected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa_text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_env_name"),
    )