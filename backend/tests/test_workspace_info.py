import pytest


@pytest.mark.asyncio
async def test_workspace_info_requires_auth(client):
    """Unauthenticated requests should return 401."""
    resp = await client.get("/api/v1/projects/test-slug/codeserver/workspace-info")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_workspace_info_project_not_found(client):
    """Nonexistent project returns 404 (after auth check, or 401 without)."""
    resp = await client.get("/api/v1/projects/nonexistent/codeserver/workspace-info")
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_workspace_info_endpoint_registered(client):
    """Verify the endpoint is wired up (returns 401 without auth)."""
    resp = await client.get("/api/v1/projects/some-project/codeserver/workspace-info")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_workspace_info_schema_importable():
    """Verify schema is importable."""
    from app.schemas.codeserver import WorkspaceInfoResponse
    w = WorkspaceInfoResponse(branch="main", ahead=0, behind=0, files=["dags/"])
    assert w.branch == "main"
    assert w.files == ["dags/"]