"""create airflow_instances table

Revision ID: a3b2c3d4e5f6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 00:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a3b2c3d4e5f6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create airflowstatus enum type ──
    postgresql.ENUM(
        "creating", "running", "stopped", "failed", name="airflowstatus"
    ).create(op.get_bind())

    # ── Create airflow_instances table ──
    op.create_table(
        "airflow_instances",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("internal_url", sa.String(256), nullable=False),
        sa.Column("external_url", sa.String(256), nullable=True),
        sa.Column("db_name", sa.String(64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "creating", "running", "stopped", "failed",
                name="airflowstatus",
                create_type=False,
            ),
            server_default="creating",
            nullable=False,
        ),
        sa.Column("admin_user", sa.String(128), nullable=False),
        sa.Column("admin_password_encrypted", sa.Text(), nullable=True),
        sa.Column("dev_user", sa.String(128), nullable=False),
        sa.Column("dev_password_encrypted", sa.Text(), nullable=True),
        sa.Column("viewer_user", sa.String(128), nullable=False),
        sa.Column("viewer_password_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("airflow_instances")
    postgresql.ENUM(name="airflowstatus").drop(op.get_bind())