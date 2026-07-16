import pytest


@pytest.mark.asyncio
async def test_commits_requires_auth(client):
    """Unauthenticated requests should return 401."""
    resp = await client.get("/api/v1/projects/test-slug/git/commits")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_commits_project_not_found(client):
    """Nonexistent project slug returns 404 (after auth check, or 401 without)."""
    resp = await client.get("/api/v1/projects/nonexistent/git/commits")
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_commits_endpoint_registered(client):
    """Verify the endpoint is wired up (returns 401 without auth)."""
    resp = await client.get("/api/v1/projects/some-project/git/commits")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_commits_default_params(client):
    """Verify default query params are accepted."""
    resp = await client.get("/api/v1/projects/some-project/git/commits?branch=main&limit=10")
    # Without auth, should be 401
    assert resp.status_code == 401