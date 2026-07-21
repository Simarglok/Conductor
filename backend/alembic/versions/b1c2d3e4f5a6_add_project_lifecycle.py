"""add durable project lifecycle persistence

Revision ID: b1c2d3e4f5a6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-18 00:20:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROJECT_LIFECYCLE_STATUS_VALUES = (
    "provisioning",
    "ready",
    "provision_failed",
    "deleting",
    "deletion_failed",
)
PROVISIONER_KIND_VALUES = ("docker_compose",)
RUNTIME_RESOURCE_KIND_VALUES = (
    "container",
    "volume",
    "network",
    "database",
    "database_role",
    "proxy_route",
)
LIFECYCLE_OPERATION_VALUES = ("provision", "delete", "reconcile")
LIFECYCLE_JOB_STATUS_VALUES = (
    "pending",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
)

project_lifecycle_status = postgresql.ENUM(
    *PROJECT_LIFECYCLE_STATUS_VALUES,
    name="project_lifecycle_status",
    create_type=False,
)
project_provisioner_kind = postgresql.ENUM(
    *PROVISIONER_KIND_VALUES,
    name="project_provisioner_kind",
    create_type=False,
)
project_runtime_resource_kind = postgresql.ENUM(
    *RUNTIME_RESOURCE_KIND_VALUES,
    name="project_runtime_resource_kind",
    create_type=False,
)
project_lifecycle_operation = postgresql.ENUM(
    *LIFECYCLE_OPERATION_VALUES,
    name="project_lifecycle_operation",
    create_type=False,
)
project_lifecycle_job_status = postgresql.ENUM(
    *LIFECYCLE_JOB_STATUS_VALUES,
    name="project_lifecycle_job_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        project_lifecycle_status,
        project_provisioner_kind,
        project_runtime_resource_kind,
        project_lifecycle_operation,
        project_lifecycle_job_status,
    ):
        enum_type.create(bind, checkfirst=False)

    # Existing projects represent unmanaged legacy runtimes and must be
    # diagnosable/retriable rather than silently treated as ready.
    op.add_column(
        "projects",
        sa.Column("lifecycle_status", project_lifecycle_status, nullable=True),
    )
    op.execute(
        "UPDATE projects SET lifecycle_status = 'provision_failed' "
        "WHERE lifecycle_status IS NULL"
    )
    op.alter_column(
        "projects",
        "lifecycle_status",
        existing_type=project_lifecycle_status,
        nullable=False,
        server_default=sa.text("'provisioning'"),
    )

    op.create_table(
        "project_deployments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provisioner_kind",
            project_provisioner_kind,
            nullable=False,
            server_default=sa.text("'docker_compose'"),
        ),
        sa.Column("template_version", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("compose_project_name", sa.String(63), nullable=False),
        sa.Column("airflow_external_url", sa.Text(), nullable=False),
        sa.Column("airflow_db_name", sa.String(63), nullable=False),
        sa.Column("airflow_db_role", sa.String(63), nullable=False),
        sa.Column("airflow_db_password_encrypted", sa.Text(), nullable=False),
        sa.Column("airflow_admin_user", sa.String(128), nullable=False),
        sa.Column("airflow_admin_password_encrypted", sa.Text(), nullable=False),
        sa.Column("airflow_dev_user", sa.String(128), nullable=False),
        sa.Column("airflow_dev_password_encrypted", sa.Text(), nullable=False),
        sa.Column("airflow_viewer_user", sa.String(128), nullable=False),
        sa.Column("airflow_viewer_password_encrypted", sa.Text(), nullable=False),
        sa.Column("airflow_integration_user", sa.String(128), nullable=False),
        sa.Column("airflow_integration_password_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_id", name="uq_project_deployments_project_id"),
        sa.UniqueConstraint(
            "compose_project_name", name="uq_project_deployments_compose_project_name"
        ),
        sa.UniqueConstraint("airflow_db_name", name="uq_project_deployments_airflow_db_name"),
        sa.UniqueConstraint("airflow_db_role", name="uq_project_deployments_airflow_db_role"),
    )

    op.create_table(
        "project_runtime_resources",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("resource_kind", project_runtime_resource_kind, nullable=False),
        sa.Column("logical_name", sa.String(255), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=True),
        sa.Column("provider_name", sa.String(255), nullable=True),
        sa.Column("observed_status", sa.String(64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "project_id",
            "generation",
            "logical_name",
            name="uq_project_runtime_resources_identity",
        ),
    )
    op.create_index(
        "ix_project_runtime_resources_project_id",
        "project_runtime_resources",
        ["project_id"],
    )

    op.create_table(
        "project_lifecycle_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", project_lifecycle_operation, nullable=False),
        sa.Column(
            "status",
            project_lifecycle_job_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("current_step", sa.String(128), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(255), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "requested_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_project_lifecycle_jobs_idempotency_key"
        ),
    )
    op.create_index(
        "ix_project_lifecycle_jobs_project_id",
        "project_lifecycle_jobs",
        ["project_id"],
    )
    op.create_index(
        "ix_project_lifecycle_jobs_correlation_id",
        "project_lifecycle_jobs",
        ["correlation_id"],
    )
    op.create_index(
        "uq_project_lifecycle_jobs_active_project",
        "project_lifecycle_jobs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running', 'retry_wait')"),
    )

    op.create_table(
        "reauth_grants",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("token_hash", name="uq_reauth_grants_token_hash"),
    )
    op.create_index("ix_reauth_grants_user_id", "reauth_grants", ["user_id"])
    op.create_index("ix_reauth_grants_project_id", "reauth_grants", ["project_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("project_id_snapshot", sa.String(32), nullable=False),
        sa.Column("project_name_snapshot", sa.String(128), nullable=False),
        sa.Column("project_slug_snapshot", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index(
        "ix_audit_events_project_id_snapshot", "audit_events", ["project_id_snapshot"]
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.execute(
        """
        CREATE FUNCTION conductor_prevent_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            -- Permit only nested FK-maintained actor anonymization required by
            -- ON DELETE SET NULL. A direct UPDATE runs at trigger depth 1.
            IF TG_OP = 'UPDATE'
               AND pg_trigger_depth() > 1
               AND OLD.actor_user_id IS NOT NULL
               AND NEW.actor_user_id IS NULL
               AND (to_jsonb(NEW) - 'actor_user_id') = (to_jsonb(OLD) - 'actor_user_id')
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION conductor_prevent_audit_event_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION conductor_prevent_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION conductor_prevent_audit_event_mutation()")
    op.drop_table("reauth_grants")
    op.drop_table("project_lifecycle_jobs")
    op.drop_table("project_runtime_resources")
    op.drop_table("project_deployments")
    op.drop_column("projects", "lifecycle_status")

    bind = op.get_bind()
    for enum_type in (
        project_lifecycle_job_status,
        project_lifecycle_operation,
        project_runtime_resource_kind,
        project_provisioner_kind,
        project_lifecycle_status,
    ):
        enum_type.drop(bind, checkfirst=False)
