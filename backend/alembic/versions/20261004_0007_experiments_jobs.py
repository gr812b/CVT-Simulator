"""Immutable experiments and a durable, account-limited run queue.

Preserve every old run/result and tune. Copy legacy named tunes into revision 1
when their setup has a saved version; original tune rows remain untouched.
"""

import hashlib
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261004_0007"
down_revision = "20261004_0006"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    payload = sa.JSON().with_variant(JSONB(), "postgresql")
    tables = sa.inspect(bind).get_table_names()
    if "experiments" not in tables:
        op.create_table(
            "experiments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "account_id",
                sa.String(36),
                sa.ForeignKey("accounts.id"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("name", sa.String(240), nullable=False),
            sa.Column("archived", sa.Boolean(), nullable=False),
            sa.Column("is_sample", sa.Boolean(), nullable=False),
            sa.Column(
                "setup_object_id",
                sa.String(36),
                sa.ForeignKey("vehicle_assemblies.id", ondelete="RESTRICT"),
            ),
            sa.Column("current_revision_id", sa.String(36)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_table(
            "experiment_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "experiment_id",
                sa.String(36),
                sa.ForeignKey("experiments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("document", payload, nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("change_note", sa.String(2000), nullable=False),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("experiment_id", "number"),
        )
        with op.batch_alter_table("experiments") as batch:
            batch.create_foreign_key(
                "fk_experiments_current_revision_id_experiment_revisions",
                "experiment_revisions",
                ["current_revision_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        for table, column in (
            ("experiments", "account_id"),
            ("experiments", "kind"),
            ("experiment_revisions", "experiment_id"),
        ):
            op.create_index(f"ix_{table}_{column}", table, [column])

    columns = {c["name"] for c in sa.inspect(bind).get_columns("runs")}
    if "request_key" not in columns:
        with op.batch_alter_table("runs") as batch:
            for column in (
                "vehicle_assembly_version_id",
                "engine_version_id",
                "cvt_design_version_id",
                "output_system_version_id",
            ):
                batch.alter_column(column, existing_type=sa.String(36), nullable=True)
            batch.add_column(
                sa.Column(
                    "name", sa.String(240), nullable=False, server_default="Simulation"
                )
            )
            batch.add_column(
                sa.Column(
                    "source", sa.String(20), nullable=False, server_default="library"
                )
            )
            for column, size in (
                ("request_key", 64),
                ("request_hash", 64),
                ("worker_token", 36),
                ("parent_run_id", 36),
            ):
                batch.add_column(sa.Column(column, sa.String(size)))
            for column in ("provenance", "runtime_identity", "execution_options"):
                batch.add_column(
                    sa.Column(column, payload, nullable=False, server_default="{}")
                )
            for column in ("heartbeat_at", "deadline_at", "cancel_requested_at"):
                batch.add_column(sa.Column(column, sa.DateTime(timezone=True)))
            batch.create_foreign_key(
                "fk_runs_parent_run_id_runs", "runs", ["parent_run_id"], ["id"]
            )
            batch.create_unique_constraint(
                "uq_runs_account_id_request_key", ["account_id", "request_key"]
            )

    if "run_notifications" not in tables:
        op.create_table(
            "run_notifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "account_id",
                sa.String(36),
                sa.ForeignKey("accounts.id"),
                nullable=False,
            ),
            sa.Column(
                "run_id",
                sa.String(36),
                sa.ForeignKey("runs.id"),
                nullable=False,
            ),
            sa.Column(
                "user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("run_id", "user_id"),
        )
        op.create_index(
            "ix_run_notifications_account_id", "run_notifications", ["account_id"]
        )
        op.create_index(
            "ix_run_notifications_user_id", "run_notifications", ["user_id"]
        )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("runs")}
    if "ix_runs_queue" not in indexes:
        op.create_index("ix_runs_queue", "runs", ["status", "submitted_at"])

    metadata = sa.MetaData()
    # Upgrade only with the pre-M3 API processes stopped. Those processes never
    # had durable worker leases; do not leave their interrupted rows blocking an
    # account forever. Frozen inputs and existing artifacts remain untouched.
    runs = sa.Table("runs", metadata, autoload_with=bind)
    notices = sa.Table("run_notifications", metadata, autoload_with=bind)
    members = sa.Table("account_users", metadata, autoload_with=bind)
    interrupted = list(
        bind.execute(
            sa.select(runs.c.id, runs.c.account_id).where(
                runs.c.status.in_(("queued", "validating", "running")),
                runs.c.request_key.is_(None),
            )
        ).mappings()
    )
    for row in interrupted:
        now = datetime.now(timezone.utc)
        bind.execute(
            runs.update()
            .where(runs.c.id == row["id"])
            .values(
                status="failed",
                completed_at=now,
                error={
                    "code": "migration_interrupted",
                    "message": "This pre-M3 run was interrupted during upgrade. Rerun its frozen inputs as a new durable job.",
                },
            )
        )
        for user_id in bind.scalars(
            sa.select(members.c.user_id).where(
                members.c.account_id == row["account_id"]
            )
        ):
            bind.execute(
                notices.insert().values(
                    id=str(
                        uuid5(
                            NAMESPACE_URL,
                            f"cinder-web:m3:interrupted:{row['id']}:{user_id}",
                        )
                    ),
                    account_id=row["account_id"],
                    user_id=user_id,
                    run_id=row["id"],
                    created_at=now,
                )
            )
    tunes = sa.Table("tunes", metadata, autoload_with=bind)
    setups = sa.Table("vehicle_assemblies", metadata, autoload_with=bind)
    experiments = sa.Table("experiments", metadata, autoload_with=bind)
    revisions = sa.Table("experiment_revisions", metadata, autoload_with=bind)
    query = sa.select(tunes, setups.c.released_version_id).join(
        setups, tunes.c.vehicle_assembly_id == setups.c.id
    )
    for row in bind.execute(query).mappings():
        if not row["released_version_id"] or bind.scalar(
            sa.select(experiments.c.id).where(experiments.c.id == row["id"])
        ):
            continue
        revision_id = str(
            uuid5(NAMESPACE_URL, f"cinder-web:m3:legacy-tune:{row['id']}:1")
        )
        document = {
            "kind": "tunes",
            "name": row["name"],
            "notes": row["notes"] or "",
            "setup_revision_id": row["released_version_id"],
            "values": row["values"],
        }
        encoded = json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        bind.execute(
            experiments.insert().values(
                id=row["id"],
                account_id=row["account_id"],
                kind="tunes",
                name=row["name"],
                archived=row["deleted_at"] is not None,
                is_sample=False,
                setup_object_id=row["vehicle_assembly_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
        bind.execute(
            revisions.insert().values(
                id=revision_id,
                experiment_id=row["id"],
                number=1,
                document=document,
                content_hash=hashlib.sha256(encoded.encode()).hexdigest(),
                change_note="Preserved pre-M3 tune values and pinned the then-current setup revision.",
                created_at=row["updated_at"],
            )
        )
        bind.execute(
            experiments.update()
            .where(experiments.c.id == row["id"])
            .values(current_revision_id=revision_id)
        )


def downgrade():
    raise RuntimeError(
        "M3 contains durable run and revision history. Restore a verified pre-M3 backup instead of discarding it with downgrade."
    )
