from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db_session
from app.models.git_config import GitConfig
from app.models.user import User
from app.services.project_access import load_ready_project_for_user
from app.services.secret_redaction import redact_secret_text
from app.services.workspace import ensure_workspace

router = APIRouter()


@router.post("/projects/{slug}/codeserver/setup-workspace")
async def setup_workspace(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj = await load_ready_project_for_user(slug, user, db)

    gc = (await db.execute(
        select(GitConfig).where(GitConfig.project_id == proj.id)
    )).scalar_one_or_none()
    if not gc:
        raise HTTPException(400, "Git repository not configured for this project")

    try:
        repo_path = await ensure_workspace(user, proj, gc)
        return {
            "status": "ready",
            "workspace_path": str(repo_path),
            "branch": gc.default_branch or "main",
        }
    except RuntimeError as exc:
        raise HTTPException(
            500,
            redact_secret_text(f"Workspace setup failed: {exc}"),
        ) from exc