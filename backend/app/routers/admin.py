from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.auth.permissions import require_super_admin
from app.database import get_db_session
from app.models.airflow_instance import AirflowInstance, AirflowInstanceStatus
from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_lifecycle_job import (
    LifecycleJobStatus,
    LifecycleOperation,
    ProjectLifecycleJob,
)
from app.models.project_member import ProjectMember
from app.models.reauth_grant import ReauthGrant
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.admin import (
    AdminProjectResponse,
    PermissionCreateRequest,
    PermissionItem,
    ProjectDeleteOperationResponse,
    ProjectDeleteRequest,
    RoleCreateRequest,
    RoleItem,
    RoleUpdateRequest,
    UserListItem,
    UserUpdateRequest,
)
from app.services.reauth import DELETE_ACTION, hash_reauth_token

router = APIRouter(dependencies=[Depends(require_super_admin)])


# ─── Users ───


@router.get("/admin/users", response_model=list[UserListItem])
async def list_users(
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.get("/admin/users/{user_id}", response_model=UserListItem)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/admin/users/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: str, body: UserUpdateRequest, db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(User).where(User.id == user_id).values(**update_data)
        )
        await db.commit()
        await db.refresh(user)
    return user


@router.delete("/admin/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str, db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()


# ─── Roles ───


@router.get("/admin/roles", response_model=list[RoleItem])
async def list_roles(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Role).order_by(Role.name))
    return result.scalars().all()


@router.post("/admin/roles", response_model=RoleItem, status_code=201)
async def create_role(
    body: RoleCreateRequest, db: AsyncSession = Depends(get_db_session)
):
    role = Role(name=body.name, description=body.description, is_system=False)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.patch("/admin/roles/{role_id}", response_model=RoleItem)
async def update_role(
    role_id: str, body: RoleUpdateRequest, db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(Role).where(Role.id == role_id).values(**update_data)
        )
        await db.commit()
        await db.refresh(role)
    return role


@router.delete("/admin/roles/{role_id}", status_code=204)
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=400, detail="Cannot delete system role"
        )
    await db.delete(role)
    await db.commit()


# ─── Permissions ───


@router.get(
    "/admin/roles/{role_id}/permissions", response_model=list[PermissionItem]
)
async def list_permissions(
    role_id: str, db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(Permission).where(Permission.role_id == role_id)
    )
    return result.scalars().all()


