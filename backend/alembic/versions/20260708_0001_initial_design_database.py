"""Initial versioned design database.

Revision ID: 20260708_0001
Revises:
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

from app.database.base import Base
from app.database import models  # noqa: F401  # register model metadata

revision = "20260708_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
