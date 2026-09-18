"""Add persistent validation workspace and immutable validation-run snapshots.

Revision ID: 20260916_0004
Revises: 20260907_0003
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260916_0004"
down_revision = "20260907_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_validation_workspace_account"),
    )
    op.create_index(
        "ix_validation_workspaces_account_id",
        "validation_workspaces",
        ["account_id"],
        unique=True,
    )

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
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_runs_account_id", "validation_runs", ["account_id"])
    op.create_index(
        "ix_validation_runs_simulation_run_id", "validation_runs", ["simulation_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_validation_runs_simulation_run_id", table_name="validation_runs")
    op.drop_index("ix_validation_runs_account_id", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_index("ix_validation_workspaces_account_id", table_name="validation_workspaces")
    op.drop_table("validation_workspaces")
