"""State-frozen mechanics for the primary-disengaged CVT deadzone.

Deadzone deliberately does *not* reuse the engaged contact snapshot.  Below
primary engagement, the primary actuator coordinate continues to move, while
belt geometry and the secondary/belt lock remain frozen at the engagement
configuration:

    x_p = s,
    geometry_belt = geometry(s_engage),
    v_b = r_s,engage omega_s.

This module contains only known-state quantities.  It carries no lambda,
normal-resultant, tension-loop, or engaged traction quantities.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Final

from cinder.model.cvt.actuation import PulleyActuationContext, PulleyClosureChannels
from cinder.model.cvt.geometry import GeometryPosition
from cinder.model.cvt.inertia import AxialTranslationInertia, ResolvedInertias
from cinder.model.cvt.closure import AffineClosureScalar
from cinder.model.system.state import CVTState
from cinder.model.boundaries.vehicle import RoadLoadResult

from cinder.model.system.evaluator import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues

_DEADZONE_SHIFT_DOMAIN_TOLERANCE: Final[float] = 1.0e-12


@dataclass(frozen=True, slots=True)
class DeadzoneSnapshot:
    """Known-state data for the reduced primary-disengaged model.

    ``primary_geometry`` is evaluated at the live primary actuator coordinate
    ``s``.  ``locked_geometry`` is evaluated once at ``s_engage`` and owns the
    low-ratio secondary radius used by the imposed belt-secondary lock.
    """

    state: CVTState
    primary_geometry: GeometryPosition
    locked_geometry: GeometryPosition
    primary_axial_inertia: AxialTranslationInertia
    primary_actuation: AffineClosureScalar
    shaft_boundaries: CVTShaftBoundaryValues
    inertias: ResolvedInertias

    @property
    def belt_secondary_lock_radius(self) -> float:
        """Return the fixed secondary effective radius in deadzone."""

        return self.locked_geometry.secondary.effective

    @property
    def primary_rotational_inertia(self) -> float:
        """Return the directly rotating primary inertia."""

        return (
            self.inertias.primary.absolute_rotation_inertia
            + self.shaft_boundaries.primary.equivalent_inertia
        )

    @property
    def secondary_belt_locked_inertia(self) -> float:
        """Return secondary absolute inertia plus belt transport inertia.

        The belt is represented as a lumped transport mass moving at
        ``v_b = r_s omega_s``.  Its kinetic energy therefore contributes
        ``m_b r_s^2`` to the locked secondary rotational inertia.
        """

        radius = self.belt_secondary_lock_radius
        return (
            self.inertias.secondary.absolute_rotation_inertia
            + self.shaft_boundaries.secondary.equivalent_inertia
            + self.inertias.belt.mass * radius * radius
        )

    @property
    def road_load(self) -> RoadLoadResult | None:
        """Return vehicle road data when supplied by the shaft boundary."""

        return self.shaft_boundaries.secondary.metadata.get("road_load")

    @property
    def vehicle_road_load(self) -> RoadLoadResult:
        """Return vehicle road data or raise for a direct shaft boundary."""

        road_load = self.road_load
        if road_load is None:
            raise RuntimeError(
                "This shaft boundary does not provide vehicle road-load data."
            )
        return road_load

    @property
    def primary_external_torque(self) -> float:
        """Return the signed torque applied to the primary shaft."""

        return self.shaft_boundaries.primary.external_torque

    @property
    def secondary_external_torque(self) -> float:
        """Return the signed torque applied to the secondary shaft."""

        return self.shaft_boundaries.secondary.external_torque

    @property
    def belt_secondary_speed_residual(self) -> float:
        """Return ``v_b - r_s omega_s`` for the imposed neutral lock."""

        return (
            self.state.belt_speed
            - self.belt_secondary_lock_radius * self.state.secondary_angular_speed
        )


def build_deadzone_snapshot(
    *,
    time: float,
    model: MechanicalCVTPlant,
    state: CVTState,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> DeadzoneSnapshot:
    """Build one frozen deadzone snapshot without invoking engaged contact.

    The live geometry evaluation is used only for the primary movable-sheave
    actuator coordinate and its axial inertia.  The belt/secondary quantities
    intentionally come from the fixed engagement geometry, even when the live
    primary coordinate lies below engagement.
    """

    if not isfinite(time):
        raise ValueError("time must be finite.")
    if not isinstance(model, MechanicalCVTPlant):
        raise TypeError("model must be a MechanicalCVTPlant instance.")
    if not isinstance(state, CVTState):
        raise TypeError("state must be a CVTState instance.")

    engagement_shift = model.geometry.spec.deadzone_shift
    if state.shift_position > engagement_shift + _DEADZONE_SHIFT_DOMAIN_TOLERANCE:
        raise ValueError(
            "Deadzone snapshot requires shift_position <= geometry.spec.deadzone_shift."
        )

    if state.shift_position > engagement_shift:
        state = replace(state, shift_position=engagement_shift)

    primary_geometry = model.geometry.evaluate(state.shift_position)
    locked_geometry = model.geometry.evaluate(engagement_shift)
    primary_coordinate = primary_geometry.primary_axial_coordinate

    primary_actuation = model.primary_actuator.evaluate_relation(
        PulleyActuationContext(
            time=time,
            axial_position=primary_coordinate.value,
            axial_speed=primary_coordinate.d_value_ds * state.shift_speed,
            shaft_speed=state.primary_angular_speed,
            closure_channels=PulleyClosureChannels.primary(),
        )
    )

    if shaft_boundaries is None:
        shaft_boundaries = CVTShaftBoundaryValues.zero()
    if not isinstance(shaft_boundaries, CVTShaftBoundaryValues):
        raise TypeError("shaft_boundaries must be a CVTShaftBoundaryValues.")

    primary_axial_inertia = model.inertias.axial_translation.evaluate(
        primary_axial_coordinate=primary_coordinate,
        secondary_axial_coordinate=locked_geometry.secondary_axial_coordinate,
        belt_axial_coordinate=locked_geometry.belt_axial_coordinate,
    ).primary

    snapshot = DeadzoneSnapshot(
        state=state,
        primary_geometry=primary_geometry,
        locked_geometry=locked_geometry,
        primary_axial_inertia=primary_axial_inertia,
        primary_actuation=primary_actuation,
        shaft_boundaries=shaft_boundaries,
        inertias=model.inertias,
    )
    _validate_deadzone_snapshot(snapshot)
    return snapshot


def _validate_deadzone_snapshot(snapshot: DeadzoneSnapshot) -> None:
    for name, value in (
        ("belt_secondary_lock_radius", snapshot.belt_secondary_lock_radius),
        ("primary_rotational_inertia", snapshot.primary_rotational_inertia),
        ("secondary_belt_locked_inertia", snapshot.secondary_belt_locked_inertia),
        ("primary_external_torque", snapshot.primary_external_torque),
        ("secondary_external_torque", snapshot.secondary_external_torque),
    ):
        if not isfinite(value):
            raise ValueError(f"Deadzone snapshot {name} must be finite.")

    if snapshot.belt_secondary_lock_radius <= 0.0:
        raise ValueError("Deadzone secondary lock radius must be positive.")
    if snapshot.primary_rotational_inertia <= 0.0:
        raise ValueError("Deadzone primary rotational inertia must be positive.")
    if snapshot.secondary_belt_locked_inertia <= 0.0:
        raise ValueError("Deadzone secondary-belt locked inertia must be positive.")
    if snapshot.primary_axial_inertia.local_shift_acceleration_gain <= 0.0:
        raise ValueError(
            "Deadzone primary axial inertia must have positive shift gain."
        )
