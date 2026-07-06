"""JSON-safe projections of CINDER results and static-study data.

Projection is intentionally separate from model objects.  Mechanics-first
objects remain NumPy/dataclass friendly for Python users, while this module
turns them into stable ordinary dictionaries for a backend boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

import numpy as np

from cinder.model.system import CVTDynamicState
from cinder.results import CVTIntegrationResult
from cinder.studies.actuation import ClampingForceResponseField
from cinder.studies.geometry import (
    GeometryDesignSummary,
    GeometryFeasibilityReport,
    GeometryPathTable,
    RadiusPlaneField,
    RatioSensitivityField,
)

from .conventions import PUBLIC_CONTRACT_VERSION, describe_public_field, public_conventions
from .simulation import summarize_simulation
from .validation import AssemblyValidationReport


def project_clamping_force_response(field: ClampingForceResponseField) -> dict[str, Any]:
    """Project one actuator response field as self-describing numeric columns."""

    return _project_columns(
        kind="clamping_force_response",
        shape=field.shape,
        axis_keys=tuple(axis.column_key for axis in field.axes),
        columns=field.columns,
    )


def project_geometry_path(path: GeometryPathTable) -> dict[str, Any]:
    """Project one sampled geometry path as ordinary named numeric columns."""

    columns = {
        "shift_m": path.shift,
        "primary_outer_radius_m": path.primary_outer_radius,
        "secondary_outer_radius_m": path.secondary_outer_radius,
        "primary_effective_radius_m": path.primary_effective_radius,
        "secondary_effective_radius_m": path.secondary_effective_radius,
        "ratio": path.ratio,
        "ratio_change_per_m_shift": path.ratio_change_per_m_shift,
        "ratio_change_per_mm_shift": path.ratio_change_per_mm_shift,
        "primary_wrap_angle_rad": path.primary_wrap_angle,
        "secondary_wrap_angle_rad": path.secondary_wrap_angle,
    }
    return _project_columns(
        kind="geometry_path",
        shape=path.shift.shape,
        axis_keys=("shift_m",),
        columns=columns,
    )


def project_radius_plane(field: RadiusPlaneField) -> dict[str, Any]:
    return _project_columns(
        kind="radius_plane",
        shape=field.ratio.shape,
        axis_keys=("primary_outer_radius_m", "secondary_outer_radius_m"),
        columns={
            "primary_outer_radius_m": field.primary_outer_radius,
            "secondary_outer_radius_m": field.secondary_outer_radius,
            "ratio": field.ratio,
            "implied_belt_outer_length_m": field.implied_belt_outer_length,
            "feasible_mask": field.feasible_mask,
        },
    )


def project_ratio_sensitivity_field(field: RatioSensitivityField) -> dict[str, Any]:
    return _project_columns(
        kind="ratio_sensitivity_field",
        shape=field.ratio_change_per_m_shift.shape,
        axis_keys=("primary_outer_radius_m", "secondary_outer_radius_m"),
        columns={
            "primary_outer_radius_m": field.primary_outer_radius,
            "secondary_outer_radius_m": field.secondary_outer_radius,
            "ratio_change_per_m_shift": field.ratio_change_per_m_shift,
            "ratio_change_per_mm_shift": field.ratio_change_per_mm_shift,
            "feasible_mask": field.feasible_mask,
        },
    )


def project_geometry_summary(summary: GeometryDesignSummary) -> dict[str, Any]:
    """Project scalar geometry summary values with descriptors."""

    return _project_scalars("geometry_summary", {
        "center_distance_m": summary.center_distance,
        "active_shift_travel_m": summary.active_shift_travel,
        "active_primary_radial_travel_m": summary.active_primary_radial_travel,
        "maximum_ratio": summary.maximum_ratio,
        "minimum_ratio": summary.minimum_ratio,
        "ratio_span": summary.ratio_span,
        "primary_outer_radius_min_m": summary.primary_outer_radius_min,
        "primary_outer_radius_max_m": summary.primary_outer_radius_max,
        "secondary_outer_radius_min_m": summary.secondary_outer_radius_min,
        "secondary_outer_radius_max_m": summary.secondary_outer_radius_max,
        "primary_effective_radius_min_m": summary.primary_effective_radius_min,
        "primary_effective_radius_max_m": summary.primary_effective_radius_max,
        "secondary_effective_radius_min_m": summary.secondary_effective_radius_min,
        "secondary_effective_radius_max_m": summary.secondary_effective_radius_max,
    })


def project_geometry_feasibility(report: GeometryFeasibilityReport) -> dict[str, Any]:
    return {
        "is_feasible": report.is_feasible,
        "findings": [
            {
                "severity": issue.severity,
                "code": issue.code,
                "message": issue.message,
                "shift_m": issue.shift,
            }
            for issue in report.issues
        ],
    }


def project_assembly_validation(report: AssemblyValidationReport) -> dict[str, Any]:
    return report.as_dict()


def project_simulation_result(result: CVTIntegrationResult) -> dict[str, Any]:
    """Project report-grid simulation data, raw transitions, and standard metrics."""

    if not isinstance(result, CVTIntegrationResult):
        raise TypeError("result must be a CVTIntegrationResult.")
    return {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "kind": "simulation_result",
        "conventions": public_conventions().as_dict(),
        "metrics": summarize_simulation(result).as_dict(),
        "summary": {
            "duration_s": result.summary.duration,
            "segment_count": result.summary.segment_count,
            "transition_count": result.summary.transition_count,
            "final_state": _project_state(result.summary.final_state),
        },
        "warnings": list(result.warnings),
        "segments": [
            {
                "mode": _project_mode(segment.mode),
                "time_s": segment.time.tolist(),
                "signals": [
                    {
                        **describe_public_field(
                            signal.key,
                            unit=signal.unit,
                            label=signal.label,
                        ).as_dict(),
                        "group": signal.group,
                        "values": signal.values.tolist(),
                    }
                    for signal in segment.signals.values()
                ],
            }
            for segment in result.segments
        ],
        "transitions": [
            {
                "time_s": record.time,
                "previous_mode": _project_mode(record.previous_mode),
                "fired_event_names": list(record.fired_event_names),
                "reason": record.transition.reason,
                "terminates": record.transition.terminates,
                "metadata": to_jsonable(record.transition.metadata),
                "post_transition_state": _project_state(record.post_transition_state),
            }
            for record in result.transitions
        ],
    }


def _project_columns(
    *,
    kind: str,
    shape: tuple[int, ...],
    axis_keys: tuple[str, ...],
    columns: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    return {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "kind": kind,
        "shape": list(shape),
        "axis_keys": list(axis_keys),
        "columns": [
            {
                **describe_public_field(key).as_dict(),
                "values": np.asarray(values).tolist(),
            }
            for key, values in columns.items()
        ],
    }


def _project_scalars(kind: str, values: Mapping[str, float]) -> dict[str, Any]:
    return {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "kind": kind,
        "scalars": [
            {**describe_public_field(key).as_dict(), "value": value}
            for key, value in values.items()
        ],
    }


def _project_mode(mode: object) -> dict[str, Any]:
    # CVTOperatingRegime has stable enum fields.  Kept duck-typed to leave this
    # adapter independent from the execution package's import graph.
    engagement = getattr(mode, "engagement", None)
    constraint = getattr(mode, "shift_constraint", None)
    contact = getattr(mode, "contact_regime", None)
    contact_mode = None if contact is None else getattr(contact.mode, "value", str(contact.mode))
    return {
        "engagement": getattr(engagement, "value", str(engagement)),
        "shift_constraint": getattr(constraint, "value", str(constraint)),
        "contact_mode": contact_mode,
    }


def _project_state(vector: object) -> dict[str, float]:
    state = CVTDynamicState.from_vector(vector)
    return {
        "primary_angular_speed_rad_per_s": state.primary_angular_speed,
        "secondary_angular_speed_rad_per_s": state.secondary_angular_speed,
        "belt_speed_m_per_s": state.belt_speed,
        "shift_position_m": state.shift_position,
        "shift_speed_m_per_s": state.shift_speed,
        "secondary_shaft_angle_rad": state.secondary_shaft_angle,
    }


def to_jsonable(value: Any) -> Any:
    """Convert ordinary CINDER/numpy values to JSON-safe Python primitives."""

    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]
    return value
