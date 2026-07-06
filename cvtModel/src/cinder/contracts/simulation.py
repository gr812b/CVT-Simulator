"""Reusable simulation metrics derived from an already materialized result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from cinder.execution.hybrid.cvt_regime import CVTEngagementState
from cinder.model.cvt.contact import ContactInterface
from cinder.results import CVTIntegrationResult


@dataclass(frozen=True, slots=True)
class SimulationMetrics:
    """Standard cross-run quantities with explicit units in their keys.

    Values that are not meaningful for a boundary or reporting configuration
    are ``None`` rather than invented values.  This keeps vehicle-independent
    dyno cases and vehicle cases on the same public contract.
    """

    duration_s: float
    completed: bool
    termination_reason: str
    transition_count: int
    first_engagement_time_s: float | None
    primary_slip_duration_s: float
    secondary_slip_duration_s: float
    primary_angular_speed_max_rad_per_s: float | None
    secondary_angular_speed_max_rad_per_s: float | None
    vehicle_speed_max_m_per_s: float | None
    vehicle_distance_final_m: float | None
    ratio_min: float | None
    ratio_max: float | None
    ratio_final: float | None
    primary_traction_utilization_max: float | None
    secondary_traction_utilization_max: float | None
    engine_work_final_J: float | None
    output_boundary_work_final_J: float | None
    primary_slip_dissipation_final_J: float | None
    secondary_slip_dissipation_final_J: float | None

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


def summarize_simulation(result: CVTIntegrationResult) -> SimulationMetrics:
    """Summarize a report without re-integrating or inspecting new states."""

    if not isinstance(result, CVTIntegrationResult):
        raise TypeError("result must be a CVTIntegrationResult.")

    def maximum(key: str) -> float | None:
        values = _signal_values(result, key)
        return _finite_max(values)

    def final(key: str) -> float | None:
        values = _signal_values(result, key)
        return _finite_last(values)

    primary_slip_duration = 0.0
    secondary_slip_duration = 0.0
    first_engagement_time: float | None = None
    for segment in result.trace.segments:
        mode = segment.mode
        if (
            mode.engagement is CVTEngagementState.ENGAGED
            and first_engagement_time is None
        ):
            first_engagement_time = segment.start_time
        if mode.contact_regime is None:
            continue
        duration = segment.end_time - segment.start_time
        if ContactInterface.PRIMARY in mode.contact_regime.mode.slipping_interfaces:
            primary_slip_duration += duration
        if ContactInterface.SECONDARY in mode.contact_regime.mode.slipping_interfaces:
            secondary_slip_duration += duration

    return SimulationMetrics(
        duration_s=result.summary.duration,
        completed=result.completed,
        termination_reason=result.termination_reason,
        transition_count=result.summary.transition_count,
        first_engagement_time_s=first_engagement_time,
        primary_slip_duration_s=primary_slip_duration,
        secondary_slip_duration_s=secondary_slip_duration,
        primary_angular_speed_max_rad_per_s=maximum("state.primary_angular_speed"),
        secondary_angular_speed_max_rad_per_s=maximum("state.secondary_angular_speed"),
        vehicle_speed_max_m_per_s=maximum("vehicle.speed"),
        vehicle_distance_final_m=final("vehicle.distance"),
        ratio_min=_finite_min(
            _signal_values(result, "geometry.effective_ratio_secondary_over_primary")
        ),
        ratio_max=maximum("geometry.effective_ratio_secondary_over_primary"),
        ratio_final=final("geometry.effective_ratio_secondary_over_primary"),
        primary_traction_utilization_max=maximum("contact.primary_lambda"),
        secondary_traction_utilization_max=maximum("contact.secondary_lambda"),
        engine_work_final_J=final("observer.engine_work"),
        output_boundary_work_final_J=final("observer.output_boundary_work"),
        primary_slip_dissipation_final_J=final("observer.primary_slip_dissipation"),
        secondary_slip_dissipation_final_J=final("observer.secondary_slip_dissipation"),
    )


def _signal_values(result: CVTIntegrationResult, key: str) -> np.ndarray:
    parts = [
        segment.signals[key].values
        for segment in result.segments
        if key in segment.signals
    ]
    if not parts:
        return np.empty(0, dtype=float)
    return np.concatenate(parts)


def _finite_max(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return None if finite.size == 0 else float(np.max(finite))


def _finite_min(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return None if finite.size == 0 else float(np.min(finite))


def _finite_last(values: np.ndarray) -> float | None:
    finite_indices = np.flatnonzero(np.isfinite(values))
    return None if finite_indices.size == 0 else float(values[finite_indices[-1]])
