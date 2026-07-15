from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.auth.permissions import require_super_admin
from app.database import get_db_session
from app.models.environment import Environment
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.role import Role
from app.models.user import User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
)

router = APIRouter()


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip().replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    search: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if user.is_admin:
        stmt = select(Project).order_by(Project.created_at.desc())
    else:
        # Only projects where user is a member
        stmt = (
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
            .order_by(Project.created_at.desc())
        )

    if search:
        stmt = stmt.where(Project.name.ilike(f"%{search}%"))

    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Enrich with member count
    response = []
    for p in projects:
        count_result = await db.execute(
            select(func.count()).select_from(ProjectMember).where(
                ProjectMember.project_id == p.id
            )
        )
        member_count = count_result.scalar() or 0
        response.append(
            ProjectResponse(
                id=p.id,
                name=p.name,
                slug=p.slug,
                description=p.description,
                self_approve_enabled=p.self_approve_enabled,
                created_at=p.created_at,
                updated_at=p.updated_at,
                member_count=member_count,
            )
        )
    return response


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreateRequest,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    slug = body.slug or _slugify(body.name)

    # Check slug uniqueness
    existing = await db.execute(select(Project).where(Project.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Project slug already exists")

    project = Project(
        name=body.name,
        slug=slug,
        description=body.description,
    )
    db.add(project)
    await db.flush()

    # Auto-create default environments
    envs = [
        Environment(
            project_id=project.id,
            name="production",
            branch_name="main",
            is_protected=True,
            is_active=True,
        ),
        Environment(
            project_id=project.id,
            name="development",
            branch_name="develop",
            is_protected=False,
            is_active=True,
        ),
    ]
    for env in envs:
        db.add(env)

    # Auto-assign creator as project_admin
    role_result = await db.execute(
        select(Role).where(Role.name == "project_admin")
    )
    admin_role = role_result.scalar_one_or_none()

    if admin_role:
        member = ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role_id=admin_role.id,
        )
        db.add(member)

    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        self_approve_enabled=project.self_approve_enabled,
        created_at=project.created_at,
        updated_at=project.updated_at,
        member_count=1,
    )


@router.get("/projects/{slug}", response_model=ProjectResponse)
async def get_project(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access
    await _ensure_access(user, project.id, db)

    count_result = await db.execute(
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        self_approve_enabled=project.self_approve_enabled,
        created_at=project.created_at,
        updated_at=project.updated_at,
        member_count=count_result.scalar() or 0,
    )


@router.patch("/projects/{slug}", response_model=ProjectResponse)
async def update_project(
    slug: str,
    body: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await _ensure_admin_access(user, project.id, db)

    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(Project).where(Project.id == project.id).values(**update_data)
        )
        await db.commit()
        await db.refresh(project)

    count_result = await db.execute(
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        self_approve_enabled=project.self_approve_enabled,
        created_at=project.created_at,
        updated_at=project.updated_at,
        member_count=count_result.scalar() or 0,
    )


@router.delete("/projects/{slug}", status_code=204)
async def delete_project(
    slug: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)
    await db.commit()


# ─── Helpers ───


async def _ensure_access(user: User, project_id: str, db: AsyncSession):
    """Check user is a member of the project, or is Super Admin."""
    if user.is_admin:
        return
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")


async def _ensure_admin_access(user: User, project_id: str, db: AsyncSession):
    """Check user has admin role in the project, or is Super Admin."""
    if user.is_admin:
        return
    result = await db.execute(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
        .options(selectinload(ProjectMember.role))
    )
    member = result.scalar_one_or_none()
    if not member or member.role.name not in ("project_admin",):
        raise HTTPException(status_code=403, detail="Project admin access required")