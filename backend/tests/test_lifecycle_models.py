from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

import pytest
from sqlalchemy import delete, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditEvent,
    LifecycleJobStatus,
    LifecycleOperation,
    Project,
    ProjectDeployment,
    ProjectLifecycleJob,
    ProjectLifecycleStatus,
    ProjectRuntimeResource,
    ProvisionerKind,
    ReauthGrant,
    RuntimeResourceKind,
    User,
)


def _enum_values(enum_type: type[Enum]) -> set[str]:
    return {member.value for member in enum_type}


def _deployment(project_id: str, suffix: str) -> ProjectDeployment:
    return ProjectDeployment(
        project_id=project_id,
        provisioner_kind=ProvisionerKind.DOCKER_COMPOSE,
        template_version="v1",
        generation=1,
        compose_project_name=f"conductor-p-{suffix}",
        airflow_external_url=f"https://{suffix}.airflow.test",
        airflow_db_name=f"airflow_{suffix}",
        airflow_db_role=f"airflow_{suffix}_role",
        airflow_db_password_encrypted="encrypted-db-password",
        airflow_admin_user="admin",
        airflow_admin_password_encrypted="encrypted-admin-password",
        airflow_dev_user="dev",
        airflow_dev_password_encrypted="encrypted-dev-password",
        airflow_viewer_user="viewer",
        airflow_viewer_password_encrypted="encrypted-viewer-password",
        airflow_integration_user="integration",
        airflow_integration_password_encrypted="encrypted-integration-password",
        parameters={},
    )


def _job(
    project_id: str,
    suffix: str,
    *,
    status: LifecycleJobStatus = LifecycleJobStatus.PENDING,
    requested_by: str | None = None,
) -> ProjectLifecycleJob:
    return ProjectLifecycleJob(
        project_id=project_id,
        operation=LifecycleOperation.PROVISION,
        status=status,
        attempt=0,
        max_attempts=5,
        available_at=datetime.now(timezone.utc),
        idempotency_key=f"idempotency-{suffix}",
        request_fingerprint=f"fingerprint-{suffix}",
        requested_by=requested_by,
        correlation_id=f"correlation-{suffix}",
    )


def test_lifecycle_enums_expose_the_complete_persisted_value_sets() -> None:
    assert _enum_values(ProjectLifecycleStatus) == {
        "provisioning",
        "ready",
        "provision_failed",
        "deleting",
        "deletion_failed",
    }
    assert _enum_values(ProvisionerKind) == {"docker_compose"}
    assert _enum_values(RuntimeResourceKind) == {
        "container",
        "volume",
        "network",
        "database",
        "database_role",
        "proxy_route",
    }
    assert _enum_values(LifecycleOperation) == {"provision", "delete", "reconcile"}
    assert _enum_values(LifecycleJobStatus) == {
        "pending",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
    }


@pytest.mark.asyncio
async def test_postgresql_lifecycle_enum_names_and_labels_are_exact(
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.execute(
            text(
                """
                SELECT type.typname, array_agg(enum.enumlabel ORDER BY enum.enumsortorder) AS labels
                FROM pg_type AS type
                JOIN pg_enum AS enum ON enum.enumtypid = type.oid
                WHERE type.typname IN (
                    'project_lifecycle_status',
                    'project_provisioner_kind',
                    'project_runtime_resource_kind',
                    'project_lifecycle_operation',
                    'project_lifecycle_job_status'
                )
                GROUP BY type.typname
                """
            )
        )
    ).all()

    assert {row.typname: list(row.labels) for row in rows} == {
        "project_lifecycle_status": [
            "provisioning",
            "ready",
            "provision_failed",
            "deleting",
            "deletion_failed",
        ],
        "project_provisioner_kind": ["docker_compose"],
        "project_runtime_resource_kind": [
            "container",
            "volume",
            "network",
            "database",
            "database_role",
            "proxy_route",
        ],
        "project_lifecycle_operation": ["provision", "delete", "reconcile"],
        "project_lifecycle_job_status": [
            "pending",
            "running",
            "retry_wait",
            "succeeded",
            "failed",
        ],
    }


