from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.auth.permissions import require_super_admin
from app.database import get_db_session
from app.models.airflow_instance import AirflowInstance, AirflowInstanceStatus
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.admin import (
    AdminProjectResponse,
    PermissionCreateRequest,
    PermissionItem,
    RoleCreateRequest,
    RoleItem,
    RoleUpdateRequest,
    UserListItem,
    UserUpdateRequest,
)

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