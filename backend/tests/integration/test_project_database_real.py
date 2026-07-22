from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest

from app.services.lifecycle_errors import ForeignResourceConflictError
from app.services.project_database import AsyncpgProjectDatabaseManager


MAINTENANCE_DSN = os.environ.get(
    "PROJECT_DATABASE_TEST_MAINTENANCE_DSN",
    "postgresql://conductor:conductor@postgres:5432/postgres",
)


def deployment_for(project_id: str, password: str):
    resource_name = f"conductor_airflow_{project_id}"
    return SimpleNamespace(
        project_id=project_id,
        airflow_db_name=resource_name,
        airflow_db_role=resource_name,
        airflow_db_password_encrypted="test-ciphertext",
    ), password


async def _role_row(connection, name):
    return await connection.fetchrow(
        """
        SELECT role.oid,
               pg_catalog.shobj_description(role.oid, 'pg_authid') AS comment
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = $1
        """,
        name,
    )


async def _database_row(connection, name):
    return await connection.fetchrow(
        """
        SELECT db.oid,
               pg_catalog.pg_get_userbyid(db.datdba) AS owner,
               pg_catalog.shobj_description(db.oid, 'pg_database') AS comment
        FROM pg_catalog.pg_database AS db
        WHERE db.datname = $1
        """,
        name,
    )


async def _cleanup_created(connection, *, deployment, role_oid, database_oid):
    """Remove only resources whose complete tracked identity still matches."""
    errors = []
    expected_comment = f"conductor.project_id={deployment.project_id}"
    quoted_name = '"' + deployment.airflow_db_name.replace('"', '""') + '"'

    if database_oid is not None:
        try:
            row = await _database_row(connection, deployment.airflow_db_name)
            if (
                row is not None
                and row["oid"] == database_oid
                and row["owner"] == deployment.airflow_db_role
                and row["comment"] == expected_comment
            ):
                await connection.execute(
                    f"ALTER DATABASE {quoted_name} ALLOW_CONNECTIONS false"
                )
                await connection.execute(
                    """
                    SELECT pg_catalog.pg_terminate_backend(pid)
                    FROM pg_catalog.pg_stat_activity
                    WHERE datname = $1 AND pid <> pg_catalog.pg_backend_pid()
                    """,
                    deployment.airflow_db_name,
                )
                current = await _database_row(connection, deployment.airflow_db_name)
                if (
                    current is not None
                    and current["oid"] == database_oid
                    and current["owner"] == deployment.airflow_db_role
                    and current["comment"] == expected_comment
                ):
                    await connection.execute(f"DROP DATABASE {quoted_name}")
        except BaseException as error:
            errors.append(error)

    if role_oid is not None:
        try:
            row = await _role_row(connection, deployment.airflow_db_role)
            if (
                row is not None
                and row["oid"] == role_oid
                and row["comment"] == expected_comment
            ):
                await connection.execute(f"DROP ROLE {quoted_name}")
        except BaseException as error:
            errors.append(error)

    if errors:
        raise BaseExceptionGroup("project database integration cleanup failed", errors)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_postgresql_owned_lifecycle_and_foreign_collision() -> None:
    project_id = uuid4().hex
    deployment, password = deployment_for(project_id, uuid4().hex)
    expected_comment = f"conductor.project_id={project_id}"
    manager = AsyncpgProjectDatabaseManager(
        MAINTENANCE_DSN,
        decrypt=lambda _: password,
    )
    cleanup = await asyncpg.connect(MAINTENANCE_DSN)
    role_oid = None
    database_oid = None
    try:
        assert await _role_row(cleanup, deployment.airflow_db_role) is None
        assert await _database_row(cleanup, deployment.airflow_db_name) is None

        role = await manager.ensure_role(deployment)
        tracked_role = await _role_row(cleanup, deployment.airflow_db_role)
        assert tracked_role is not None
        assert tracked_role["comment"] == expected_comment
        role_oid = tracked_role["oid"]
        assert await manager.ensure_role(deployment) == role

        database = await manager.ensure_database(deployment)
        tracked_database = await _database_row(cleanup, deployment.airflow_db_name)
        assert tracked_database is not None
        assert dict(tracked_database) == {
            "oid": tracked_database["oid"],
            "owner": deployment.airflow_db_role,
            "comment": expected_comment,
        }
        database_oid = tracked_database["oid"]
        assert await manager.ensure_database(deployment) == database
        assert await manager.verify_absent(deployment) is False

        foreign_owner = await cleanup.fetchval("SELECT current_user")
        assert foreign_owner != deployment.airflow_db_role
        quoted_foreign_owner = '"' + foreign_owner.replace('"', '""') + '"'
        try:
            await cleanup.execute(
                f'ALTER DATABASE "{deployment.airflow_db_name}" OWNER TO '
                f"{quoted_foreign_owner}"
            )
            with pytest.raises(ForeignResourceConflictError):
                await manager.ensure_database(deployment)
            with pytest.raises(ForeignResourceConflictError):
                await manager.drop_database(deployment)
            foreign_row = await _database_row(cleanup, deployment.airflow_db_name)
            assert foreign_row is not None
            assert foreign_row["oid"] == database_oid
            assert foreign_row["owner"] == foreign_owner
        finally:
            foreign_row = await _database_row(cleanup, deployment.airflow_db_name)
            if (
                foreign_row is not None
                and foreign_row["oid"] == database_oid
                and foreign_row["owner"] == foreign_owner
                and foreign_row["comment"] == expected_comment
            ):
                await cleanup.execute(
                    f'ALTER DATABASE "{deployment.airflow_db_name}" '
                    f'OWNER TO "{deployment.airflow_db_role}"'
                )

        await manager.drop_database(deployment)
        database_oid = None
        await manager.drop_database(deployment)
        await manager.drop_role(deployment)
        role_oid = None
        await manager.drop_role(deployment)
        assert await manager.verify_absent(deployment) is True
    finally:
        try:
            await _cleanup_created(
                cleanup,
                deployment=deployment,
                role_oid=role_oid,
                database_oid=database_oid,
            )
        finally:
            await cleanup.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_postgresql_advisory_lock_fences_second_connection() -> None:
    project_id = uuid4().hex
    deployment, _ = deployment_for(project_id, uuid4().hex)
    lock_identity = f"conductor.project_database:{project_id}"
    blocker = await asyncpg.connect(MAINTENANCE_DSN)
    try:
        await blocker.execute(
            "SELECT pg_catalog.pg_advisory_lock(pg_catalog.hashtextextended($1, 0))",
            lock_identity,
        )
        manager = AsyncpgProjectDatabaseManager(MAINTENANCE_DSN)
        operation = asyncio.create_task(manager.verify_absent(deployment))
        await asyncio.sleep(0.1)
        assert operation.done() is False
        await blocker.execute(
            "SELECT pg_catalog.pg_advisory_unlock(pg_catalog.hashtextextended($1, 0))",
            lock_identity,
        )
        assert await asyncio.wait_for(operation, timeout=2) is True
    finally:
        await blocker.close()
