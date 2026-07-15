from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.database import get_db_session
from app.models.airflow_instance import AirflowInstance
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.role import Role
from app.models.user import User
from app.schemas.dag import DAGRunInfo, DAGSummary

router = APIRouter()

ROLE_ACCOUNT_MAP: dict[str, str] = {
    "super_admin": "admin",
    "project_admin": "admin",
    "maintainer": "dev",
    "developer": "dev",
    "viewer": "viewer",
}

_airflow_sessions: dict[str, str] = {}


async def _get_session(instance: AirflowInstance, account_key: str) -> str:
    cache_key = f"{instance.id}_{account_key}"
    if cache_key in _airflow_sessions:
        return _airflow_sessions[cache_key]

    if account_key == "admin":
        username, password = instance.admin_user, instance.admin_password_encrypted
    elif account_key == "dev":
        username, password = instance.dev_user, instance.dev_password_encrypted
    else:
        username, password = instance.viewer_user, instance.viewer_password_encrypted

    if not password:
        raise HTTPException(status_code=500, detail="Airflow not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{instance.internal_url}/api/v1/login/",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Airflow login failed")
        session_val = ""
        for cookie in resp.cookies.jar:
            if cookie.name == "session":
                session_val = cookie.value or ""
                _airflow_sessions[cache_key] = session_val
                return session_val
    return ""


async def _get_airflow(project_slug: str, user: User, db: AsyncSession) -> tuple[AirflowInstance, str]:
    proj = (await db.execute(select(Project).where(Project.slug == project_slug))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")
    if not user.is_admin:
        member = (await db.execute(
            select(ProjectMember).where(ProjectMember.project_id == proj.id, ProjectMember.user_id == user.id)
        )).scalar_one_or_none()
        if not member:
            raise HTTPException(403, "Access denied")
    inst = (await db.execute(select(AirflowInstance).where(AirflowInstance.project_id == proj.id))).scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "Airflow not provisioned")
    if user.is_admin:
        return inst, "admin"
    member = (await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == proj.id, ProjectMember.user_id == user.id)
        .options(selectinload(ProjectMember.role))
    )).scalar_one_or_none()
    key = ROLE_ACCOUNT_MAP.get(member.role.name if member else "viewer", "viewer")
    return inst, key


@router.get("/projects/{slug}/airflow/dags", response_model=list[DAGSummary])
async def list_dags(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    inst, key = await _get_airflow(slug, user, db)
    session = await _get_session(inst, key)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{inst.internal_url}/api/v1/dags",
            cookies={"session": session},
        )
    if resp.status_code != 200:
        raise HTTPException(502, "Airflow API error")
    data = resp.json()
    return [
        DAGSummary(
            dag_id=d["dag_id"],
            description=d.get("description"),
            is_paused=d.get("is_paused", False),
            latest_run_state=None,
            latest_run_start=None,
            latest_run_end=None,
            next_dagrun=None,
        )
        for d in data.get("dags", [])
    ]


@router.get("/projects/{slug}/airflow/dags/{dag_id}/runs", response_model=list[DAGRunInfo])
async def list_dag_runs(
    slug: str, dag_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    inst, key = await _get_airflow(slug, user, db)
    session = await _get_session(inst, key)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{inst.internal_url}/api/v1/dags/{dag_id}/dagRuns",
            cookies={"session": session},
        )
    if resp.status_code != 200:
        raise HTTPException(502, "Airflow API error")
    data = resp.json()
    return [
        DAGRunInfo(
            run_id=r["dag_run_id"],
            state=r.get("state", ""),
            execution_date=r.get("execution_date", ""),
            start_date=r.get("start_date"),
            end_date=r.get("end_date"),
            duration=r.get("duration"),
        )
        for r in data.get("dag_runs", [])
    ]


@router.get("/projects/{slug}/airflow-iframe/{path:path}")
async def airflow_iframe(
    slug: str, path: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    inst, key = await _get_airflow(slug, user, db)
    session = await _get_session(inst, key)
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
<script>
document.cookie = "session={session}; path=/; SameSite=Lax";
window.location.href = "{inst.internal_url}/{path}";
</script></body></html>"""
    return Response(content=html, media_type="text/html")