"""Associate tunes with CVTs and designate a default per saved CVT version."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "20261005_0010"
down_revision = "20261004_0009"
branch_labels = None
depends_on = None


def digest(document):
    return hashlib.sha256(
        json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("experiments")}
    if "cvt_object_id" not in columns:
        with op.batch_alter_table(
            "experiments",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch:
            batch.add_column(sa.Column("cvt_object_id", sa.String(36)))
            batch.create_foreign_key(
                "fk_experiments_cvt_object_id_cvt_designs",
                "cvt_designs",
                ["cvt_object_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch.create_index("ix_experiments_cvt_object_id", ["cvt_object_id"])
    metadata = sa.MetaData()

    def table(name):
        return sa.Table(name, metadata, autoload_with=bind)

    experiments, revisions, setups, cvts, designs = [
        table(name)
        for name in (
            "experiments",
            "experiment_revisions",
            "vehicle_assembly_versions",
            "cvt_design_versions",
            "cvt_designs",
        )
    ]
    setup_cvts = dict(
        bind.execute(sa.select(setups.c.id, setups.c.cvt_design_version_id)).all()
    )
    cvt_rows = {row.id: row for row in bind.execute(sa.select(cvts)).mappings()}
    for row in bind.execute(sa.select(revisions)).mappings().all():
        document = dict(row.document)
        if document.get("kind") != "tunes":
            continue
        if "setup_revision_id" in document:
            document["cvt_revision_id"] = setup_cvts[document.pop("setup_revision_id")]
            bind.execute(
                revisions.update()
                .where(revisions.c.id == row.id)
                .values(document=document, content_hash=digest(document))
            )
        bind.execute(
            experiments.update()
            .where(experiments.c.current_revision_id == row.id)
            .values(cvt_object_id=cvt_rows[document["cvt_revision_id"]].cvt_design_id)
        )
    if "setup_object_id" in columns:
        with op.batch_alter_table(
            "experiments",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch:
            for index in inspector.get_indexes("experiments"):
                if "setup_object_id" in index["column_names"]:
                    batch.drop_index(index["name"])
            for fk in inspector.get_foreign_keys("experiments"):
                if fk["constrained_columns"] == ["setup_object_id"]:
                    batch.drop_constraint(
                        fk["name"]
                        or "fk_experiments_setup_object_id_vehicle_assemblies",
                        type_="foreignkey",
                    )
            batch.drop_column("setup_object_id")
    if "cvt_default_tunes" not in inspector.get_table_names():
        op.create_table(
            "cvt_default_tunes",
            sa.Column(
                "cvt_revision_id",
                sa.String(36),
                sa.ForeignKey("cvt_design_versions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "tune_id",
                sa.String(36),
                sa.ForeignKey("experiments.id", ondelete="RESTRICT"),
                nullable=False,
            ),
        )
    defaults = table("cvt_default_tunes")
    # Reflect again after dropping the obsolete column.
    metadata.remove(experiments)
    experiments = table("experiments")
    objects = {row.id: row for row in bind.execute(sa.select(designs)).mappings()}
    existing = set(bind.execute(sa.select(defaults.c.cvt_revision_id)).scalars())
    for cvt in cvt_rows.values():
        if cvt.id in existing:
            continue
        candidates = bind.execute(
            sa.select(experiments.c.id, revisions.c.document)
            .join(revisions, experiments.c.current_revision_id == revisions.c.id)
            .where(
                experiments.c.cvt_object_id == cvt.cvt_design_id,
                experiments.c.is_sample.is_(True),
                experiments.c.name == "R00 · Reference",
                experiments.c.archived.is_(False),
            )
        ).all()
        tune_id = next(
            (
                row.id
                for row in candidates
                if row.document.get("cvt_revision_id") == cvt.id
            ),
            None,
        )
        if not tune_id:
            tune_id, revision_id = str(uuid4()), str(uuid4())
            now = datetime.now(timezone.utc)
            obj = objects[cvt.cvt_design_id]
            document = {
                "kind": "tunes",
                "name": "Default tune",
                "notes": "",
                "cvt_revision_id": cvt.id,
                "values": {},
            }
            bind.execute(
                experiments.insert().values(
                    id=tune_id,
                    account_id=obj.account_id,
                    kind="tunes",
                    name="Default tune",
                    archived=False,
                    is_sample=obj.catalog_status
                    in ("seeded_example", "official", "admin_curated"),
                    cvt_object_id=cvt.cvt_design_id,
                    current_revision_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            bind.execute(
                revisions.insert().values(
                    id=revision_id,
                    experiment_id=tune_id,
                    number=1,
                    document=document,
                    content_hash=digest(document),
                    change_note="Initial tune for this CVT version.",
                    created_by_user_id=cvt.created_by_user_id,
                    created_at=now,
                )
            )
            bind.execute(
                experiments.update()
                .where(experiments.c.id == tune_id)
                .values(current_revision_id=revision_id)
            )
        bind.execute(defaults.insert().values(cvt_revision_id=cvt.id, tune_id=tune_id))


def downgrade():
    raise RuntimeError(
        "CVT-owned tunes cannot be assigned to a unique vehicle. Restore a database backup to downgrade."
    )