def test_lifecycle_metadata_registers_tables_constraints_and_relationships() -> None:
    expected_tables = {
        "project_deployments",
        "project_runtime_resources",
        "project_lifecycle_jobs",
        "reauth_grants",
        "audit_events",
    }
    assert expected_tables <= set(Project.metadata.tables)

    project_relationships = inspect(Project).relationships
    assert project_relationships["deployment"].uselist is False
    for relationship_name in (
        "deployment",
        "runtime_resources",
        "lifecycle_jobs",
        "reauth_grants",
    ):
        assert project_relationships[relationship_name].passive_deletes is True

    deployment = ProjectDeployment.__table__
    assert deployment.c.project_id.unique is True
    for column_name in ("compose_project_name", "airflow_db_name", "airflow_db_role"):
        assert deployment.c[column_name].unique is True

    audit = AuditEvent.__table__
    assert "project_id_snapshot" in audit.c
    assert not audit.c.project_id_snapshot.foreign_keys
    actor_fk = next(iter(audit.c.actor_user_id.foreign_keys))
    assert actor_fk.target_fullname == "users.id"
    assert actor_fk.ondelete == "SET NULL"

    for table_name in (
        "project_deployments",
        "project_runtime_resources",
        "project_lifecycle_jobs",
        "reauth_grants",
    ):
        project_fk = next(iter(Project.metadata.tables[table_name].c.project_id.foreign_keys))
        assert project_fk.target_fullname == "projects.id"
        assert project_fk.ondelete == "CASCADE"

    active_index = next(
        index
        for index in ProjectLifecycleJob.__table__.indexes
        if index.name == "uq_project_lifecycle_jobs_active_project"
    )
    assert active_index.unique is True
    predicate = str(active_index.dialect_options["postgresql"]["where"])
    assert predicate == "status IN ('pending', 'running', 'retry_wait')"


@pytest.mark.asyncio
async def test_postgresql_active_job_partial_index_predicate_is_exact(
    db_session: AsyncSession,
) -> None:
    predicate = (
        await db_session.execute(
            text(
                """
                SELECT pg_get_expr(index.indpred, index.indrelid)
                FROM pg_index AS index
                JOIN pg_class AS index_class ON index_class.oid = index.indexrelid
                WHERE index_class.relname = 'uq_project_lifecycle_jobs_active_project'
                """
            )
        )
    ).scalar_one()

    assert predicate == (
        "(status = ANY (ARRAY["
        "'pending'::project_lifecycle_job_status, "
        "'running'::project_lifecycle_job_status, "
        "'retry_wait'::project_lifecycle_job_status]))"
    )


def test_project_lifecycle_status_has_provisioning_defaults() -> None:
    status_column = Project.__table__.c.lifecycle_status
    assert status_column.default.arg == ProjectLifecycleStatus.PROVISIONING
    assert str(status_column.server_default.arg) == "'provisioning'"


