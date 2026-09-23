"""Add persistent validation workspace and immutable validation-run snapshots.

Revision ID: 20260916_0004
Revises: 20260907_0003
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260916_0004"
down_revision = "20260907_0003"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name") is not None
    }


def upgrade() -> None:
    # Revision 0001 uses the live ORM metadata via Base.metadata.create_all().
    # On a brand-new database running today's code, that legacy bootstrap can
    # therefore create tables that historically belong to later migrations.
    # Keep this migration authoritative for real 0003 -> 0004 upgrades while
    # tolerating those objects already existing on a fresh full-chain upgrade.
    tables = _table_names()

    if "validation_workspaces" not in tables:
        op.create_table(
            "validation_workspaces",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("account_id", sa.String(length=36), nullable=False),
            sa.Column("setup_document", sa.JSON(), nullable=False),
            sa.Column("metrology", sa.JSON(), nullable=False),
            sa.Column("controller_templates", sa.JSON(), nullable=False),
            sa.Column("workflow_defaults", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["account_id"],
                ["accounts.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "account_id",
                name="uq_validation_workspace_account",
            ),
        )

    workspace_indexes = _index_names("validation_workspaces")
    if "ix_validation_workspaces_account_id" not in workspace_indexes:
        op.create_index(
            "ix_validation_workspaces_account_id",
            "validation_workspaces",
            ["account_id"],
            unique=True,
        )

    tables = _table_names()
    if "validation_runs" not in tables:
        op.create_table(
            "validation_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("account_id", sa.String(length=36), nullable=False),
            sa.Column("simulation_run_id", sa.String(length=36), nullable=True),
            sa.Column("source_filename", sa.String(length=512), nullable=False),
            sa.Column("raw_csv", sa.Text(), nullable=False),
            sa.Column("crop_start_s", sa.Float(), nullable=False),
            sa.Column("crop_end_s", sa.Float(), nullable=False),
            sa.Column("channel_config", sa.JSON(), nullable=False),
            sa.Column("initial_state_config", sa.JSON(), nullable=False),
            sa.Column("workspace_snapshot", sa.JSON(), nullable=False),
            sa.Column("resolved_document", sa.JSON(), nullable=False),
            sa.Column("result_snapshot", sa.JSON(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["account_id"],
                ["accounts.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    run_indexes = _index_names("validation_runs")
    if "ix_validation_runs_account_id" not in run_indexes:
        op.create_index(
            "ix_validation_runs_account_id",
            "validation_runs",
            ["account_id"],
        )
    if "ix_validation_runs_simulation_run_id" not in run_indexes:
        op.create_index(
            "ix_validation_runs_simulation_run_id",
            "validation_runs",
            ["simulation_run_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_validation_runs_simulation_run_id", table_name="validation_runs")
    op.drop_index("ix_validation_runs_account_id", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_index("ix_validation_workspaces_account_id", table_name="validation_workspaces")
    op.drop_table("validation_workspaces")
