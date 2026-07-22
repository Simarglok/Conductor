from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DDL, DateTime, ForeignKey, String, event, func, text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_uuid

if TYPE_CHECKING:
    from app.models.user import User


class AuditEvent(Base):
    """Immutable, secret-free audit snapshot that survives project deletion."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id_snapshot: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    project_name_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    project_slug_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])


_CREATE_APPEND_ONLY_FUNCTION = DDL(
    """
    CREATE OR REPLACE FUNCTION conductor_prevent_audit_event_mutation()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
        -- ON DELETE SET NULL on users is the sole allowed mutation. A direct
        -- UPDATE invokes this trigger at depth 1; the FK action invokes it as
        -- a nested trigger. The payload and snapshots must remain unchanged.
        IF TG_OP = 'UPDATE'
           AND pg_trigger_depth() > 1
           AND OLD.actor_user_id IS NOT NULL
           AND NEW.actor_user_id IS NULL
           AND (to_jsonb(NEW) - 'actor_user_id') = (to_jsonb(OLD) - 'actor_user_id')
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = '55000';
    END;
    $$
    """
)
_CREATE_APPEND_ONLY_TRIGGER = DDL(
    """
    CREATE TRIGGER trg_audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION conductor_prevent_audit_event_mutation()
    """
)
_CREATE_TRUNCATE_BLOCKER_TRIGGER = DDL(
    """
    CREATE TRIGGER trg_audit_events_append_only_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION conductor_prevent_audit_event_mutation()
    """
)
_DROP_APPEND_ONLY_FUNCTION = DDL(
    "DROP FUNCTION IF EXISTS conductor_prevent_audit_event_mutation() CASCADE"
)

event.listen(
    AuditEvent.__table__,
    "after_create",
    _CREATE_APPEND_ONLY_FUNCTION.execute_if(dialect="postgresql"),
)
event.listen(
    AuditEvent.__table__,
    "after_create",
    _CREATE_APPEND_ONLY_TRIGGER.execute_if(dialect="postgresql"),
)
event.listen(
    AuditEvent.__table__,
    "after_create",
    _CREATE_TRUNCATE_BLOCKER_TRIGGER.execute_if(dialect="postgresql"),
)
event.listen(
    AuditEvent.__table__,
    "after_drop",
    _DROP_APPEND_ONLY_FUNCTION.execute_if(dialect="postgresql"),
)
