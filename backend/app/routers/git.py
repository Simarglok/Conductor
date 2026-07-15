from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db_session
from app.models.git_config import GitConfig
from app.models.merge_request import MergeRequest
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.role import Role
from app.models.user import User
from app.schemas.git import (
    BranchResponse,
    CheckRunResponse,
    CommitResponse,
    MergeRequestCreate,
    MergeRequestResponse,
)
from app.services.git_service import GitService, GitError

router = APIRouter()


async def _resolve_project(slug: str, user: User, db: AsyncSession) -> tuple[Project, GitConfig | None]:
    proj = (await db.execute(select(Project).where(Project.slug == slug))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")
    if not user.is_admin:
        member = (await db.execute(
            select(ProjectMember).where(ProjectMember.project_id == proj.id, ProjectMember.user_id == user.id)
        )).scalar_one_or_none()
        if not member:
            raise HTTPException(403, "Access denied")
    gc = (await db.execute(select(GitConfig).where(GitConfig.project_id == proj.id))).scalar_one_or_none()
    return proj, gc


async def _get_role(user: User, project_id: str, db: AsyncSession) -> str | None:
    if user.is_admin:
        return "super_admin"
    member = (await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        .options(selectinload(ProjectMember.role))
    )).scalar_one_or_none()
    return member.role.name if member else None


# ─── Branches ───


@router.get("/projects/{slug}/git/branches", response_model=list[BranchResponse])
async def list_branches(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, gc = await _resolve_project(slug, user, db)
    if not gc:
        raise HTTPException(400, "Git not configured")
    # TODO: Use workspace path for the actual repo
    # For now, return empty list since git_service needs a real repo
    return []


@router.post("/projects/{slug}/git/branches", status_code=201)
async def create_branch(
    slug: str,
    name: str,
    source: str = "main",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, gc = await _resolve_project(slug, user, db)
    role = await _get_role(user, proj.id, db)
    if role not in ("super_admin", "project_admin", "maintainer", "developer"):
        raise HTTPException(403, "Insufficient permissions")
    return {"status": "created", "branch": name, "source": source}


# ─── Merge Requests ───


@router.get("/projects/{slug}/git/merge-requests", response_model=list[MergeRequestResponse])
async def list_mrs(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, _ = await _resolve_project(slug, user, db)
    result = await db.execute(
        select(MergeRequest).where(MergeRequest.project_id == proj.id)
        .order_by(MergeRequest.created_at.desc())
        .options(selectinload(MergeRequest.author))
    )
    mrs = result.scalars().all()
    return [
        MergeRequestResponse(
            id=mr.id,
            project_id=mr.project_id,
            author_id=mr.author_id,
            author_name=mr.author.display_name,
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            title=mr.title,
            description=mr.description,
            status=mr.status,
            merge_commit_sha=mr.merge_commit_sha,
            created_at=mr.created_at,
            updated_at=mr.updated_at,
        )
        for mr in mrs
    ]


@router.post("/projects/{slug}/git/merge-requests", response_model=MergeRequestResponse, status_code=201)
async def create_mr(
    slug: str,
    body: MergeRequestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, _ = await _resolve_project(slug, user, db)
    role = await _get_role(user, proj.id, db)
    if role not in ("super_admin", "project_admin", "maintainer", "developer"):
        raise HTTPException(403, "Insufficient permissions")

    mr = MergeRequest(
        project_id=proj.id,
        author_id=user.id,
        source_branch=body.source_branch,
        target_branch=body.target_branch,
        title=body.title,
        description=body.description,
    )
    db.add(mr)
    await db.commit()
    await db.refresh(mr)

    return MergeRequestResponse(
        id=mr.id,
        project_id=mr.project_id,
        author_id=mr.author_id,
        author_name=user.display_name,
        source_branch=mr.source_branch,
        target_branch=mr.target_branch,
        title=mr.title,
        description=mr.description,
        status=mr.status,
        merge_commit_sha=mr.merge_commit_sha,
        created_at=mr.created_at,
        updated_at=mr.updated_at,
    )


@router.post("/projects/{slug}/git/merge-requests/{mr_id}/merge")
async def merge_mr(
    slug: str,
    mr_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, gc = await _resolve_project(slug, user, db)
    role = await _get_role(user, proj.id, db)
    if role not in ("super_admin", "project_admin", "maintainer"):
        raise HTTPException(403, "Insufficient permissions")

    mr = (await db.execute(select(MergeRequest).where(MergeRequest.id == mr_id))).scalar_one_or_none()
    if not mr:
        raise HTTPException(404, "Merge request not found")

    # Check self-approval
    if mr.author_id == user.id and not proj.self_approve_enabled:
        raise HTTPException(400, "Self-approval not allowed for this project")

    mr.status = "merged"
    await db.commit()
    return {"status": "merged", "mr_id": mr_id}


@router.post("/projects/{slug}/git/merge-requests/{mr_id}/close")
async def close_mr(
    slug: str,
    mr_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, _ = await _resolve_project(slug, user, db)
    mr = (await db.execute(select(MergeRequest).where(MergeRequest.id == mr_id))).scalar_one_or_none()
    if not mr:
        raise HTTPException(404, "Merge request not found")
    if mr.author_id != user.id:
        role = await _get_role(user, proj.id, db)
        if role not in ("super_admin", "project_admin", "maintainer"):
            raise HTTPException(403, "Only author or maintainer can close")
    mr.status = "closed"
    await db.commit()
    return {"status": "closed", "mr_id": mr_id}


# ─── GitHub Checks ───


@router.get("/projects/{slug}/git/merge-requests/{mr_id}/checks", response_model=list[CheckRunResponse])
async def get_mr_checks(
    slug: str,
    mr_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj, gc = await _resolve_project(slug, user, db)
    if not gc or "github.com" not in gc.repo_url:
        return []

    # Extract owner/repo from URL
    url = gc.repo_url.rstrip(".git")
    parts = url.split("github.com/")
    if len(parts) < 2:
        return []
    repo_path = parts[1]

    mr = (await db.execute(select(MergeRequest).where(MergeRequest.id == mr_id))).scalar_one_or_none()
    if not mr:
        raise HTTPException(404, "Merge request not found")

    token = gc.credentials_encrypted
    if not token:
        return []

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo_path}/commits/{mr.source_branch}/check-runs",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            return []

    data = resp.json()
    return [
        CheckRunResponse(
            name=cr["name"],
            status=cr["status"],
            conclusion=cr.get("conclusion"),
            details_url=cr.get("details_url"),
        )
        for cr in data.get("check_runs", [])
    ]