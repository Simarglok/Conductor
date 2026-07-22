"""merge existing Alembic heads

Revision ID: b0c1d2e3f4a5
Revises: a4b2c3d4e5f6, a2b2c3d4e5f6
Create Date: 2026-07-18 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = (
    "a4b2c3d4e5f6",
    "a2b2c3d4e5f6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
