from __future__ import annotations

import re
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.auth.permissions import require_super_admin
from app.database import get_db_session
from app.models.environment import Environment
from app.models.git_config import GitConfig
from app.models.project import Project, ProjectLifecycleStatus
from app.models.project_member import ProjectMember
from app.models.role import Role
from app.models.user import User
from app.schemas.member import AddMemberRequest, ChangeRoleRequest, MemberResponse
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectOperationResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.schemas.settings import (
    EnvironmentCreateRequest,
    EnvironmentResponse,
    EnvironmentUpdateRequest,
    GitConfigResponse,
    GitConfigUpdateRequest,
    ProjectSettingsResponse,
    ProjectSettingsUpdateRequest,
)
from app.services.crypto import CredentialsEncryptionNotConfigured, encrypt_token
from app.services.project_access import load_ready_project_for_user
from app.services.project_operations import (
    DuplicateProjectSlugError,
    IdempotencyKeyConflictError,
    create_project_operation,
)
from app.services.secret_redaction import redact_secret_text

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
    stmt = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user.id,
            Project.lifecycle_status == ProjectLifecycleStatus.READY,
        )
        .order_by(Project.created_at.desc())
    )

    if search:
        stmt = stmt.where(Project.name.ilike(f"%{search}%"))

    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Batch-resolve roles for current user
    member_map: dict[str, str] = {}
    if projects and not user.is_admin:
        members_result = await db.execute(
            select(ProjectMember)
            .where(
                ProjectMember.user_id == user.id,
                ProjectMember.project_id.in_([p.id for p in projects]),
            )
            .options(selectinload(ProjectMember.role))
        )
        for m in members_result.scalars():
            member_map[m.project_id] = m.role.name if m.role else "member"

    response = []
    for p in projects:
        count_result = await db.execute(
            select(func.count()).select_from(ProjectMember).where(
                ProjectMember.project_id == p.id
            )
        )
        member_count = count_result.scalar() or 0
        role = member_map.get(p.id) if not user.is_admin else "super_admin"
        response.append(
            ProjectResponse(
                id=p.id,
                name=p.name,
                slug=p.slug,
                description=p.description,
                self_approve_enabled=p.self_approve_enabled,
                lifecycle_status=p.lifecycle_status,
                created_at=p.created_at,
                updated_at=p.updated_at,
                member_count=member_count,
                role=role,
            )
        )
    return response


@router.post(
    "/projects",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_project(
    body: ProjectCreateRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    slug = body.slug or _slugify(body.name)
    try:
        project, operation = await create_project_operation(
            db,
            name=body.name,
            slug=slug,
            description=body.description,
            requested_by=user,
            idempotency_key=str(idempotency_key),
        )
    except CredentialsEncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=redact_secret_text(str(exc)),
        ) from exc
    except IdempotencyKeyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key already used with a different request",
        ) from exc
    except DuplicateProjectSlugError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project slug already exists",
        ) from exc

    return ProjectCreateResponse(
        project=ProjectResponse(
            id=project.id,
            name=project.name,
            slug=project.slug,
            description=project.description,
            self_approve_enabled=project.self_approve_enabled,
            lifecycle_status=project.lifecycle_status,
            created_at=project.created_at,
            updated_at=project.updated_at,
            member_count=1,
            role="super_admin",
        ),
        operation=ProjectOperationResponse(
            id=operation.id,
            operation=operation.operation,
            status=operation.status,
        ),
    )


@router.get("/projects/{slug}", response_model=ProjectResponse)
async def get_project(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)

    # Check access
    await _ensure_access(user, project.id, db)

    count_result = await db.execute(
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    )

    role = "super_admin" if user.is_admin else None
    if not user.is_admin:
        m_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id, ProjectMember.user_id == user.id,
            ).options(selectinload(ProjectMember.role))
        )
        m = m_result.scalar_one_or_none()
        if m:
            role = m.role.name

    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        self_approve_enabled=project.self_approve_enabled,
        lifecycle_status=project.lifecycle_status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        member_count=count_result.scalar() or 0,
        role=role,
    )


