from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project


COMMITTED_API_SLUG = "fixture-isolation-committed-api-project"


@pytest.mark.asyncio
async def test_01_api_can_commit_a_row_visible_from_a_fresh_session(
    admin_client,
    db_session: AsyncSession,
) -> None:
    response = await admin_client.post(
        "/api/v1/projects",
        json={
            "name": "Fixture Isolation Committed API Project",
            "slug": COMMITTED_API_SLUG,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text

    committed = (
        await db_session.execute(select(Project).where(Project.slug == COMMITTED_API_SLUG))
    ).scalar_one_or_none()
    assert committed is not None


@pytest.mark.asyncio
async def test_02_committed_api_rows_do_not_leak_into_the_next_test(
    db_session: AsyncSession,
) -> None:
    leaked = (
        await db_session.execute(select(Project).where(Project.slug == COMMITTED_API_SLUG))
    ).scalar_one_or_none()
    assert leaked is None
