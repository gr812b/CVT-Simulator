"""Repair legacy frontend ramp quadrant encoding in persisted tunes.

Revision ID: 20260824_0002
Revises: 20260708_0001
Create Date: 2026-08-24

Older frontend code encoded editor quadrant 2 as -1. CINDER has always used
canonical quadrant values 1, 2, 3, or 4, so those persisted -1 values are
invalid documents. This migration repairs only circular-segment quadrant=-1
values inside Tune.values and maps them to canonical quadrant 2.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260824_0002"
down_revision = "20260708_0001"
branch_labels = None
depends_on = None


def _repair_legacy_ramp_quadrants(value: Any) -> tuple[Any, bool]:
    if isinstance(value, list):
        changed = False
        repaired_items: list[Any] = []
        for item in value:
            repaired, item_changed = _repair_legacy_ramp_quadrants(item)
            repaired_items.append(repaired)
            changed = changed or item_changed
        return repaired_items, changed

    if isinstance(value, dict):
        changed = False
        repaired_dict: dict[str, Any] = {}
        for key, item in value.items():
            repaired, item_changed = _repair_legacy_ramp_quadrants(item)
            repaired_dict[key] = repaired
            changed = changed or item_changed

        if (
            repaired_dict.get("kind") == "circular_segment"
            and repaired_dict.get("quadrant") == -1
        ):
            repaired_dict["quadrant"] = 2
            changed = True

        return repaired_dict, changed

    return value, False


def upgrade() -> None:
    bind = op.get_bind()
    tunes = sa.table(
        "tunes",
        sa.column("id", sa.String()),
        sa.column("values", sa.JSON()),
    )

    rows = bind.execute(sa.select(tunes.c.id, tunes.c.values)).mappings().all()
    for row in rows:
        repaired_values, changed = _repair_legacy_ramp_quadrants(row["values"])
        if changed:
            bind.execute(
                sa.update(tunes)
                .where(tunes.c.id == row["id"])
                .values(values=repaired_values)
            )


def downgrade() -> None:
    # The -1 values were invalid CINDER documents, and there is no safe reason
    # to recreate them on downgrade.
    pass
