"""create merge_requests table

Revision ID: a4b2c3d4e5f6
Revises: a3b2c3d4e5f6
Create Date: 2026-07-15 04:00:00.000000
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a4b2c3d4e5f6"
down_revision: Union[str, None] = "a3b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merge_requests",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_branch", sa.String(128), nullable=False),
        sa.Column("target_branch", sa.String(128), nullable=False, server_default="main"),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("merge_commit_sha", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("merge_requests")