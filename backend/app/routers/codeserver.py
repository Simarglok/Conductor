from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import settings
from app.database import get_db_session
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User

router = APIRouter()


@router.post("/projects/{slug}/codeserver/token")
async def generate_codeserver_token(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj = (await db.execute(select(Project).where(Project.slug == slug))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")

    if not user.is_admin:
        member = (await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj.id, ProjectMember.user_id == user.id
            )
        )).scalar_one_or_none()
        if not member:
            raise HTTPException(403, "Access denied")

    payload = {
        "sub": user.id,
        "name": user.display_name,
        "workspace": f"/workspace/{user.id}",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    token = jwt.encode(payload, settings.code_server_jwt_secret, algorithm=settings.algorithm)

    return {
        "token": token,
        "expires_in": 900,
        "iframe_url": f"{settings.code_server_host}?token={token}",
    }


@router.get("/projects/{slug}/codeserver/iframe")
async def codeserver_iframe(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    proj = (await db.execute(select(Project).where(Project.slug == slug))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")

    if not user.is_admin:
        member = (await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj.id, ProjectMember.user_id == user.id
            )
        )).scalar_one_or_none()
        if not member:
            raise HTTPException(403, "Access denied")

    payload = {
        "sub": user.id,
        "name": user.display_name,
        "workspace": f"/workspace/{user.id}",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    token = jwt.encode(payload, settings.code_server_jwt_secret, algorithm=settings.algorithm)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{margin:0;overflow:hidden}}iframe{{width:100vw;height:100vh;border:none}}</style>
</head><body>
<iframe src="{settings.code_server_host}?token={token}"
  sandbox="allow-scripts allow-same-origin"
  allow="clipboard-read; clipboard-write"
  loading="lazy">
</iframe>
</body></html>"""
    return HTMLResponse(content=html)