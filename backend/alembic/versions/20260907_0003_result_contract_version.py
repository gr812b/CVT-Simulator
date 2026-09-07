"""Track CINDER simulation-result contract versions separately.

Revision ID: 20260907_0003
Revises: 20260824_0002
Create Date: 2026-09-07

The existing ``contract_schema_version`` column records the frozen input
simulation-document schema.  Result projections now evolve independently, so
runs and cache entries need a separate result-contract version.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260907_0003"
down_revision = "20260824_0002"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    for table_name in ("run_cache_entries", "runs"):
        if "result_contract_version" in _column_names(table_name):
            continue
        op.add_column(
            table_name,
            sa.Column(
                "result_contract_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )


def downgrade() -> None:
    for table_name in ("runs", "run_cache_entries"):
        if "result_contract_version" not in _column_names(table_name):
            continue
        op.drop_column(table_name, "result_contract_version")
