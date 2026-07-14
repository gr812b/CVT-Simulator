from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "sequence",
    "name",
    "analysis_role",
    "kind",
    "anchor_latitude",
    "anchor_longitude",
    "corrected_anchor_latitude",
    "corrected_anchor_longitude",
    "extent_method",
    "event_start_latitude",
    "event_start_longitude",
    "event_end_latitude",
    "event_end_longitude",
    "final_group_id",
    "grouping_notes",
)

NULL_TOKENS = {"", "N/A", "NA", "NONE", "NULL"}
FILL_TOKEN = "FILL"


@dataclass(frozen=True)
class DefinitionIssue:
    severity: str
    sequence: int | None
    name: str
    field: str
    code: str
    message: str


class DefinitionValidationError(ValueError):
    def __init__(self, issues: Iterable[DefinitionIssue]):
        self.issues = [issue for issue in issues if issue.severity == "error"]
        details = "\n".join(
            f"- row {issue.sequence or '?'} {issue.name!r}, {issue.field}: {issue.message}"
            for issue in self.issues[:20]
        )
        remainder = len(self.issues) - 20
        if remainder > 0:
            details += f"\n- ...and {remainder} more errors"
        super().__init__(f"Obstacle definition CSV is not ready:\n{details}")


def load_definition_csv(
    path: Path,
    *,
    allow_incomplete: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the finalized form and convert it to the geometry core contract.

    Strict mode refuses unresolved ``FILL`` cells. ``allow_incomplete`` exists
    only for pipeline development: unresolved interval extents use the old
    default windows, unresolved anchors use the supplied anchor, and grouping
    candidates are kept separate. Every fallback is recorded as a warning.
    """

    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raw.columns = [column.strip() for column in raw.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(f"Definition CSV is missing required columns: {missing}")
    raw = raw.apply(lambda column: column.str.strip() if column.dtype == object else column)

    issues: list[DefinitionIssue] = []
    output_rows: list[dict[str, object]] = []

    sequence_numbers = pd.to_numeric(raw["sequence"], errors="coerce")
    if sequence_numbers.isna().any():
        bad_rows = raw.index[sequence_numbers.isna()].tolist()
        raise ValueError(f"Non-numeric sequence values on CSV rows: {[row + 2 for row in bad_rows]}")
    raw["sequence"] = sequence_numbers.astype(int)

    if raw["sequence"].duplicated().any():
        duplicates = sorted(raw.loc[raw["sequence"].duplicated(keep=False), "sequence"].unique())
        raise ValueError(f"Duplicate sequence values: {duplicates}")
    if raw["name"].str.casefold().duplicated().any():
        duplicates = raw.loc[raw["name"].str.casefold().duplicated(keep=False), "name"].tolist()
        raise ValueError(f"Duplicate feature names: {duplicates}")

    for _, row in raw.sort_values("sequence").iterrows():
        sequence = int(row["sequence"])
        name = str(row["name"])
        if not name:
            issues.append(_issue("error", sequence, name, "name", "blank_name", "must not be blank"))
        analysis_role = str(row["analysis_role"]).casefold()
        if analysis_role not in {"track_event", "turn_context"}:
            issues.append(
                _issue(
                    "error",
                    sequence,
                    name,
                    "analysis_role",
                    "invalid_analysis_role",
                    "must be track_event or turn_context",
                )
            )
        kind = str(row["kind"]).casefold()
        if kind not in {"point", "interval", "turn_apex"}:
            issues.append(_issue("error", sequence, name, "kind", "invalid_kind", "must be point, interval, or turn_apex"))
        extent_method = str(row["extent_method"]).upper()
        if extent_method not in {"AUTO_POINT_WINDOW", "AUTO_TURN_WINDOW", "GPS_START_END_REQUIRED"}:
            issues.append(
                _issue(
                    "error",
                    sequence,
                    name,
                    "extent_method",
                    "invalid_extent_method",
                    "must be AUTO_POINT_WINDOW, AUTO_TURN_WINDOW, or GPS_START_END_REQUIRED",
                )
            )

        anchor_lat = _required_number(row["anchor_latitude"], sequence, name, "anchor_latitude", issues)
        anchor_lon = _required_number(row["anchor_longitude"], sequence, name, "anchor_longitude", issues)
        corrected_lat = _optional_number(row["corrected_anchor_latitude"])
        corrected_lon = _optional_number(row["corrected_anchor_longitude"])
        for field in ("corrected_anchor_latitude", "corrected_anchor_longitude"):
            _validate_optional_number_token(row[field], sequence, name, field, issues)
        corrected_fill = _is_fill(row["corrected_anchor_latitude"]) or _is_fill(row["corrected_anchor_longitude"])
        if corrected_fill:
            _incomplete(
                allow_incomplete,
                issues,
                sequence,
                name,
                "corrected_anchor_latitude/longitude",
                "unresolved_corrected_anchor",
                "replace both corrected anchor cells with numeric coordinates",
                "using the existing anchor for this provisional run",
            )
        elif (corrected_lat is None) != (corrected_lon is None):
            issues.append(_issue("error", sequence, name, "corrected_anchor_latitude/longitude", "partial_coordinate_pair", "provide both corrected coordinates or neither"))

        latitude = corrected_lat if corrected_lat is not None else anchor_lat
        longitude = corrected_lon if corrected_lon is not None else anchor_lon
        if latitude is not None and not -90 <= latitude <= 90:
            issues.append(_issue("error", sequence, name, "anchor_latitude", "latitude_out_of_range", "latitude must be between -90 and 90"))
        if longitude is not None and not -180 <= longitude <= 180:
            issues.append(_issue("error", sequence, name, "anchor_longitude", "longitude_out_of_range", "longitude must be between -180 and 180"))

        start_lat = _optional_number(row["event_start_latitude"])
        start_lon = _optional_number(row["event_start_longitude"])
        end_lat = _optional_number(row["event_end_latitude"])
        end_lon = _optional_number(row["event_end_longitude"])
        extent_values = (
            row["event_start_latitude"],
            row["event_start_longitude"],
            row["event_end_latitude"],
            row["event_end_longitude"],
        )
        for field, value in zip(
            (
                "event_start_latitude",
                "event_start_longitude",
                "event_end_latitude",
                "event_end_longitude",
            ),
            extent_values,
        ):
            _validate_optional_number_token(value, sequence, name, field, issues)
        has_extent_fill = any(_is_fill(value) for value in extent_values)
        numeric_extent_count = sum(value is not None for value in (start_lat, start_lon, end_lat, end_lon))
        requires_extent = kind == "interval" or str(row["extent_method"]).casefold() == "gps_start_end_required"
        if requires_extent and (has_extent_fill or numeric_extent_count == 0):
            _incomplete(
                allow_incomplete,
                issues,
                sequence,
                name,
                "event_start/end_latitude/longitude",
                "unresolved_interval_extent",
                "replace all four interval start/end cells with numeric coordinates",
                "using an assumed interval window for this provisional run",
            )
        elif numeric_extent_count not in {0, 4}:
            issues.append(_issue("error", sequence, name, "event_start/end_latitude/longitude", "partial_extent", "provide all four start/end coordinates or none"))
        for field, value, low, high in (
            ("event_start_latitude", start_lat, -90.0, 90.0),
            ("event_start_longitude", start_lon, -180.0, 180.0),
            ("event_end_latitude", end_lat, -90.0, 90.0),
            ("event_end_longitude", end_lon, -180.0, 180.0),
        ):
            if value is not None and not low <= value <= high:
                issues.append(
                    _issue(
                        "error",
                        sequence,
                        name,
                        field,
                        "coordinate_out_of_range",
                        f"must be between {low:g} and {high:g}",
                    )
                )

        final_group_id = str(row["final_group_id"]).strip()
        grouping_notes = str(row["grouping_notes"]).strip()
        if _is_fill(final_group_id) or _is_null(final_group_id):
            _incomplete(
                allow_incomplete,
                issues,
                sequence,
                name,
                "final_group_id",
                "unresolved_grouping",
                "assign a group ID; use the same ID only for inseparable rows",
                "keeping this row separate for this provisional run",
            )
            final_group_id = f"TEMP_E{sequence:02d}"
        if not _is_null(row.get("candidate_group", "")) and _is_fill(grouping_notes):
            _incomplete(
                allow_incomplete,
                issues,
                sequence,
                name,
                "grouping_notes",
                "unresolved_grouping_notes",
                "record which rows were grouped or why they remain separate",
                "grouping rationale remains unresolved for this provisional run",
            )

        output_rows.append(
            {
                "sequence": sequence,
                "name": name,
                "analysis_role": analysis_role,
                "kind": kind,
                "latitude": latitude,
                "longitude": longitude,
                "start_latitude": start_lat,
                "start_longitude": start_lon,
                "end_latitude": end_lat,
                "end_longitude": end_lon,
                "extent_method": extent_method,
                "candidate_group": str(row.get("candidate_group", "")).strip(),
                "candidate_members": str(row.get("candidate_members", "")).strip(),
                "final_group_id": final_group_id,
                "grouping_notes": grouping_notes,
                "input_format": "finalized_csv_form",
                "feature_before_m": np.nan,
                "feature_after_m": np.nan,
                "entry_before_start_m": np.nan,
                "entry_gap_m": np.nan,
                "exit_gap_m": np.nan,
                "exit_length_m": np.nan,
                "recovery_limit_m": np.nan,
            }
        )

    out = pd.DataFrame(output_rows).sort_values("sequence").reset_index(drop=True)
    _validate_groups(out, issues)

    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise DefinitionValidationError(issues)

    group_sizes = out.groupby("final_group_id")["sequence"].transform("size")
    out["compound_group"] = out["final_group_id"].where(group_sizes > 1, "SEPARATE")
    issue_table = pd.DataFrame([issue.__dict__ for issue in issues], columns=list(DefinitionIssue.__annotations__))
    return out, issue_table


def _validate_groups(out: pd.DataFrame, issues: list[DefinitionIssue]) -> None:
    for group_id, members in out.groupby("final_group_id", sort=False):
        sequences = sorted(members["sequence"].astype(int).tolist())
        if len(sequences) > 1 and sequences != list(range(sequences[0], sequences[-1] + 1)):
            first = members.sort_values("sequence").iloc[0]
            issues.append(
                _issue(
                    "error",
                    int(first["sequence"]),
                    str(first["name"]),
                    "final_group_id",
                    "nonconsecutive_group",
                    f"group {group_id!r} contains nonconsecutive sequences {sequences}",
                )
            )
        if len(sequences) > 1 and members["analysis_role"].eq("turn_context").all():
            first = members.sort_values("sequence").iloc[0]
            issues.append(
                _issue(
                    "warning",
                    int(first["sequence"]),
                    str(first["name"]),
                    "final_group_id",
                    "turn_only_group",
                    f"group {group_id!r} contains only turn-context rows",
                )
            )


def _required_number(value: object, sequence: int, name: str, field: str, issues: list[DefinitionIssue]) -> float | None:
    parsed = _optional_number(value)
    if parsed is None:
        issues.append(_issue("error", sequence, name, field, "required_number", "must contain a numeric value"))
    return parsed


def _optional_number(value: object) -> float | None:
    text = str(value).strip()
    if _is_null(text) or _is_fill(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _validate_optional_number_token(
    value: object,
    sequence: int,
    name: str,
    field: str,
    issues: list[DefinitionIssue],
) -> None:
    if _is_null(value) or _is_fill(value):
        return
    try:
        float(str(value).strip())
    except ValueError:
        issues.append(
            _issue(
                "error",
                sequence,
                name,
                field,
                "invalid_number",
                "must be numeric, N/A, or FILL",
            )
        )


def _is_null(value: object) -> bool:
    return str(value).strip().upper() in NULL_TOKENS


def _is_fill(value: object) -> bool:
    return str(value).strip().upper() == FILL_TOKEN


def _incomplete(
    allow: bool,
    issues: list[DefinitionIssue],
    sequence: int,
    name: str,
    field: str,
    code: str,
    error_message: str,
    warning_message: str,
) -> None:
    issues.append(_issue("warning" if allow else "error", sequence, name, field, code, warning_message if allow else error_message))


def _issue(severity: str, sequence: int | None, name: str, field: str, code: str, message: str) -> DefinitionIssue:
    return DefinitionIssue(severity, sequence, name, field, code, message)