@pytest.mark.asyncio
async def test_project_delete_cascades_owned_rows_but_retains_audit_snapshot(
    db_session: AsyncSession,
) -> None:
    actor = User(
        email="lifecycle-cascade@test.local",
        hashed_password="not-used",
        display_name="Lifecycle Cascade",
    )
    project = Project(name="Cascade Project", slug="lifecycle-cascade")
    db_session.add_all([actor, project])
    await db_session.flush()

    deployment = _deployment(project.id, "cascade")
    resource = ProjectRuntimeResource(
        project_id=project.id,
        generation=1,
        resource_kind=RuntimeResourceKind.CONTAINER,
        logical_name="airflow.api",
        provider_id="container-cascade",
        provider_name="airflow-api",
        observed_status="running",
        metadata_json={"healthy": True},
    )
    job = _job(project.id, "cascade", requested_by=actor.id)
    grant = ReauthGrant(
        token_hash="token-hash-cascade",
        user_id=actor.id,
        action="project.delete",
        project_id=project.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    audit = AuditEvent(
        event_type="project.delete.completed",
        actor_user_id=actor.id,
        project_id_snapshot=project.id,
        project_name_snapshot=project.name,
        project_slug_snapshot=project.slug,
        correlation_id="correlation-cascade",
        outcome="succeeded",
        metadata_json={"resources_removed": 4},
    )
    db_session.add_all([deployment, resource, job, grant, audit])
    await db_session.flush()
    audit_id = audit.id
    project_id = project.id

    await db_session.delete(project)
    await db_session.flush()

    for model in (ProjectDeployment, ProjectRuntimeResource, ProjectLifecycleJob, ReauthGrant):
        assert (await db_session.execute(select(model).where(model.project_id == project_id))).scalars().all() == []

    retained = await db_session.get(AuditEvent, audit_id)
    assert retained is not None
    assert retained.project_id_snapshot == project_id
    assert retained.project_name_snapshot == "Cascade Project"
    assert retained.project_slug_snapshot == "lifecycle-cascade"


@pytest.mark.asyncio
async def test_audit_actor_is_set_null_when_user_is_deleted(db_session: AsyncSession) -> None:
    actor = User(
        email="audit-actor@test.local",
        hashed_password="not-used",
        display_name="Audit Actor",
    )
    db_session.add(actor)
    await db_session.flush()
    audit = AuditEvent(
        event_type="project.provision.requested",
        actor_user_id=actor.id,
        project_id_snapshot="snapshot-project-id",
        project_name_snapshot="Snapshot Project",
        project_slug_snapshot="snapshot-project",
        correlation_id="correlation-audit-actor",
        outcome="requested",
        metadata_json={},
    )
    db_session.add(audit)
    await db_session.flush()
    audit_id = audit.id

    await db_session.delete(actor)
    await db_session.flush()
    db_session.expire_all()

    retained = await db_session.get(AuditEvent, audit_id)
    assert retained is not None
    assert retained.actor_user_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_field", ["compose_project_name", "airflow_db_name", "airflow_db_role"])
async def test_deployment_runtime_identities_are_unique(
    db_session: AsyncSession,
    identity_field: str,
) -> None:
    first_project = Project(name=f"Identity One {identity_field}", slug=f"identity-one-{identity_field}")
    second_project = Project(name=f"Identity Two {identity_field}", slug=f"identity-two-{identity_field}")
    db_session.add_all([first_project, second_project])
    await db_session.flush()
    first = _deployment(first_project.id, f"first-{identity_field}")
    second = _deployment(second_project.id, f"second-{identity_field}")
    setattr(second, identity_field, getattr(first, identity_field))
    db_session.add(first)
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(second)
            await db_session.flush()


@pytest.mark.asyncio
async def test_only_one_active_lifecycle_job_is_allowed_per_project(
    db_session: AsyncSession,
) -> None:
    project = Project(name="Active Job Project", slug="active-job-project")
    db_session.add(project)
    await db_session.flush()
    db_session.add(_job(project.id, "active-one", status=LifecycleJobStatus.PENDING))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(_job(project.id, "active-two", status=LifecycleJobStatus.RUNNING))
            await db_session.flush()

    db_session.add(_job(project.id, "terminal", status=LifecycleJobStatus.SUCCEEDED))
    await db_session.flush()


@pytest.mark.asyncio
async def test_audit_events_reject_updates_and_deletes(db_session: AsyncSession) -> None:
    audit = AuditEvent(
        event_type="project.provision.succeeded",
        actor_user_id=None,
        project_id_snapshot="append-only-project-id",
        project_name_snapshot="Append Only Project",
        project_slug_snapshot="append-only-project",
        correlation_id="correlation-append-only",
        outcome="succeeded",
        metadata_json={},
    )
    db_session.add(audit)
    await db_session.flush()
    audit_id = audit.id

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(AuditEvent).where(AuditEvent.id == audit_id).values(outcome="mutated")
            )

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(delete(AuditEvent).where(AuditEvent.id == audit_id))

    assert await db_session.get(AuditEvent, audit_id) is not None


@pytest.mark.asyncio
async def test_audit_events_reject_direct_actor_anonymization(
    db_session: AsyncSession,
) -> None:
    actor = User(
        email="direct-audit-anonymization@test.local",
        hashed_password="not-used",
        display_name="Direct Audit Anonymization",
    )
    db_session.add(actor)
    await db_session.flush()
    audit = AuditEvent(
        event_type="project.provision.requested",
        actor_user_id=actor.id,
        project_id_snapshot="direct-anonymization-project-id",
        project_name_snapshot="Direct Anonymization Project",
        project_slug_snapshot="direct-anonymization-project",
        correlation_id="correlation-direct-anonymization",
        outcome="requested",
        metadata_json={},
    )
    db_session.add(audit)
    await db_session.flush()

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(AuditEvent)
                .where(AuditEvent.id == audit.id)
                .values(actor_user_id=None)
            )


@pytest.mark.asyncio
async def test_audit_events_reject_truncate(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(text("TRUNCATE TABLE audit_events"))
