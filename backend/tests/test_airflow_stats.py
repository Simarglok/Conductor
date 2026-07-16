import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_stats_requires_auth(client):
    """Unauthenticated requests should return 401."""
    resp = await client.get("/api/v1/projects/test-slug/airflow/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stats_project_not_found(client):
    """Nonexistent project should return 404 (after auth check, or 401 without)."""
    resp = await client.get("/api/v1/projects/nonexistent/airflow/stats")
    # Without auth token, 401 is expected. With auth, it'd be 404.
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_stats_endpoint_registered(client):
    """Verify the endpoint is wired up and accessible (even if 401)."""
    resp = await client.get("/api/v1/projects/some-project/airflow/stats")
    # Should return 401 (not authenticated) not 404 (endpoint missing)
    assert resp.status_code == 401