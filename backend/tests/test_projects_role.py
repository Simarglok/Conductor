import pytest


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
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["role"] == "super_admin"
    assert data["member_count"] == 1


@pytest.mark.asyncio
async def test_get_project_returns_role(admin_client):
    """GET /projects/{slug} — returns role for authenticated user."""
    # Create first
    r = await admin_client.post("/api/v1/projects", json={"name": "P", "slug": "p"})
    assert r.status_code == 201
    slug = r.json()["slug"]

    # Get
    r = await admin_client.get(f"/api/v1/projects/{slug}")
    assert r.status_code == 200
    assert r.json()["role"] == "super_admin"


@pytest.mark.asyncio
async def test_list_projects_returns_role(admin_client):
    """GET /projects — each project has role field."""
    await admin_client.post("/api/v1/projects", json={"name": "X", "slug": "x"})
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
    await admin_client.post("/api/v1/projects", json={"name": "Dup", "slug": "dup"})
    r = await admin_client.post("/api/v1/projects", json={"name": "Dup2", "slug": "dup"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_project_non_admin_rejected(client):
    """POST /projects — 401/403 for unauthenticated/non-admin."""
    r = await client.post("/api/v1/projects", json={"name": "Hack", "slug": "hack"})
    assert r.status_code in (401, 403)