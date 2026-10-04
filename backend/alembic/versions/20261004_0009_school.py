"""Optional school on account profiles.

Revision ID: 20261004_0009
Revises: 20261004_0008
"""

import sqlalchemy as sa
from alembic import op

revision = "20261004_0009"
down_revision = "20261004_0008"
branch_labels = None
depends_on = None


def upgrade():
    if "school" not in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")
    }:
        op.add_column(
            "users",
            sa.Column("school", sa.String(200), nullable=False, server_default=""),
        )


def downgrade():
    op.drop_column("users", "school")
