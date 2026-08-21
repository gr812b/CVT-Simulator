"""State-frozen mechanics for the primary-disengaged CVT deadzone."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Final

from cinder.model.cvt.actuation import PulleyElementContribution
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

    ``primary_mechanism`` is the same pulley-element contribution used by the
    engaged plant. It may contain affine coupling to primary shaft acceleration
    and global shift acceleration, which is why deadzone free motion uses a
    small coupled solve rather than assuming the actuator is a known force.
    """

    state: CVTState
    primary_geometry: GeometryPosition
    locked_geometry: GeometryPosition
    primary_axial_inertia: AxialTranslationInertia
    primary_mechanism: PulleyElementContribution
    primary_rigid_rotational_inertia: float
    shaft_boundaries: CVTShaftBoundaryValues
    inertias: ResolvedInertias

    @property
    def primary_actuation(self) -> AffineClosureScalar:
        """Compatibility alias for the mechanism's local closing-force relation."""

        return self.primary_mechanism.closing_force

    @property
    def belt_secondary_lock_radius(self) -> float:
        return self.locked_geometry.secondary.effective

    @property
    def primary_rotational_inertia(self) -> float:
        """Rigid primary inertia not already carried by a mounted coupling."""

        return self.primary_rigid_rotational_inertia

    @property
    def secondary_belt_locked_inertia(self) -> float:
        """Return fixed-shift secondary plus belt transport inertia."""

        radius = self.belt_secondary_lock_radius
        return (
            self.inertias.secondary.absolute_rotation_inertia
            + self.shaft_boundaries.secondary.equivalent_inertia
            + self.inertias.belt.mass * radius * radius
        )

    @property
    def road_load(self) -> RoadLoadResult | None:
        return self.shaft_boundaries.secondary.metadata.get("road_load")

    @property
    def vehicle_road_load(self) -> RoadLoadResult:
        road_load = self.road_load
        if road_load is None:
            raise RuntimeError(
                "This shaft boundary does not provide vehicle road-load data."
            )
        return road_load

    @property
    def primary_external_torque(self) -> float:
        return self.shaft_boundaries.primary.external_torque

    @property
    def secondary_external_torque(self) -> float:
        return self.shaft_boundaries.secondary.external_torque

    @property
    def belt_secondary_speed_residual(self) -> float:
        return (
            self.state.belt_speed
            - self.belt_secondary_lock_radius * self.state.secondary_angular_speed
        )


def build_deadzone_snapshot(
    *,
    model: MechanicalCVTPlant,
    state: CVTState,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> DeadzoneSnapshot:
    """Build one frozen deadzone snapshot without invoking engaged contact."""

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

    if shaft_boundaries is None:
        shaft_boundaries = CVTShaftBoundaryValues.zero()
    if not isinstance(shaft_boundaries, CVTShaftBoundaryValues):
        raise TypeError("shaft_boundaries must be a CVTShaftBoundaryValues.")

    primary_geometry = model.geometry.evaluate_deadzone(state.shift_position)
    locked_geometry = model.geometry.evaluate_deadzone(engagement_shift)
    primary_coordinate = primary_geometry.primary_axial_coordinate

    primary_context = model.primary_actuation_context(
        state=state,
        geometry=primary_geometry,
    )
    primary_mechanism = model.primary_actuator.evaluate_element(primary_context)

    primary_axial_inertia = model.inertias.axial_translation.evaluate(
        primary_axial_coordinate=primary_coordinate,
        secondary_axial_coordinate=locked_geometry.secondary_axial_coordinate,
        belt_axial_coordinate=locked_geometry.belt_axial_coordinate,
    ).primary

    # If a helical coupling is present, its element already carries the movable
    # member's rotational inertia and relative-motion terms. Otherwise the
    # movable sheave rotates rigidly with the shaft in deadzone.
    primary_rigid_rotational_inertia = (
        model.inertias.primary.fixed_rotating_hardware_inertia
        + shaft_boundaries.primary.equivalent_inertia
    )
    if model.primary_helical_coupling is None:
        primary_rigid_rotational_inertia += (
            model.inertias.primary.movable_sheave_rotational_inertia
        )

    snapshot = DeadzoneSnapshot(
        state=state,
        primary_geometry=primary_geometry,
        locked_geometry=locked_geometry,
        primary_axial_inertia=primary_axial_inertia,
        primary_mechanism=primary_mechanism,
        primary_rigid_rotational_inertia=primary_rigid_rotational_inertia,
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
