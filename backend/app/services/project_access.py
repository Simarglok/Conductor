"""Central project visibility and lifecycle-state access gates."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_member import ProjectMember
from app.models.user import User


async def load_ready_project_for_user(
    slug: str,
    user: User,
    db: AsyncSession,
) -> Project:
    """Load a ready project and require membership, without admin bypass."""

    project = (
        await db.execute(
            select(Project).where(
                Project.slug == slug,
                Project.lifecycle_status == ProjectLifecycleStatus.READY,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return project


async def load_project_for_admin(
    slug: str,
    user: User,
    db: AsyncSession,
) -> Project:
    """Load a project in any lifecycle state for an authenticated super admin."""

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required",
        )
    project = (
        await db.execute(select(Project).where(Project.slug == slug))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project