@router.post(
    "/admin/roles/{role_id}/permissions",
    response_model=PermissionItem,
    status_code=201,
)
async def add_permission(
    role_id: str,
    body: PermissionCreateRequest,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Role).where(Role.id == role_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Role not found")

    perm = Permission(
        role_id=role_id,
        resource=body.resource,
        action=body.action,
        constraint=body.constraint,
    )
    db.add(perm)
    await db.commit()
    await db.refresh(perm)
    return perm


@router.delete(
    "/admin/roles/{role_id}/permissions/{perm_id}",
    status_code=204,
)
async def remove_permission(
    role_id: str,
    perm_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Permission).where(
            Permission.id == perm_id, Permission.role_id == role_id
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")
    await db.delete(perm)
    await db.commit()


# ─── Projects ───


@router.get("/admin/projects", response_model=list[AdminProjectResponse])
async def list_admin_projects(
    db: AsyncSession = Depends(get_db_session),
):
    """List all projects with member counts and Airflow status (super_admin only)."""
    result = await db.execute(
        select(Project).options(
            selectinload(Project.airflow_instance),
            selectinload(Project.members),
        )
    )
    projects = result.scalars().all()
    return [
        AdminProjectResponse(
            id=p.id,
            name=p.name,
            slug=p.slug,
            member_count=len(p.members),
            airflow_status=p.airflow_instance.status.value if p.airflow_instance else "not_provisioned",
            created_at=p.created_at,
        )
        for p in projects
    ]


_DELETE_INITIAL_STATES = {
    ProjectLifecycleStatus.READY,
    ProjectLifecycleStatus.PROVISION_FAILED,
    ProjectLifecycleStatus.DELETION_FAILED,
}
_DELETE_MAX_ATTEMPTS = 5


def _delete_fingerprint(
    *,
    actor_id: str,
    project_id: str,
    slug: str,
    confirmation_slug: str,
) -> str:
    canonical = json.dumps(
        {
            "actor_id": actor_id,
            "confirmation_slug": confirmation_slug,
            "operation": "delete",
            "project_id": project_id,
            "slug": slug,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _delete_response(operation: ProjectLifecycleJob) -> ProjectDeleteOperationResponse:
    return ProjectDeleteOperationResponse(
        id=operation.id,
        operation="delete",
        status=operation.status.value,
    )


@router.delete(
    "/admin/projects/{slug}",
    response_model=ProjectDeleteOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_project_deletion(
    slug: str,
    body: ProjectDeleteRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    reauth_token: str | None = Header(default=None, alias="X-Reauth-Token"),
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Consume a one-time grant and atomically enqueue durable teardown."""

    key = str(idempotency_key)
    try:
        project = (
            await db.execute(
                select(Project).where(Project.slug == slug).with_for_update()
            )
        ).scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        fingerprint = _delete_fingerprint(
            actor_id=actor.id,
            project_id=project.id,
            slug=slug,
            confirmation_slug=body.confirmation_slug,
        )
        existing = (
            await db.execute(
                select(ProjectLifecycleJob).where(
                    ProjectLifecycleJob.idempotency_key == key
                )
            )
        ).scalar_one_or_none()

        if (
            existing is not None
            and existing.project_id == project.id
            and existing.operation is LifecycleOperation.DELETE
            and existing.requested_by == actor.id
            and existing.request_fingerprint == fingerprint
        ):
            response = _delete_response(existing)
            await db.rollback()
            return response

        if project.lifecycle_status is ProjectLifecycleStatus.DELETING:
            raise HTTPException(
                status_code=409,
                detail="Project deletion already has a different request",
            )

        if project.lifecycle_status not in _DELETE_INITIAL_STATES:
            raise HTTPException(
                status_code=409,
                detail="Project is not in a deletable state",
            )
        if body.confirmation_slug != slug:
            raise HTTPException(
                status_code=400,
                detail="Project slug confirmation does not match",
            )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key already used with a different request",
            )
        if not reauth_token:
            raise HTTPException(
                status_code=403,
                detail="Invalid re-authentication grant",
            )

        failed_deletion_boundary = None
        if project.lifecycle_status is ProjectLifecycleStatus.DELETION_FAILED:
            latest_failed_delete = (
                await db.execute(
                    select(ProjectLifecycleJob)
                    .where(
                        ProjectLifecycleJob.project_id == project.id,
                        ProjectLifecycleJob.operation == LifecycleOperation.DELETE,
                        ProjectLifecycleJob.status == LifecycleJobStatus.FAILED,
                    )
                    .order_by(ProjectLifecycleJob.created_at.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            failed_deletion_boundary = (
                latest_failed_delete.finished_at
                if latest_failed_delete is not None
                and latest_failed_delete.finished_at is not None
                else project.updated_at
            )

        grant = (
            await db.execute(
                select(ReauthGrant)
                .where(ReauthGrant.token_hash == hash_reauth_token(reauth_token))
                .with_for_update()
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if (
            grant is None
            or grant.user_id != actor.id
            or grant.action != DELETE_ACTION
            or grant.project_id != project.id
            or grant.consumed_at is not None
            or grant.expires_at <= now
            or (
                project.lifecycle_status is ProjectLifecycleStatus.DELETION_FAILED
                and (
                    failed_deletion_boundary is None
                    or grant.created_at is None
                    or grant.created_at <= failed_deletion_boundary
                )
            )
        ):
            raise HTTPException(
                status_code=403,
                detail="Invalid re-authentication grant",
            )

        correlation_id = uuid4().hex
        operation = ProjectLifecycleJob(
            project_id=project.id,
            operation=LifecycleOperation.DELETE,
            status=LifecycleJobStatus.PENDING,
            attempt=0,
            max_attempts=_DELETE_MAX_ATTEMPTS,
            available_at=now,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            requested_by=actor.id,
            correlation_id=correlation_id,
        )
        grant.consumed_at = now
        project.lifecycle_status = ProjectLifecycleStatus.DELETING
        db.add(operation)
        await db.flush()
        db.add(
            AuditEvent(
                event_type="project.delete.requested",
                actor_user_id=actor.id,
                project_id_snapshot=project.id,
                project_name_snapshot=project.name,
                project_slug_snapshot=project.slug,
                correlation_id=correlation_id,
                outcome="requested",
                metadata_json={"operation_id": operation.id},
            )
        )
        await db.commit()
        return _delete_response(operation)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        replay = (
            await db.execute(
                select(ProjectLifecycleJob).where(
                    ProjectLifecycleJob.idempotency_key == key
                )
            )
        ).scalar_one_or_none()
        if replay is not None:
            if (
                replay.operation is LifecycleOperation.DELETE
                and replay.requested_by == actor.id
                and replay.request_fingerprint
                == _delete_fingerprint(
                    actor_id=actor.id,
                    project_id=replay.project_id,
                    slug=slug,
                    confirmation_slug=body.confirmation_slug,
                )
            ):
                return _delete_response(replay)
            raise HTTPException(
                status_code=409,
                detail="Idempotency key already used with a different request",
            ) from None
        raise HTTPException(
            status_code=500,
            detail="Project deletion request failed",
        ) from None
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Project deletion request failed",
        ) from None