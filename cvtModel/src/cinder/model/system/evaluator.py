"""Mechanical CVT plant evaluation.

The plant evaluates only CVT-owned mechanics. Engines, vehicles, dynos,
controllers, tires, and suspension models are external systems that provide
signed shaft boundary values at each call.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from cinder.model.cvt.actuation import (
    HelicalCouplingState,
    PulleyActuationContext,
    PulleyActuator,
    PulleyClosureChannels,
    PulleyElementContribution,
)
from cinder.model.cvt.actuation.forces import AxialSpringForce, CentrifugalRampForce
from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains, ClosureUnknown
from cinder.model.cvt.geometry import BeltPulleyGeometry, GeometryPosition
from cinder.model.cvt.inertia import AxialTranslationInertias, ResolvedInertias
from cinder.model.cvt.profiles import HelixShiftKinematics

from .assembly import BeltContactSpec, CVTAssemblySpec, HelicalPulleyCoupling
from .ports import CVTShaftBoundaryValues
from .state import CVTState


@dataclass(frozen=True, slots=True)
class DynamicsSnapshot:
    """State-frozen quantities shared by closure solves."""

    state: CVTState
    geometry: GeometryPosition
    axial_translation_inertias: AxialTranslationInertias

    primary_pulley: PulleyElementContribution
    secondary_pulley: PulleyElementContribution
    primary_actuation: AffineClosureScalar
    secondary_actuation: AffineClosureScalar

    primary_helix: HelixShiftKinematics | None
    secondary_helix: HelixShiftKinematics | None

    shaft_boundaries: CVTShaftBoundaryValues
    inertias: ResolvedInertias
    sheave_half_angle: float

    @property
    def road_load(self):
        return self.shaft_boundaries.secondary.metadata.get("road_load")

    @property
    def vehicle_road_load(self):
        road_load = self.road_load
        if road_load is None:
            raise RuntimeError(
                "This shaft boundary does not provide vehicle road-load data."
            )
        return road_load

    @property
    def vehicle_distance(self) -> float:
        if "vehicle_distance" in self.shaft_boundaries.secondary.metadata:
            return float(self.shaft_boundaries.secondary.metadata["vehicle_distance"])
        if "vehicle_position" in self.shaft_boundaries.secondary.metadata:
            return float(self.shaft_boundaries.secondary.metadata["vehicle_position"])
        raise RuntimeError("This shaft boundary does not provide vehicle distance.")

    @property
    def belt_transport_mass(self) -> float:
        return self.inertias.belt.mass

    @property
    def belt_linear_density(self) -> float:
        return self.inertias.belt.density * self.inertias.belt.cross_sectional_area

    @property
    def primary_boundary_equivalent_inertia(self) -> float:
        return self.shaft_boundaries.primary.equivalent_inertia

    @property
    def secondary_boundary_equivalent_inertia(self) -> float:
        return self.shaft_boundaries.secondary.equivalent_inertia

    @property
    def primary_rotational_inertia(self) -> float:
        return (
            self.inertias.primary.absolute_rotation_inertia
            + self.primary_boundary_equivalent_inertia
        )

    @property
    def secondary_fixed_rotational_inertia(self) -> float:
        return (
            self.inertias.secondary.fixed_side.total
            + self.secondary_boundary_equivalent_inertia
        )

    @property
    def movable_secondary_rotational_inertia(self) -> float:
        return self.inertias.secondary.movable_sheave_rotational_inertia

    @property
    def secondary_absolute_rotational_inertia(self) -> float:
        return (
            self.secondary_fixed_rotational_inertia
            + self.movable_secondary_rotational_inertia
        )

    @property
    def primary_external_torque(self) -> float:
        return self.shaft_boundaries.primary.external_torque

    @property
    def secondary_external_torque(self) -> float:
        return self.shaft_boundaries.secondary.external_torque


@dataclass(frozen=True, slots=True, init=False)
class MechanicalCVTPlant:
    """Five-state mechanical CVT plant.

    The plant has no engine or vehicle fields. Every evaluation receives
    primary/secondary shaft-port values from a host simulation.
    """

    geometry: BeltPulleyGeometry
    primary_actuator: PulleyActuator
    secondary_actuator: PulleyActuator
    primary_helical_coupling: HelicalPulleyCoupling | None
    secondary_helical_coupling: HelicalPulleyCoupling | None
    inertias: ResolvedInertias
    contact: BeltContactSpec

    def __init__(self) -> None:
        raise TypeError("Use MechanicalCVTPlant.from_assembly().")

    def __post_init__(self) -> None:
        positions = _operating_geometry_positions(self.geometry)
        for name, coupling in (
            ("primary", self.primary_helical_coupling),
            ("secondary", self.secondary_helical_coupling),
        ):
            if coupling is not None:
                _validate_helix_domain(
                    name=name, helix_coupling=coupling, positions=positions
                )
        _validate_ramp_domain(
            name="primary", actuator=self.primary_actuator, positions=positions
        )
        _validate_ramp_domain(
            name="secondary", actuator=self.secondary_actuator, positions=positions
        )
        _validate_compression_spring_domains(
            primary_actuator=self.primary_actuator,
            secondary_actuator=self.secondary_actuator,
            positions=positions,
        )

    @classmethod
    def from_assembly(cls, assembly: CVTAssemblySpec) -> "MechanicalCVTPlant":
        if not isinstance(assembly, CVTAssemblySpec):
            raise TypeError("assembly must be a CVTAssemblySpec.")
        instance = object.__new__(cls)
        object.__setattr__(instance, "geometry", assembly.geometry)
        object.__setattr__(
            instance, "primary_actuator", assembly.pulleys.primary.actuator
        )
        object.__setattr__(
            instance, "secondary_actuator", assembly.pulleys.secondary.actuator
        )
        object.__setattr__(
            instance,
            "primary_helical_coupling",
            assembly.pulleys.primary.helical_coupling,
        )
        object.__setattr__(
            instance,
            "secondary_helical_coupling",
            assembly.pulleys.secondary.helical_coupling,
        )
        object.__setattr__(instance, "inertias", assembly.inertias)
        object.__setattr__(instance, "contact", assembly.contact)
        instance.__post_init__()
        return instance

    @property
    def traction_law(self):
        """Internal CVT contact law derived from the assembly contact spec."""

        return self.contact.traction_law()

    def primary_actuation_context(
        self, *, time: float, state: CVTState, geometry: GeometryPosition
    ) -> PulleyActuationContext:
        return self._actuation_context(
            time=time,
            side="primary",
            state=state,
            coordinate=geometry.primary_axial_coordinate,
            coupling=self.primary_helical_coupling,
            shaft_speed=state.primary_angular_speed,
            channels=PulleyClosureChannels.primary(),
            movable_member_rotational_inertia=self.inertias.primary.movable_sheave_rotational_inertia,
        )

    def secondary_actuation_context(
        self, *, time: float, state: CVTState, geometry: GeometryPosition
    ) -> PulleyActuationContext:
        return self._actuation_context(
            time=time,
            side="secondary",
            state=state,
            coordinate=geometry.secondary_axial_coordinate,
            coupling=self.secondary_helical_coupling,
            shaft_speed=state.secondary_angular_speed,
            channels=PulleyClosureChannels.secondary(),
            movable_member_rotational_inertia=self.inertias.secondary.movable_sheave_rotational_inertia,
        )

    def _actuation_context(
        self,
        *,
        time: float,
        side: str,
        state: CVTState,
        coordinate: Any,
        coupling: HelicalPulleyCoupling | None,
        shaft_speed: float,
        channels: PulleyClosureChannels,
        movable_member_rotational_inertia: float,
    ) -> PulleyActuationContext:
        del side
        helical_state = None
        if coupling is not None:
            helical_state = HelicalCouplingState(
                kinematics=coupling.evaluate_from_local_coordinate(
                    axial_position=coordinate.value,
                    d_axial_position_ds=coordinate.d_value_ds,
                    d2_axial_position_ds2=coordinate.d2_value_ds2,
                ),
                opening_per_axial_position=coupling.opening_per_axial_position,
                opening_offset=coupling.opening_offset,
            )
        return PulleyActuationContext(
            time=time,
            axial_position=coordinate.value,
            axial_speed=coordinate.d_value_ds * state.shift_speed,
            shaft_speed=shaft_speed,
            shift_speed=state.shift_speed,
            closure_channels=channels,
            helical_coupling=helical_state,
            movable_member_rotational_inertia=movable_member_rotational_inertia,
        )

    def snapshot(
        self,
        *,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        geometry_side: str = "auto",
    ) -> DynamicsSnapshot:
        """Build a frozen snapshot at the explicit static time origin ``t = 0``."""

        return self.snapshot_at_time(
            time=0.0,
            state=state,
            shaft_boundaries=shaft_boundaries,
            geometry_side=geometry_side,
        )

    def snapshot_at_time(
        self,
        *,
        time: float,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        geometry_side: str = "auto",
    ) -> DynamicsSnapshot:
        if not isfinite(time):
            raise ValueError("time must be finite.")
        if shaft_boundaries is None:
            shaft_boundaries = CVTShaftBoundaryValues.zero()
        if not isinstance(shaft_boundaries, CVTShaftBoundaryValues):
            raise TypeError("shaft_boundaries must be a CVTShaftBoundaryValues.")

        if geometry_side == "auto":
            geometry = self.geometry.evaluate(state.shift_position)
        elif geometry_side == "deadzone":
            geometry = self.geometry.evaluate_deadzone(state.shift_position)
        elif geometry_side == "engaged":
            geometry = self.geometry.evaluate_engaged(state.shift_position)
        else:
            raise ValueError(
                "geometry_side must be one of {'auto', 'deadzone', 'engaged'}."
            )
        primary_context = self.primary_actuation_context(
            time=time, state=state, geometry=geometry
        )
        secondary_context = self.secondary_actuation_context(
            time=time, state=state, geometry=geometry
        )

        primary_mechanism = self.primary_actuator.evaluate_element(primary_context)
        secondary_mechanism = self.secondary_actuator.evaluate_element(
            secondary_context
        )
        primary_element = primary_mechanism
        secondary_element = secondary_mechanism

        axial_inertias = self.inertias.axial_translation.evaluate(
            primary_axial_coordinate=geometry.primary_axial_coordinate,
            secondary_axial_coordinate=geometry.secondary_axial_coordinate,
            belt_axial_coordinate=geometry.belt_axial_coordinate,
        )

        primary_element = primary_element + PulleyElementContribution(
            closing_force=_axial_inertial_reaction(
                axial_inertia=axial_inertias.primary,
                shift_speed=state.shift_speed,
            ),
            shaft_torque=_rigid_shaft_inertial_torque(
                unknown=ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION,
                inertia=self._primary_rigid_inertia(shaft_boundaries=shaft_boundaries),
            ),
        )

        secondary_rigid_inertia = (
            self.inertias.secondary.fixed_side.total
            + shaft_boundaries.secondary.equivalent_inertia
        )
        if self.secondary_helical_coupling is None:
            secondary_rigid_inertia += (
                self.inertias.secondary.movable_sheave_rotational_inertia
            )
        secondary_element = secondary_element + PulleyElementContribution(
            closing_force=_axial_inertial_reaction(
                axial_inertia=axial_inertias.secondary,
                shift_speed=state.shift_speed,
            ),
            shaft_torque=_rigid_shaft_inertial_torque(
                unknown=ClosureUnknown.SECONDARY_ANGULAR_ACCELERATION,
                inertia=secondary_rigid_inertia,
            ),
        )

        primary_helix = (
            primary_context.helical_coupling.kinematics
            if primary_context.helical_coupling
            else None
        )
        secondary_helix = (
            secondary_context.helical_coupling.kinematics
            if secondary_context.helical_coupling
            else None
        )

        snapshot = DynamicsSnapshot(
            state=state,
            geometry=geometry,
            axial_translation_inertias=axial_inertias,
            primary_pulley=primary_element,
            secondary_pulley=secondary_element,
            primary_actuation=primary_mechanism.closing_force,
            secondary_actuation=secondary_mechanism.closing_force,
            primary_helix=primary_helix,
            secondary_helix=secondary_helix,
            shaft_boundaries=shaft_boundaries,
            inertias=self.inertias,
            sheave_half_angle=self.geometry.spec.sheave_half_angle,
        )
        _validate_snapshot(snapshot)
        return snapshot

    def _primary_rigid_inertia(
        self, *, shaft_boundaries: CVTShaftBoundaryValues
    ) -> float:
        inertia = (
            self.inertias.primary.fixed_rotating_hardware_inertia
            + shaft_boundaries.primary.equivalent_inertia
        )
        if self.primary_helical_coupling is None:
            inertia += self.inertias.primary.movable_sheave_rotational_inertia
        return inertia


def _axial_inertial_reaction(
    *, axial_inertia, shift_speed: float
) -> AffineClosureScalar:
    return AffineClosureScalar(
        bias=-axial_inertia.local_known_inertial_force(shift_speed=shift_speed),
        gains=ClosureGains(
            shift_acceleration=-axial_inertia.local_shift_acceleration_gain
        ),
    )


def _rigid_shaft_inertial_torque(
    *, unknown: ClosureUnknown, inertia: float
) -> AffineClosureScalar:
    return AffineClosureScalar(gains=ClosureGains.from_by_unknown({unknown: -inertia}))


def _operating_geometry_positions(
    geometry: BeltPulleyGeometry,
) -> tuple[GeometryPosition, ...]:
    spec = geometry.spec
    shifts = tuple(sorted({0.0, spec.deadzone_shift, spec.max_shift}))
    return tuple(geometry.evaluate(shift) for shift in shifts)


def _validate_helix_domain(
    *,
    name: str,
    helix_coupling: HelicalPulleyCoupling,
    positions: tuple[GeometryPosition, ...],
) -> None:
    values = []
    for position in positions:
        coordinate = (
            position.primary_axial_coordinate
            if name == "primary"
            else position.secondary_axial_coordinate
        )
        values.append(
            helix_coupling.opening_offset
            + helix_coupling.opening_per_axial_position * coordinate.value
        )
    minimum_opening = min(values)
    maximum_opening = max(values)
    if (
        minimum_opening < helix_coupling.profile.opening_travel_min
        or maximum_opening > helix_coupling.profile.opening_travel_max
    ):
        raise ValueError(
            f"{name} helical_coupling does not cover the geometry-reachable opening-travel interval "
            f"[{minimum_opening}, {maximum_opening}]."
        )


def _validate_ramp_domain(
    *, name: str, actuator: PulleyActuator, positions: tuple[GeometryPosition, ...]
) -> None:
    axial_positions = tuple(
        (
            position.primary_axial_coordinate.value
            if name == "primary"
            else position.secondary_axial_coordinate.value
        )
        for position in positions
    )
    minimum_position = min(axial_positions)
    maximum_position = max(axial_positions)
    for force_law in actuator.force_laws:
        if not isinstance(force_law, CentrifugalRampForce):
            continue
        profile = force_law.spec.radial_displacement_profile
        if minimum_position < profile.x_min or maximum_position > profile.x_max:
            raise ValueError(
                f"{name} centrifugal-ramp profile does not cover the geometry-reachable "
                f"axial interval [{minimum_position}, {maximum_position}]."
            )
        for axial_position in axial_positions:
            flyweight_radius = (
                force_law.spec.radius_at_zero_position
                + profile.evaluate(axial_position).value
            )
            if flyweight_radius <= 0.0:
                raise ValueError(
                    f"{name} centrifugal-ramp profile gives a non-positive flyweight radius."
                )


def _validate_compression_spring_domains(
    *,
    primary_actuator: PulleyActuator,
    secondary_actuator: PulleyActuator,
    positions: tuple[GeometryPosition, ...],
) -> None:
    _validate_actuator_springs(
        name="primary",
        actuator=primary_actuator,
        axial_positions=tuple(
            position.primary_axial_coordinate.value for position in positions
        ),
    )
    _validate_actuator_springs(
        name="secondary",
        actuator=secondary_actuator,
        axial_positions=tuple(
            position.secondary_axial_coordinate.value for position in positions
        ),
    )


def _validate_actuator_springs(
    *, name: str, actuator: PulleyActuator, axial_positions: tuple[float, ...]
) -> None:
    for force_law in actuator.force_laws:
        if not isinstance(force_law, AxialSpringForce):
            continue
        spec = force_law.spec
        compressions = tuple(
            spec.initial_compression
            + spec.compression_per_axial_position * axial_position
            for axial_position in axial_positions
        )
        if min(compressions) < 0.0:
            raise ValueError(
                f"{name} compression spring reaches negative compression in the shift range."
            )


def _validate_snapshot(snapshot: DynamicsSnapshot) -> None:
    scalar_values = {
        "primary_external_torque": snapshot.primary_external_torque,
        "secondary_external_torque": snapshot.secondary_external_torque,
        "belt_transport_mass": snapshot.belt_transport_mass,
        "belt_linear_density": snapshot.belt_linear_density,
        "primary_rotational_inertia": snapshot.primary_rotational_inertia,
        "secondary_absolute_rotational_inertia": snapshot.secondary_absolute_rotational_inertia,
        "primary_axial_mass": snapshot.axial_translation_inertias.primary.mass,
        "secondary_axial_mass": snapshot.axial_translation_inertias.secondary.mass,
        "belt_axial_mass": snapshot.axial_translation_inertias.belt.mass,
        "sheave_half_angle": snapshot.sheave_half_angle,
    }
    if snapshot.secondary_helix is not None:
        scalar_values["secondary_dtheta_ds"] = snapshot.secondary_helix.dtheta_ds
        scalar_values["secondary_d2theta_ds2"] = snapshot.secondary_helix.d2theta_ds2
    if snapshot.primary_helix is not None:
        scalar_values["primary_dtheta_ds"] = snapshot.primary_helix.dtheta_ds
        scalar_values["primary_d2theta_ds2"] = snapshot.primary_helix.d2theta_ds2
    for name, value in scalar_values.items():
        if not isfinite(value):
            raise ValueError(f"Dynamics snapshot produced non-finite {name}.")
    if not 0.0 < snapshot.sheave_half_angle < 1.5707963267948966:
        raise ValueError(
            "Dynamics snapshot sheave_half_angle must lie strictly between zero and pi/2."
        )