@router.patch("/projects/{slug}", response_model=ProjectResponse)
async def update_project(
    slug: str,
    body: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)

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
        lifecycle_status=project.lifecycle_status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        member_count=count_result.scalar() or 0,
        role="super_admin" if user.is_admin else "project_admin",
    )


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


# ─── Members ───


@router.get("/projects/{slug}/members", response_model=list[MemberResponse])
async def list_members(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)

    await _ensure_access(user, project.id, db)

    stmt = (
        select(ProjectMember)
        .where(ProjectMember.project_id == project.id)
        .options(selectinload(ProjectMember.user), selectinload(ProjectMember.role))
        .order_by(ProjectMember.created_at)
    )
    result = await db.execute(stmt)
    members = result.scalars().all()

    return [
        MemberResponse(
            user_id=m.user.id,
            email=m.user.email,
            display_name=m.user.display_name,
            role_name=m.role.name,
            role_id=m.role.id,
            joined_at=m.created_at,
        )
        for m in members
    ]


@router.post("/projects/{slug}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    slug: str,
    body: AddMemberRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)

    await _ensure_admin_access(user, project.id, db)

    # Find user by email
    user_result = await db.execute(
        select(User).where(User.email == body.email)
    )
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found by email")

    # Check not already a member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == target_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member")

    # Find role
    role_result = await db.execute(
        select(Role).where(Role.name == body.role_name)
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role_name}' not found")

    member = ProjectMember(
        project_id=project.id,
        user_id=target_user.id,
        role_id=role.id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    return MemberResponse(
        user_id=target_user.id,
        email=target_user.email,
        display_name=target_user.display_name,
        role_name=role.name,
        role_id=role.id,
        joined_at=member.created_at,
    )


@router.patch("/projects/{slug}/members/{user_id}", response_model=MemberResponse)
async def change_member_role(
    slug: str,
    user_id: str,
    body: ChangeRoleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)

    await _ensure_admin_access(user, project.id, db)

    # Find role
    role_result = await db.execute(
        select(Role).where(Role.name == body.role_name)
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role_name}' not found")

    # Find member
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member.role_id = role.id
    await db.commit()
    await db.refresh(member)

    # Fetch user+role for response
    u_result = await db.execute(select(User).where(User.id == user_id))
    target_user = u_result.scalar_one()

    return MemberResponse(
        user_id=target_user.id,
        email=target_user.email,
        display_name=target_user.display_name,
        role_name=role.name,
        role_id=role.id,
        joined_at=member.created_at,
    )


@router.delete("/projects/{slug}/members/{user_id}", status_code=204)
async def remove_member(
    slug: str,
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)

    await _ensure_admin_access(user, project.id, db)

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Prevent removing the last project_admin
    if member.role_id == "project_admin":
        admin_count = await db.execute(
            select(func.count()).select_from(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.role_id == "project_admin",
            )
        )
        count_val = admin_count.scalar() or 0
        if count_val <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot remove the last project admin"
            )

    await db.delete(member)
    await db.commit()


# ─── Settings ───


