"""JSON-safe projections of CINDER results and static-study data.

Projection remains separate from mechanics.  CINDER model objects stay useful
for Python/numerical callers, while this module supplies stable dictionaries for
an HTTP boundary or saved result artifact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from math import isfinite
from typing import Any

import numpy as np

from cinder.model.system import CVTState
from cinder.results import CVTIntegrationResult
from cinder.studies.actuation import ClampingForceResponseField
from cinder.studies.geometry import (
    GeometryDesignSummary,
    GeometryFeasibilityReport,
    GeometryPathTable,
    RadiusPlaneField,
    RatioSensitivityField,
)

from .conventions import (
    PUBLIC_CONTRACT_VERSION,
    describe_public_field,
    public_conventions,
)
from .simulation import summarize_simulation
from .validation import AssemblyValidationReport

# ---------------------------------------------------------------------------
# Static studies
# ---------------------------------------------------------------------------


def project_clamping_force_response(
    field: ClampingForceResponseField,
) -> dict[str, Any]:
    """Project one actuator response field as self-describing numeric columns."""

    return _project_columns(
        kind="clamping_force_response",
        shape=field.shape,
        axis_keys=tuple(axis.column_key for axis in field.axes),
        columns=field.columns,
    )


def project_geometry_path(path: GeometryPathTable) -> dict[str, Any]:
    """Project one sampled geometry path as ordinary named numeric columns."""

    return _project_columns(
        kind="geometry_path",
        shape=path.shift.shape,
        axis_keys=("shift_m",),
        columns={
            "shift_m": path.shift,
            "primary_outer_radius_m": path.primary_outer_radius,
            "secondary_outer_radius_m": path.secondary_outer_radius,
            "primary_effective_radius_m": path.primary_effective_radius,
            "secondary_effective_radius_m": path.secondary_effective_radius,
            "ratio": path.ratio,
            "ratio_change_per_m_shift": path.ratio_change_per_m_shift,
            "primary_wrap_angle_rad": path.primary_wrap_angle,
            "secondary_wrap_angle_rad": path.secondary_wrap_angle,
        },
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
            "feasible_mask": field.feasible_mask,
        },
    )


def project_geometry_summary(summary: GeometryDesignSummary) -> dict[str, Any]:
    """Project scalar geometry summary values with descriptors."""

    return _project_scalars(
        "geometry_summary",
        {
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
        },
    )


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


# ---------------------------------------------------------------------------
# Simulation reports
# ---------------------------------------------------------------------------


def project_simulation_result(
    result: CVTIntegrationResult,
    *,
    include_reported_segments: bool = False,
    include_raw_trace: bool = False,
) -> dict[str, Any]:
    """Project standard report data, events, metrics, and optional raw trace.

    ``report_table`` is the default frontend-oriented surface: a continuous
    time-aligned column table across all hybrid segments. Event boundaries are
    intentionally retained as duplicate timestamps when a projection/reset
    creates a discontinuity. Detailed ``reported_segments`` and the accepted
    solver-mesh ``raw_trace`` are both opt-in because they can materially
    increase result payload size.
    """

    if not isinstance(result, CVTIntegrationResult):
        raise TypeError("result must be a CVTIntegrationResult.")

    payload: dict[str, Any] = {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "kind": "simulation_result",
        "conventions": public_conventions().as_dict(),
        "metrics": to_jsonable(summarize_simulation(result).as_dict()),
        "summary": {
            "duration_s": result.summary.duration,
            "segment_count": result.summary.segment_count,
            "transition_count": result.summary.transition_count,
            "final_state": _project_state(result.summary.final_state),
        },
        "warnings": list(result.warnings),
        "report_table": _project_report_table(result),
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
    if include_reported_segments:
        payload["reported_segments"] = [
            _project_reported_segment(segment) for segment in result.segments
        ]
    if include_raw_trace:
        payload["raw_trace"] = _project_raw_trace(result)
    return payload


def _project_reported_segment(segment: object) -> dict[str, Any]:
    time = np.asarray(getattr(segment, "time"), dtype=float)
    signals = getattr(segment, "signals")
    return {
        "mode": _project_mode(getattr(segment, "mode")),
        "time_s": _json_vector(time),
        "signals": [
            {
                **describe_public_field(
                    signal.key,
                    unit=signal.unit,
                    label=signal.label,
                ).as_dict(),
                "group": signal.group,
                "values": _json_vector(signal.values),
            }
            for signal in signals.values()
        ],
    }


def _project_report_table(result: CVTIntegrationResult) -> dict[str, Any]:
    """Flatten reported hybrid segments into one front-end-ready column table."""

    signal_metadata: dict[str, tuple[str, str, str, str]] = {}
    ordered_signal_keys: list[str] = []
    for segment in result.segments:
        for key, signal in segment.signals.items():
            if key not in signal_metadata:
                signal_metadata[key] = (
                    signal.unit,
                    signal.label,
                    signal.group,
                    describe_public_field(
                        signal.key, unit=signal.unit, label=signal.label
                    ).dimension,
                )
                ordered_signal_keys.append(key)

    time_values: list[float | None] = []
    columns: dict[str, list[float | None]] = {key: [] for key in ordered_signal_keys}
    segment_ranges: list[dict[str, Any]] = []
    start_index = 0
    for index, segment in enumerate(result.segments):
        time = np.asarray(segment.time, dtype=float)
        time_values.extend(_json_vector(time))
        point_count = int(time.size)
        for key in ordered_signal_keys:
            signal = segment.signals.get(key)
            if signal is None:
                columns[key].extend([None] * point_count)
            else:
                columns[key].extend(_json_vector(signal.values))
        segment_ranges.append(
            {
                "segment_index": index,
                "start_index": start_index,
                "end_index": start_index + point_count - 1,
                "mode": _project_mode(segment.mode),
            }
        )
        start_index += point_count

    projected_columns: list[dict[str, Any]] = [
        {
            **describe_public_field("time_s").as_dict(),
            "group": "time",
            "values": time_values,
        }
    ]
    for key in ordered_signal_keys:
        unit, label, group, _dimension = signal_metadata[key]
        projected_columns.append(
            {
                **describe_public_field(key, unit=unit, label=label).as_dict(),
                "group": group,
                "values": columns[key],
            }
        )

    return {
        "axis_key": "time_s",
        "row_count": len(time_values),
        "columns": projected_columns,
        "segment_ranges": segment_ranges,
        "preserves_duplicate_transition_times": True,
    }


def _project_raw_trace(result: CVTIntegrationResult) -> dict[str, Any]:
    state_columns = (
        ("primary_angular_speed_rad_per_s", "Primary angular speed", "rad/s"),
        ("secondary_angular_speed_rad_per_s", "Secondary angular speed", "rad/s"),
        ("belt_speed_m_per_s", "Belt speed", "m/s"),
        ("shift_position_m", "Shift position", "m"),
        ("shift_speed_m_per_s", "Shift speed", "m/s"),
    )
    segments = []
    for segment in result.trace.segments:
        state = np.asarray(segment.state, dtype=float)
        segments.append(
            {
                "mode": _project_mode(segment.mode),
                "time_s": _json_vector(segment.time),
                "state_columns": [
                    {
                        **describe_public_field(key, unit=unit, label=label).as_dict(),
                        "values": _json_vector(state[row_index]),
                    }
                    for row_index, (key, label, unit) in enumerate(state_columns)
                ],
            }
        )
    return {
        "kind": "adaptive_hybrid_trace",
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Generic JSON helpers
# ---------------------------------------------------------------------------


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
                "values": _json_array(values),
            }
            for key, values in columns.items()
        ],
    }


def _project_scalars(kind: str, values: Mapping[str, float]) -> dict[str, Any]:
    return {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "kind": kind,
        "scalars": [
            {**describe_public_field(key).as_dict(), "value": to_jsonable(value)}
            for key, value in values.items()
        ],
    }


def _project_mode(mode: object) -> dict[str, Any]:
    engagement = getattr(mode, "engagement", None)
    constraint = getattr(mode, "shift_constraint", None)
    contact = getattr(mode, "contact_regime", None)
    contact_mode = (
        None if contact is None else getattr(contact.mode, "value", str(contact.mode))
    )
    return {
        "engagement": getattr(engagement, "value", str(engagement)),
        "shift_constraint": getattr(constraint, "value", str(constraint)),
        "contact_mode": contact_mode,
    }


def _project_state(vector: object) -> dict[str, float]:
    values = np.asarray(vector, dtype=float)
    if values.ndim == 1 and values.size > 5:
        values = values[:5]
    state = CVTState.from_vector(values)
    return {
        "primary_angular_speed_rad_per_s": state.primary_angular_speed,
        "secondary_angular_speed_rad_per_s": state.secondary_angular_speed,
        "belt_speed_m_per_s": state.belt_speed,
        "shift_position_m": state.shift_position,
        "shift_speed_m_per_s": state.shift_speed,
    }


def _json_vector(values: object) -> list[float | None]:
    vector = np.asarray(values, dtype=float)
    if vector.ndim != 1:
        raise ValueError("Expected one-dimensional numeric values for projection.")
    return [float(value) if isfinite(float(value)) else None for value in vector]


def _json_array(values: object) -> Any:
    array = np.asarray(values)
    if array.ndim == 0:
        item = array.item()
        return to_jsonable(item)
    if array.dtype == np.bool_ or array.dtype == bool:
        return array.tolist()
    if np.issubdtype(array.dtype, np.number):
        if array.ndim == 1:
            return _json_vector(array)
        return _json_array_recursive(array)
    return to_jsonable(array.tolist())


def _json_array_recursive(array: np.ndarray) -> list[Any]:
    if array.ndim == 1:
        return _json_vector(array)
    return [_json_array_recursive(np.asarray(item)) for item in array]


def to_jsonable(value: Any) -> Any:
    """Convert ordinary CINDER/numpy values to strict JSON-safe primitives."""

    if isinstance(value, np.ndarray):
        return _json_array(value)
    if isinstance(value, np.generic):
        return to_jsonable(value.item())
    if isinstance(value, float):
        return value if isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]
    return value
