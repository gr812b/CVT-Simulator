"""Versioned lightweight run preview generation.

Full simulation results can be large and are intentionally evictable.  A run
preview is the durable chart-ready slice that lets users browse historical runs
without keeping every full trace online.  Preview payloads are profile-versioned
so we can change columns, point caps, or downsampling methods later without
pretending the old shape was wrong.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class PreviewProfile:
    """Configuration for one generated preview payload."""

    name: str
    version: int
    max_points: int
    columns: tuple[str, ...]
    downsample_method: str = "uniform_stride_include_endpoints"


DEFAULT_PREVIEW_PROFILE = PreviewProfile(
    name="default_run_preview",
    version=1,
    max_points=500,
    columns=(
        "time_s",
        "state.primary_angular_speed",
        "state.secondary_angular_speed",
        "state.shift_position",
        "kinematics.ratio",
        "vehicle.speed",
        "vehicle.distance",
    ),
)


def build_run_preview(
    result: JsonDict,
    *,
    profile: PreviewProfile = DEFAULT_PREVIEW_PROFILE,
    source_result_hash: str | None = None,
) -> JsonDict:
    """Build a durable, downsampled preview payload from a full result.

    The payload is deliberately self-describing.  Older runs can keep their
    original preview profile forever, while future runs may use a new profile
    with different columns or compression settings.
    """

    table = result.get("report_table")
    base_payload: JsonDict = {
        "artifact_kind": "preview_series",
        "profile_name": profile.name,
        "profile_version": profile.version,
        "source_result_hash": source_result_hash,
        "downsample_method": profile.downsample_method,
        "max_points": profile.max_points,
        "axis_key": None,
        "original_row_count": 0,
        "preview_row_count": 0,
        "sampled_indices": [],
        "columns": [],
    }
    if not isinstance(table, dict):
        return base_payload

    table_columns = [column for column in table.get("columns", []) if isinstance(column, dict)]
    selected_columns = [column for column in table_columns if column.get("key") in profile.columns]
    original_row_count = _infer_row_count(table, selected_columns)
    sampled_indices = _sample_indices(original_row_count, profile.max_points)

    preview_columns = []
    for column in selected_columns:
        values = column.get("values", [])
        if not isinstance(values, list):
            continue
        preview_column = {
            key: copy.deepcopy(value) for key, value in column.items() if key != "values"
        }
        preview_column["values"] = [
            copy.deepcopy(values[index]) for index in sampled_indices if index < len(values)
        ]
        preview_columns.append(preview_column)

    base_payload.update(
        {
            "axis_key": table.get("axis_key"),
            "original_row_count": original_row_count,
            "preview_row_count": len(sampled_indices),
            "sampled_indices": sampled_indices,
            "columns": preview_columns,
        }
    )
    return base_payload


def _infer_row_count(table: JsonDict, selected_columns: list[JsonDict]) -> int:
    row_count = table.get("row_count")
    if isinstance(row_count, int) and row_count >= 0:
        return row_count
    lengths = []
    for column in selected_columns:
        values = column.get("values")
        if isinstance(values, list):
            lengths.append(len(values))
    return max(lengths, default=0)


def _sample_indices(row_count: int, max_points: int) -> list[int]:
    if row_count <= 0 or max_points <= 0:
        return []
    if row_count <= max_points:
        return list(range(row_count))
    if max_points == 1:
        return [0]

    # Rounded linear spacing preserves both endpoints while avoiding a numpy
    # dependency in the backend layer.  A set removes rare rounding duplicates.
    raw_indices = {round(index * (row_count - 1) / (max_points - 1)) for index in range(max_points)}
    indices = sorted(int(index) for index in raw_indices)
    if indices[0] != 0:
        indices.insert(0, 0)
    if indices[-1] != row_count - 1:
        indices.append(row_count - 1)
    return indices
