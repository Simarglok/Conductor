from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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

router = APIRouter()

# Map Conductor roles to Airflow system account keys
ROLE_ACCOUNT_MAP: dict[str, str] = {
    "super_admin": "admin",
    "project_admin": "admin",
    "maintainer": "dev",
    "developer": "dev",
    "viewer": "viewer",
}

# Cache for Airflow sessions: {instance_id_role: session_cookie}
_airflow_sessions: dict[str, str] = {}


async def _get_airflow_session(instance: AirflowInstance, account_key: str) -> str:
    """Get or create a session cookie for an Airflow system account."""
    cache_key = f"{instance.id}_{account_key}"
    if cache_key in _airflow_sessions:
        return _airflow_sessions[cache_key]

    # Map account_key to actual credentials
    if account_key == "admin":
        username = instance.admin_user
        password = instance.admin_password_encrypted
    elif account_key == "dev":
        username = instance.dev_user
        password = instance.dev_password_encrypted
    else:
        username = instance.viewer_user
        password = instance.viewer_password_encrypted

    if not password:
        raise HTTPException(status_code=500, detail="Airflow credentials not configured")

    # Login via Basic Auth
    async with httpx.AsyncClient() as client:
        login_resp = await client.post(
            f"{instance.internal_url}/api/v1/login/",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if login_resp.status_code != 200:
            raise HTTPException(
                status_code=502, detail="Failed to authenticate with Airflow"
            )
        session_cookie = login_resp.cookies.get("session")
        if not session_cookie:
            # Try to get it from the response
            for cookie in login_resp.cookies.jar:
                if cookie.name == "session":
                    session_cookie = cookie.value
                    break

        if session_cookie:
            _airflow_sessions[cache_key] = session_cookie

        return session_cookie or ""


async def _resolve_airflow(
    slug: str, user: User, db: AsyncSession
) -> tuple[AirflowInstance, str]:
    """Resolve project, Airflow instance, and account key for a user."""
    # Resolve project
    proj_result = await db.execute(select(Project).where(Project.slug == slug))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check membership
    if not user.is_admin:
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
        )
        if not member_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Get Airflow instance
    inst_result = await db.execute(
        select(AirflowInstance).where(AirflowInstance.project_id == project.id)
    )
    instance = inst_result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Airflow not provisioned")

    # Determine role → account mapping
    if user.is_admin:
        account_key = "admin"
    else:
        member_result = await db.execute(
            select(ProjectMember)
            .where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
            .options(selectinload(ProjectMember.role))
        )
        member = member_result.scalar_one_or_none()
        account_key = ROLE_ACCOUNT_MAP.get(member.role.name if member else "viewer", "viewer")

    return instance, account_key


@router.api_route(
    "/projects/{slug}/airflow-proxy/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def airflow_proxy(
    slug: str,
    path: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    instance, account_key = await _resolve_airflow(slug, user, db)
    session = await _get_airflow_session(instance, account_key)

    # Forward request to Airflow
    target_url = f"{instance.internal_url}/{path}"
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("authorization", None)

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            content=body,
            headers={**headers, "Cookie": f"session={session}"},
            params=dict(request.query_params),
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


@router.get("/projects/{slug}/airflow-iframe/{path:path}")
async def airflow_iframe(
    slug: str,
    path: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns an HTML page that sets Airflow session cookie and redirects to iframe."""
    instance, account_key = await _resolve_airflow(slug, user, db)
    session = await _get_airflow_session(instance, account_key)

    return Response(
        content=f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body>
<script>
document.cookie = "session={session}; path=/; SameSite=Lax";
window.location.href = "{instance.internal_url}/{path}";
</script>
</body>
</html>""",
        media_type="text/html",
    )