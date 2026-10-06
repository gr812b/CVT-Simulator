"""Add reusable belt revisions; preserve existing embedded CVT belts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261004_0006"
down_revision = "20261003_0005"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # 0001 uses live metadata on fresh installations; upgrades need these tables.
    if "belts" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "belts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "account_id",
                sa.String(36),
                sa.ForeignKey("accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(240), nullable=False),
            sa.Column("slug", sa.String(180)),
            sa.Column("description", sa.Text()),
            sa.Column("visibility", sa.String(20), nullable=False),
            sa.Column("gallery_listed", sa.Boolean(), nullable=False),
            sa.Column("lifecycle_status", sa.String(32), nullable=False),
            sa.Column("catalog_status", sa.String(32), nullable=False),
            sa.Column("catalog_priority", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("source_label", sa.String(240)),
            sa.Column("source_url", sa.String(500)),
            sa.Column("source_notes", sa.Text()),
            sa.Column("draft_payload", sa.JSON().with_variant(JSONB(), "postgresql")),
            sa.Column("draft_updated_at", sa.DateTime(timezone=True)),
            sa.Column("released_version_id", sa.String(36)),
            sa.Column("forked_from_version_id", sa.String(36)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
        )
        op.create_table(
            "belt_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "belt_id",
                sa.String(36),
                sa.ForeignKey("belts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column(
                "belt_payload",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=False,
            ),
            sa.Column(
                "summary", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
            ),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False),
            sa.Column("payload_schema_name", sa.String(120), nullable=False),
            sa.Column("payload_schema_version", sa.Integer(), nullable=False),
            sa.Column("validation_status", sa.String(32), nullable=False),
            sa.Column("validation_messages", sa.JSON(), nullable=False),
            sa.Column(
                "created_by_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("release_notes", sa.Text()),
            sa.Column("visibility_at_release", sa.String(20), nullable=False),
            sa.Column(
                "attribution_institution_id",
                sa.String(36),
                sa.ForeignKey("institutions.id", ondelete="SET NULL"),
            ),
            sa.Column("attribution_label", sa.String(200)),
            sa.Column(
                "superseded_by_version_id",
                sa.String(36),
                sa.ForeignKey("belt_versions.id", ondelete="SET NULL"),
            ),
            sa.Column("deprecated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("belt_id", "version_number"),
        )
        with op.batch_alter_table("belts") as batch:
            batch.create_foreign_key(
                "fk_belts_released_version_id_belt_versions",
                "belt_versions",
                ["released_version_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_foreign_key(
                "fk_belts_forked_from_version_id_belt_versions",
                "belt_versions",
                ["forked_from_version_id"],
                ["id"],
                ondelete="SET NULL",
            )
        for name, table, columns in (
            ("ix_belts_account_id", "belts", ["account_id"]),
            ("ix_belts_slug", "belts", ["slug"]),
            ("ix_belt_versions_belt_id", "belt_versions", ["belt_id"]),
            ("ix_belt_versions_payload_hash", "belt_versions", ["payload_hash"]),
        ):
            op.create_index(name, table, columns)
    if "belt_version_id" not in {
        c["name"] for c in sa.inspect(bind).get_columns("cvt_design_versions")
    }:
        with op.batch_alter_table("cvt_design_versions") as batch:
            batch.add_column(sa.Column("belt_version_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_cvt_design_versions_belt_version_id_belt_versions",
                "belt_versions",
                ["belt_version_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def downgrade():
    with op.batch_alter_table("cvt_design_versions") as batch:
        batch.drop_constraint(
            "fk_cvt_design_versions_belt_version_id_belt_versions", type_="foreignkey"
        )
        batch.drop_column("belt_version_id")
    with op.batch_alter_table("belts") as batch:
        batch.drop_constraint(
            "fk_belts_released_version_id_belt_versions", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_belts_forked_from_version_id_belt_versions", type_="foreignkey"
        )
    op.drop_table("belt_versions")
    op.drop_table("belts")
