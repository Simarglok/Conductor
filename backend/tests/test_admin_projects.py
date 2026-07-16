import pytest


@pytest.mark.asyncio
async def test_admin_projects_requires_auth(client):
    """Unauthenticated requests should return 401."""
    resp = await client.get("/api/v1/admin/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_projects_endpoint_registered(client):
    """Verify the endpoint is wired up (returns 401 without auth)."""
    resp = await client.get("/api/v1/admin/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_projects_schema_importable():
    """Verify schema is importable with all fields."""
    from app.schemas.admin import AdminProjectResponse
    from datetime import datetime
    p = AdminProjectResponse(
        id="1",
        name="test",
        slug="test",
        member_count=5,
        airflow_status="running",
        created_at=datetime.now(),
    )
    assert p.member_count == 5
    assert p.airflow_status == "running"