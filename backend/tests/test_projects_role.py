from uuid import uuid4

import pytest

from app.models.project import Project, ProjectLifecycleStatus


def _idempotency_headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


async def _mark_ready(db_session, project_id: str) -> None:
    project = await db_session.get(Project, project_id)
    project.lifecycle_status = ProjectLifecycleStatus.READY
    await db_session.commit()


@pytest.mark.asyncio
async def test_projects_requires_auth(client):
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_projects_schema_has_role():
    from app.schemas.project import ProjectResponse
    assert "role" in ProjectResponse.model_fields


@pytest.mark.asyncio
async def test_create_project_returns_role(admin_client):
    """POST /projects — super_admin creates project, response includes role."""
    resp = await admin_client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "slug": "test-proj", "description": "Desc"},
        headers=_idempotency_headers(),
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()["project"]
    assert data["name"] == "Test Project"
    assert data["role"] == "super_admin"
    assert data["member_count"] == 1
    assert resp.json()["operation"]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_project_returns_role(admin_client, db_session):
    """GET /projects/{slug} — returns role for authenticated user."""
    # Create first
    r = await admin_client.post(
        "/api/v1/projects",
        json={"name": "P", "slug": "p"},
        headers=_idempotency_headers(),
    )
    assert r.status_code == 202
    project = r.json()["project"]
    await _mark_ready(db_session, project["id"])
    slug = project["slug"]

    # Get
    r = await admin_client.get(f"/api/v1/projects/{slug}")
    assert r.status_code == 200
    assert r.json()["role"] == "super_admin"


@pytest.mark.asyncio
async def test_list_projects_returns_role(admin_client, db_session):
    """GET /projects — each project has role field."""
    created = await admin_client.post(
        "/api/v1/projects",
        json={"name": "X", "slug": "x"},
        headers=_idempotency_headers(),
    )
    assert created.status_code == 202
    await _mark_ready(db_session, created.json()["project"]["id"])
    r = await admin_client.get("/api/v1/projects")
    assert r.status_code == 200
    projects = r.json()
    assert len(projects) >= 1
    for p in projects:
        assert "role" in p
        assert p["role"] == "super_admin"
        assert "member_count" in p


@pytest.mark.asyncio
async def test_create_project_slug_conflict(admin_client):
    """POST /projects — 409 on duplicate slug."""
    first = await admin_client.post(
        "/api/v1/projects",
        json={"name": "Dup", "slug": "dup"},
        headers=_idempotency_headers(),
    )
    assert first.status_code == 202
    r = await admin_client.post(
        "/api/v1/projects",
        json={"name": "Dup2", "slug": "dup"},
        headers=_idempotency_headers(),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_project_non_admin_rejected(client):
    """POST /projects — 401/403 for unauthenticated/non-admin."""
    r = await client.post(
        "/api/v1/projects",
        json={"name": "Hack", "slug": "hack"},
        headers=_idempotency_headers(),
    )
    assert r.status_code in (401, 403)