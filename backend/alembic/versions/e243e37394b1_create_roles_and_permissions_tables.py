"""create roles and permissions tables

Revision ID: e243e37394b1
Revises: d2f4e1b3c5a7
Create Date: 2026-07-15 00:03:38.131431
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

revision: str = "e243e37394b1"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create tables ──
    op.create_table(
        "roles",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("role_id", sa.String(32), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("constraint", sa.Text(), nullable=True),
    )
    op.create_index("ix_permissions_role_id", "permissions", ["role_id"], unique=False)

    # ── Seed roles ──
    roles_table = table(
        "roles",
        column("id", sa.String(32)),
        column("name", sa.String(64)),
        column("description", sa.Text()),
        column("is_system", sa.Boolean()),
    )
    op.bulk_insert(roles_table, [
        {
            "id": "super_admin",
            "name": "super_admin",
            "description": "Full system access, all projects",
            "is_system": True,
        },
        {
            "id": "project_admin",
            "name": "project_admin",
            "description": "Project settings, members, git config, full Airflow",
            "is_system": True,
        },
        {
            "id": "maintainer",
            "name": "maintainer",
            "description": "Code review, merge MRs, trigger DAGs",
            "is_system": True,
        },
        {
            "id": "developer",
            "name": "developer",
            "description": "Create branches, push, create MRs, trigger DAGs",
            "is_system": True,
        },
        {
            "id": "viewer",
            "name": "viewer",
            "description": "Read-only: DAGs, code, logs",
            "is_system": True,
        },
    ])

    # ── Seed permissions ──
    permissions_table = table(
        "permissions",
        column("id", sa.String(32)),
        column("role_id", sa.String(32)),
        column("resource", sa.String(128)),
        column("action", sa.String(32)),
        column("constraint", sa.Text()),
    )
    op.bulk_insert(permissions_table, [
        # super_admin — all access
        {"id": "p001", "role_id": "super_admin", "resource": "*", "action": "admin", "constraint": None},
        # project_admin — everything for a project
        {"id": "p010", "role_id": "project_admin", "resource": "project.*", "action": "admin", "constraint": None},
        # maintainer
        {"id": "p020", "role_id": "maintainer", "resource": "project.dag.view", "action": "read", "constraint": None},
        {"id": "p021", "role_id": "maintainer", "resource": "project.dag.run", "action": "write", "constraint": None},
        {"id": "p022", "role_id": "maintainer", "resource": "project.git.mr.*", "action": "admin", "constraint": None},
        {"id": "p023", "role_id": "maintainer", "resource": "project.git.branch.*", "action": "write", "constraint": None},
        {"id": "p024", "role_id": "maintainer", "resource": "project.dev.read", "action": "read", "constraint": None},
        # developer
        {"id": "p030", "role_id": "developer", "resource": "project.dag.view", "action": "read", "constraint": None},
        {"id": "p031", "role_id": "developer", "resource": "project.dag.run", "action": "write", "constraint": None},
        {"id": "p032", "role_id": "developer", "resource": "project.git.mr.create", "action": "write", "constraint": None},
        {"id": "p033", "role_id": "developer", "resource": "project.git.branch.*", "action": "write", "constraint": None},
        {"id": "p034", "role_id": "developer", "resource": "project.dev.read", "action": "read", "constraint": None},
        # viewer
        {"id": "p040", "role_id": "viewer", "resource": "project.dag.view", "action": "read", "constraint": None},
        {"id": "p041", "role_id": "viewer", "resource": "project.git.read", "action": "read", "constraint": None},
        {"id": "p042", "role_id": "viewer", "resource": "project.dev.read", "action": "read", "constraint": None},
    ])


def downgrade() -> None:
    op.drop_table("permissions")
    op.drop_table("roles")