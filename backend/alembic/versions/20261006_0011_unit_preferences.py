"""Persist personal display-unit preferences on users."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0011"
down_revision = "20261005_0010"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "unit_preferences" not in columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column(
                    "unit_preferences",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                )
            )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "unit_preferences" in columns:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("unit_preferences")
