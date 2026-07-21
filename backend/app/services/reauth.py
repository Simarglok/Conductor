"""Password re-authentication for one-time destructive-action grants."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_token
from app.auth.password import verify_password
from app.config import settings
from app.models.audit_event import AuditEvent
from app.models.project import Project
from app.models.reauth_grant import ReauthGrant
from app.models.user import User

DELETE_ACTION = "project.delete"

_RATE_LIMIT_INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class ReauthError(RuntimeError):
    def __init__(self, status_code: int, public_detail: str) -> None:
        super().__init__(public_detail)
        self.status_code = status_code
        self.public_detail = public_detail


def hash_reauth_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _audit_event(
    *,
    actor: User | None,
    project: Project | None,
    requested_project_id: str,
    outcome: str,
    reason_code: str,
) -> AuditEvent:
    return AuditEvent(
        event_type="auth.reauth",
        actor_user_id=actor.id if actor else None,
        project_id_snapshot=project.id if project else requested_project_id,
        project_name_snapshot=project.name if project else "<unknown>",
        project_slug_snapshot=project.slug if project else "<unknown>",
        correlation_id=uuid4().hex,
        outcome=outcome,
        metadata_json={"reason_code": reason_code},
    )


async def _fail(
    db: AsyncSession,
    *,
    actor: User | None,
    project: Project | None,
    requested_project_id: str,
    reason_code: str,
    status_code: int,
    public_detail: str,
) -> None:
    db.add(
        _audit_event(
            actor=actor,
            project=project,
            requested_project_id=requested_project_id,
            outcome="failed",
            reason_code=reason_code,
        )
    )
    await db.commit()
    raise ReauthError(status_code, public_detail)


async def _increment_limit(redis, key: str) -> int:
    return int(
        await redis.eval(
            _RATE_LIMIT_INCREMENT_SCRIPT,
            1,
            key,
            settings.reauth_rate_limit_window_seconds,
        )
    )


async def _check_rate_limits(redis, *, user_id: str, source_ip: str) -> bool:
    user_count, ip_count = await asyncio.gather(
        _increment_limit(redis, f"reauth:rate:user:{user_id}"),
        _increment_limit(redis, f"reauth:rate:ip:{source_ip}"),
    )
    limit = settings.reauth_rate_limit_attempts
    return user_count <= limit and ip_count <= limit


async def create_reauth_grant(
    db: AsyncSession,
    *,
    redis,
    access_token: str,
    password: str,
    action: str,
    project_id: str,
    source_ip: str,
) -> str:
    """Validate current authority and return a newly issued opaque grant once."""

    payload = decode_token(access_token)
    if payload is None or payload.get("type") != "access" or not payload.get("sub"):
        raise ReauthError(401, "Invalid or expired token")

    user_id = str(payload["sub"])
    actor = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()

    try:
        allowed = await _check_rate_limits(redis, user_id=user_id, source_ip=source_ip)
    except Exception:
        await _fail(
            db,
            actor=actor,
            project=project,
            requested_project_id=project_id,
            reason_code="rate_limit_unavailable",
            status_code=503,
            public_detail="Re-authentication temporarily unavailable",
        )
        raise AssertionError("unreachable")

    checks = (
        (not allowed, "rate_limited", 429, "Too many re-authentication attempts"),
        (actor is None, "actor_not_found", 403, "Re-authentication is not permitted"),
        (actor is not None and not actor.is_active, "inactive_actor", 403, "Re-authentication is not permitted"),
        (actor is not None and not actor.is_admin, "not_super_admin", 403, "Re-authentication is not permitted"),
        (action != DELETE_ACTION, "invalid_action", 400, "Unsupported re-authentication action"),
        (project is None, "project_not_found", 404, "Project not found"),
    )
    for denied, reason, status_code, public_detail in checks:
        if denied:
            await _fail(
                db,
                actor=actor,
                project=project,
                requested_project_id=project_id,
                reason_code=reason,
                status_code=status_code,
                public_detail=public_detail,
            )

    assert actor is not None and project is not None
    if not verify_password(password, actor.hashed_password):
        await _fail(
            db,
            actor=actor,
            project=project,
            requested_project_id=project_id,
            reason_code="invalid_password",
            status_code=401,
            public_detail="Re-authentication failed",
        )

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        ReauthGrant(
            token_hash=hash_reauth_token(token),
            user_id=actor.id,
            action=DELETE_ACTION,
            project_id=project.id,
            expires_at=now + timedelta(seconds=settings.reauth_grant_ttl_seconds),
        )
    )
    db.add(
        _audit_event(
            actor=actor,
            project=project,
            requested_project_id=project_id,
            outcome="succeeded",
            reason_code="granted",
        )
    )
    await db.commit()
    return token