@router.get("/projects/{slug}/git", response_model=GitConfigResponse)
async def get_git_config(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_access(user, project.id, db)

    git_result = await db.execute(
        select(GitConfig).where(GitConfig.project_id == project.id)
    )
    config = git_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Git config not found")

    return GitConfigResponse(
        repo_url=config.repo_url,
        auth_type=config.auth_type,
        default_branch=config.default_branch,
        dbt_path=config.dbt_path,
        dags_path=config.dags_path,
        has_credentials=bool(config.credentials_encrypted),
        has_token=config.auth_type == "token" and bool(config.credentials_encrypted),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put("/projects/{slug}/git", response_model=GitConfigResponse)
async def update_git_config(
    slug: str,
    body: GitConfigUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_admin_access(user, project.id, db)

    git_result = await db.execute(
        select(GitConfig).where(GitConfig.project_id == project.id)
    )
    config = git_result.scalar_one_or_none()
    if not config:
        config = GitConfig(project_id=project.id, repo_url="", auth_type="https")
        db.add(config)
        await db.flush()

    previous_auth_type = config.auth_type
    effective_auth_type = body.auth_type or previous_auth_type
    credential = body.token if body.token is not None else body.credentials
    if body.token is not None and effective_auth_type != "token":
        raise HTTPException(status_code=422, detail="Token requires token authentication")
    if body.credentials is not None and effective_auth_type not in ("token", "ssh"):
        raise HTTPException(
            status_code=422,
            detail="Credentials require token or SSH authentication",
        )
    if effective_auth_type == "token" and previous_auth_type != "token" and credential is None:
        raise HTTPException(
            status_code=422,
            detail="A token is required when enabling token authentication",
        )

    update_data = body.model_dump(
        exclude_unset=True,
        exclude={"token", "credentials", "webhook_secret"},
    )
    if update_data:
        for key, value in update_data.items():
            setattr(config, key, value)

    if config.auth_type == "token":
        parsed_repo_url = urlsplit(config.repo_url)
        if parsed_repo_url.scheme != "https" or not parsed_repo_url.netloc:
            raise HTTPException(
                status_code=422,
                detail="Token authentication requires an HTTPS repository URL",
            )

    # Handle encrypted fields
    try:
        if credential is not None:
            config.credentials_encrypted = encrypt_token(credential)
        elif body.auth_type is not None and body.auth_type != previous_auth_type:
            config.credentials_encrypted = None
        if body.webhook_secret is not None:
            config.webhook_secret_encrypted = encrypt_token(body.webhook_secret)
    except CredentialsEncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail=redact_secret_text(str(exc)),
        ) from exc

    if config.auth_type == "token" and not config.credentials_encrypted:
        raise HTTPException(status_code=422, detail="Token authentication requires a token")

    await db.commit()
    await db.refresh(config)

    return GitConfigResponse(
        repo_url=config.repo_url,
        auth_type=config.auth_type,
        default_branch=config.default_branch,
        dbt_path=config.dbt_path,
        dags_path=config.dags_path,
        has_credentials=bool(config.credentials_encrypted),
        has_token=config.auth_type == "token" and bool(config.credentials_encrypted),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.get("/projects/{slug}/environments", response_model=list[EnvironmentResponse])
async def list_environments(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_access(user, project.id, db)

    env_result = await db.execute(
        select(Environment)
        .where(Environment.project_id == project.id)
        .order_by(Environment.name)
    )
    return env_result.scalars().all()


@router.post("/projects/{slug}/environments", response_model=EnvironmentResponse, status_code=201)
async def create_environment(
    slug: str,
    body: EnvironmentCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_admin_access(user, project.id, db)

    env = Environment(
        project_id=project.id,
        name=body.name,
        branch_name=body.branch_name,
        is_protected=body.is_protected,
    )
    db.add(env)
    await db.commit()
    await db.refresh(env)
    return env


@router.patch("/projects/{slug}/environments/{env_id}", response_model=EnvironmentResponse)
async def update_environment(
    slug: str,
    env_id: str,
    body: EnvironmentUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_admin_access(user, project.id, db)

    env_result = await db.execute(
        select(Environment).where(
            Environment.id == env_id, Environment.project_id == project.id
        )
    )
    env = env_result.scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(env, key, value)
        await db.commit()
        await db.refresh(env)
    return env


@router.delete("/projects/{slug}/environments/{env_id}", status_code=204)
async def delete_environment(
    slug: str,
    env_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_admin_access(user, project.id, db)

    env_result = await db.execute(
        select(Environment).where(
            Environment.id == env_id, Environment.project_id == project.id
        )
    )
    env = env_result.scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    await db.delete(env)
    await db.commit()


@router.get("/projects/{slug}/settings", response_model=ProjectSettingsResponse)
async def get_settings(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_access(user, project.id, db)

    return ProjectSettingsResponse(
        self_approve_enabled=project.self_approve_enabled,
    )


@router.patch("/projects/{slug}/settings", response_model=ProjectSettingsResponse)
async def update_settings(
    slug: str,
    body: ProjectSettingsUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    project = await load_ready_project_for_user(slug, user, db)
    await _ensure_admin_access(user, project.id, db)

    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(project, key, value)
        await db.commit()
        await db.refresh(project)

    return ProjectSettingsResponse(
        self_approve_enabled=project.self_approve_enabled,
    )