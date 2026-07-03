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

from dataclasses import dataclass
from math import isfinite

from cinder.actuation import PulleyActuationResult, PulleyActuationState
from cinder.geometry import GeometryPosition
from cinder.inertia import AxialTranslationInertia, ResolvedInertias
from cinder.integration import CVTDynamicState
from cinder.vehicle import RoadLoadResult

from ..snapshot import CVTDynamicsModel


@dataclass(frozen=True, slots=True)
class DeadzoneSnapshot:
    """Known-state data for the reduced primary-disengaged model.

    ``primary_geometry`` is evaluated at the live primary actuator coordinate
    ``s``.  ``locked_geometry`` is evaluated once at ``s_engage`` and owns the
    low-ratio secondary radius used by the imposed belt-secondary lock.
    """

    state: CVTDynamicState
    primary_geometry: GeometryPosition
    locked_geometry: GeometryPosition
    primary_axial_inertia: AxialTranslationInertia
    primary_actuation: PulleyActuationResult
    engine_torque: float
    road_load: RoadLoadResult
    inertias: ResolvedInertias

    @property
    def belt_secondary_lock_radius(self) -> float:
        """Return the fixed secondary effective radius in deadzone."""

        return self.locked_geometry.secondary.effective

    @property
    def primary_rotational_inertia(self) -> float:
        """Return the directly rotating primary inertia."""

        return self.inertias.primary.rotational_inertia

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
            + self.inertias.belt.mass * radius * radius
        )

    @property
    def secondary_external_torque(self) -> float:
        """Return the signed vehicle/road torque applied to the secondary."""

        return self.road_load.secondary_external_torque

    @property
    def belt_secondary_speed_residual(self) -> float:
        """Return ``v_b - r_s omega_s`` for the imposed neutral lock."""

        return (
            self.state.belt_speed
            - self.belt_secondary_lock_radius * self.state.secondary_angular_speed
        )


def build_deadzone_snapshot(
    *,
    model: CVTDynamicsModel,
    state: CVTDynamicState,
) -> DeadzoneSnapshot:
    """Build one frozen deadzone snapshot without invoking engaged contact.

    The live geometry evaluation is used only for the primary movable-sheave
    actuator coordinate and its axial inertia.  The belt/secondary quantities
    intentionally come from the fixed engagement geometry, even when the live
    primary coordinate lies below engagement.
    """

    if not isinstance(model, CVTDynamicsModel):
        raise TypeError("model must be a CVTDynamicsModel instance.")
    if not isinstance(state, CVTDynamicState):
        raise TypeError("state must be a CVTDynamicState instance.")

    engagement_shift = model.geometry.spec.deadzone_shift
    if state.shift_position > engagement_shift:
        raise ValueError(
            "Deadzone snapshot requires shift_position <= geometry.spec.deadzone_shift."
        )

    primary_geometry = model.geometry.evaluate(state.shift_position)
    locked_geometry = model.geometry.evaluate(engagement_shift)
    primary_coordinate = primary_geometry.primary_axial_coordinate

    primary_actuation = model.primary_actuator.evaluate(
        PulleyActuationState(
            axial_position=primary_coordinate.value,
            axial_speed=primary_coordinate.d_value_ds * state.shift_speed,
            shaft_speed=state.primary_angular_speed,
        )
    )

    vehicle_distance = (
        model.road_load.final_drive.vehicle_distance_from_secondary_angle(
            secondary_shaft_angle=state.secondary_shaft_angle,
        )
    )
    grade_angle = model.road_profile.sample(
        vehicle_distance=vehicle_distance,
    ).grade_angle
    road_load = model.road_load.evaluate(
        secondary_angular_speed=state.secondary_angular_speed,
        grade_angle=grade_angle,
    )

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
        engine_torque=model.engine.evaluate(state.primary_angular_speed),
        road_load=road_load,
        inertias=model.inertias,
    )
    _validate_deadzone_snapshot(snapshot)
    return snapshot


def _validate_deadzone_snapshot(snapshot: DeadzoneSnapshot) -> None:
    for name, value in (
        ("belt_secondary_lock_radius", snapshot.belt_secondary_lock_radius),
        ("primary_rotational_inertia", snapshot.primary_rotational_inertia),
        ("secondary_belt_locked_inertia", snapshot.secondary_belt_locked_inertia),
        ("engine_torque", snapshot.engine_torque),
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
