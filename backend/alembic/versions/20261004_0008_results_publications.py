"""Add fixed public configuration bundles and independent-copy attribution.

Existing design revisions, private visibility, runs and artifacts are untouched.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261004_0008"
down_revision = "20261004_0007"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    payload = sa.JSON().with_variant(JSONB(), "postgresql")
    if "physical_publications" not in tables:
        op.create_table(
            "physical_publications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "account_id",
                sa.String(36),
                sa.ForeignKey("accounts.id"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("source_object_id", sa.String(36), nullable=False),
            sa.Column("source_revision_id", sa.String(36), nullable=False),
            sa.Column("revision_number", sa.Integer, nullable=False),
            sa.Column("publication_number", sa.Integer, nullable=False),
            *[
                sa.Column(name, sa.String(length), nullable=False)
                for name, length in (
                    ("name", 240),
                    ("description", 4000),
                    ("author", 240),
                    ("source_label", 240),
                    ("source_url", 500),
                    ("snapshot_hash", 64),
                )
            ],
            *[
                sa.Column(name, payload, nullable=False)
                for name in ("document", "dependencies", "tuning_schema", "validation")
            ],
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("visibility", sa.String(20), nullable=False),
            sa.Column("gallery_listed", sa.Boolean, nullable=False),
            sa.Column("access_version", sa.Integer, nullable=False),
            sa.Column("sample", sa.Boolean, nullable=False),
            sa.UniqueConstraint(
                "kind", "source_revision_id", name="uq_publication_source_revision"
            ),
        )
        op.create_index(
            "ix_physical_publications_account_id",
            "physical_publications",
            ["account_id"],
        )
        op.create_index(
            "ix_physical_publications_source_object_id",
            "physical_publications",
            ["source_object_id"],
        )
        op.create_index(
            "ix_publications_gallery",
            "physical_publications",
            ["visibility", "gallery_listed", "published_at"],
        )
    if "configuration_copies" not in tables:
        op.create_table(
            "configuration_copies",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "account_id",
                sa.String(36),
                sa.ForeignKey("accounts.id"),
                nullable=False,
            ),
            sa.Column("request_key", sa.String(64), nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("object_id", sa.String(36), nullable=False),
            sa.Column(
                "publication_id",
                sa.String(36),
                sa.ForeignKey("physical_publications.id"),
            ),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id")),
            sa.Column("scenario_id", sa.String(36), sa.ForeignKey("experiments.id")),
            sa.Column("copied_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "account_id", "request_key", name="uq_configuration_copy_request"
            ),
        )
        op.create_index(
            "ix_configuration_copies_account_id", "configuration_copies", ["account_id"]
        )
        op.create_index(
            "ix_configuration_copies_object_id", "configuration_copies", ["object_id"]
        )


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-M4 backup to roll back; publication and copy history is not discarded automatically."
    )
