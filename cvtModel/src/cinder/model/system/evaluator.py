"""State-frozen inputs for repeated trial-lambda closure solves."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from cinder.model.cvt.actuation import (
    HelicalCouplingState,
    PulleyActuationContext,
    PulleyActuator,
    PulleyClosureChannels,
)
from cinder.model.cvt.closure import AffineClosureScalar
from cinder.model.cvt.actuation.forces import (
    AxialSpringForce,
    CentrifugalRampForce,
    HelicalTorqueReactionForce,
)
from cinder.model.boundaries.input import InputTorqueBoundary
from cinder.model.cvt.geometry import BeltPulleyGeometry, GeometryPosition
from cinder.model.boundaries.output import (
    OutputBoundary,
    OutputBoundaryEvaluation,
)
from cinder.model.cvt.inertia import AxialTranslationInertias, ResolvedInertias
from cinder.model.cvt.profiles import HelixShiftKinematics
from cinder.model.boundaries.output.vehicle import RoadLoadResult
from .assembly import HelicalPulleyCoupling

from cinder.execution.hybrid import CVTDynamicState


@dataclass(frozen=True, slots=True)
class DynamicsSnapshot:
    """All quantities fixed across repeated lambda trials at one ODE state.

    The snapshot intentionally contains no trial lambda pair or assembled
    matrix.  It includes the state-evaluated secondary boundary so the contact
    closure sees the same downstream torque and inertia during every lambda
    trial at this ODE point.
    """

    state: CVTDynamicState

    geometry: GeometryPosition
    axial_translation_inertias: AxialTranslationInertias

    primary_actuation: AffineClosureScalar
    secondary_actuation: AffineClosureScalar
    secondary_helix: HelixShiftKinematics

    engine_torque: float
    output_boundary_evaluation: OutputBoundaryEvaluation

    inertias: ResolvedInertias
    sheave_half_angle: float

    @property
    def road_load(self) -> RoadLoadResult | None:
        """Return road data when the attachment is vehicle-backed.

        Direct secondary-shaft loads have no vehicle observables and return
        ``None`` here.  Vehicle-specific callers should use
        :attr:`vehicle_road_load` for an explicit checked access path.
        """

        return self.output_boundary_evaluation.road_load

    @property
    def vehicle_road_load(self) -> RoadLoadResult:
        """Return vehicle road data or raise for a non-vehicle attachment.

        This keeps launch/reporting code explicit about the fact that vehicle
        observables belong to the locked vehicle attachment, not to every CVT
        simulation.
        """

        road_load = self.output_boundary_evaluation.road_load
        if road_load is None:
            raise RuntimeError(
                "This secondary attachment does not provide vehicle road-load data."
            )
        return road_load

    @property
    def vehicle_distance(self) -> float:
        """Return attachment vehicle distance or raise for a direct shaft load."""

        distance = self.output_boundary_evaluation.vehicle_distance
        if distance is None:
            raise RuntimeError(
                "This secondary attachment does not provide vehicle distance."
            )
        return distance

    @property
    def belt_transport_mass(self) -> float:
        """Return the belt mass multiplying belt-speed acceleration."""

        return self.inertias.belt.mass

    @property
    def belt_linear_density(self) -> float:
        """Return rho_b A_b used by the wrap equations."""

        return self.inertias.belt.density * self.inertias.belt.cross_sectional_area

    @property
    def primary_rotational_inertia(self) -> float:
        """Return I_p."""

        return self.inertias.primary.rotational_inertia

    @property
    def output_boundary_added_rotational_inertia(self) -> float:
        """Return state-frozen downstream inertia referred to the secondary."""

        return self.output_boundary_evaluation.added_rotational_inertia

    @property
    def secondary_fixed_rotational_inertia(self) -> float:
        """Return core fixed-side plus downstream secondary inertia."""

        return (
            self.inertias.secondary.fixed_side.total
            + self.output_boundary_added_rotational_inertia
        )

    @property
    def movable_secondary_rotational_inertia(self) -> float:
        """Return I_M."""

        return self.inertias.secondary.movable_sheave_rotational_inertia

    @property
    def secondary_absolute_rotational_inertia(self) -> float:
        """Return total absolute secondary inertia at this RHS evaluation."""

        return (
            self.secondary_fixed_rotational_inertia
            + self.movable_secondary_rotational_inertia
        )

    @property
    def secondary_external_torque(self) -> float:
        """Return signed external torque applied at the secondary."""

        return self.output_boundary_evaluation.external_torque


@dataclass(frozen=True, slots=True, init=False)
class CVTDynamicsModel:
    """Runtime evaluator assembled exclusively from a :class:`CVTSimulationCase`.

    The evaluator owns no independent engine, vehicle, or road constructor
    pathway. Input and output shaft behavior is supplied by the case's
    boundaries, while CVT geometry, actuation, inertia, and contact mechanics
    remain in the assembly.
    """

    geometry: BeltPulleyGeometry
    primary_actuator: PulleyActuator
    secondary_actuator: PulleyActuator
    output_helical_coupling: HelicalPulleyCoupling
    inertias: ResolvedInertias
    input_boundary: InputTorqueBoundary
    output_boundary: OutputBoundary

    def __init__(self) -> None:
        raise TypeError(
            "CVTDynamicsModel is runtime-only; construct it with "
            "CVTDynamicsModel.from_case(case)."
        )

    def __post_init__(self) -> None:
        if not callable(getattr(self.input_boundary, "evaluate", None)):
            raise TypeError("input_boundary must implement evaluate(angular_speed).")
        if not callable(getattr(self.output_boundary, "evaluate", None)):
            raise TypeError("output_boundary must implement evaluate(state=...).")

        operating_positions = _operating_geometry_positions(self.geometry)
        _validate_secondary_helix_domain(
            helix_coupling=self.output_helical_coupling,
            positions=operating_positions,
        )
        _validate_primary_ramp_domain(
            actuator=self.primary_actuator,
            positions=operating_positions,
        )
        _validate_compression_spring_domains(
            primary_actuator=self.primary_actuator,
            secondary_actuator=self.secondary_actuator,
            positions=operating_positions,
        )

    @classmethod
    def from_case(cls, case: "CVTSimulationCase") -> "CVTDynamicsModel":
        """Build the evaluator through CINDER's sole editable case contract."""

        from .case import CVTSimulationCase

        if not isinstance(case, CVTSimulationCase):
            raise TypeError("case must be a CVTSimulationCase.")
        instance = object.__new__(cls)
        object.__setattr__(instance, "geometry", case.cvt.geometry)
        object.__setattr__(instance, "primary_actuator", case.cvt.pulleys.input.actuator)
        object.__setattr__(instance, "secondary_actuator", case.cvt.pulleys.output.actuator)
        object.__setattr__(
            instance,
            "output_helical_coupling",
            _require_output_helical_coupling(case),
        )
        object.__setattr__(instance, "inertias", case.cvt.inertias)
        object.__setattr__(instance, "input_boundary", case.input_boundary)
        object.__setattr__(instance, "output_boundary", case.output_boundary)
        instance.__post_init__()
        return instance

    def primary_actuation_context(
        self,
        *,
        state: CVTDynamicState,
        geometry: GeometryPosition,
    ) -> PulleyActuationContext:
        """Build the generic input-pulley actuator context at one state."""

        coordinate = geometry.primary_axial_coordinate
        return PulleyActuationContext(
            axial_position=coordinate.value,
            axial_speed=coordinate.d_value_ds * state.shift_speed,
            shaft_speed=state.primary_angular_speed,
            closure_channels=PulleyClosureChannels.input_pulley(),
        )

    def output_actuation_context(
        self,
        *,
        state: CVTDynamicState,
        geometry: GeometryPosition,
        helical_kinematics: HelixShiftKinematics,
    ) -> PulleyActuationContext:
        """Build the generic output-pulley actuator context at one state."""

        coordinate = geometry.secondary_axial_coordinate
        return PulleyActuationContext(
            axial_position=coordinate.value,
            axial_speed=coordinate.d_value_ds * state.shift_speed,
            shaft_speed=state.secondary_angular_speed,
            shift_speed=state.shift_speed,
            closure_channels=PulleyClosureChannels.output_pulley(),
            helical_coupling=HelicalCouplingState(
                kinematics=helical_kinematics,
                opening_per_axial_position=(
                    self.output_helical_coupling.opening_per_axial_position
                ),
                opening_offset=self.output_helical_coupling.opening_offset,
            ),
            movable_member_rotational_inertia=(
                self.inertias.secondary.movable_sheave_rotational_inertia
            ),
        )

    def snapshot(
        self,
        *,
        state: CVTDynamicState,
    ) -> DynamicsSnapshot:
        """Evaluate every state-dependent, lambda-independent quantity once."""

        geometry = self.geometry.evaluate(state.shift_position)

        primary_coordinate = geometry.primary_axial_coordinate
        secondary_coordinate = geometry.secondary_axial_coordinate

        secondary_helix = self.output_helical_coupling.evaluate_from_local_coordinate(
            axial_position=secondary_coordinate.value,
            d_axial_position_ds=secondary_coordinate.d_value_ds,
            d2_axial_position_ds2=secondary_coordinate.d2_value_ds2,
        )

        primary_actuation = self.primary_actuator.evaluate_relation(
            self.primary_actuation_context(state=state, geometry=geometry)
        )

        secondary_actuation = self.secondary_actuator.evaluate_relation(
            self.output_actuation_context(
                state=state,
                geometry=geometry,
                helical_kinematics=secondary_helix,
            )
        )

        attachment = self.output_boundary
        if attachment is None:  # pragma: no cover - __post_init__ invariant.
            raise RuntimeError("CVTDynamicsModel has no secondary attachment.")
        output_boundary_evaluation = attachment.evaluate(state=state)
        if not isinstance(output_boundary_evaluation, OutputBoundaryEvaluation):
            raise TypeError(
                "output_boundary.evaluate() must return OutputBoundaryEvaluation."
            )

        snapshot = DynamicsSnapshot(
            state=state,
            geometry=geometry,
            axial_translation_inertias=self.inertias.axial_translation.evaluate(
                primary_axial_coordinate=primary_coordinate,
                secondary_axial_coordinate=secondary_coordinate,
                belt_axial_coordinate=geometry.belt_axial_coordinate,
            ),
            primary_actuation=primary_actuation,
            secondary_actuation=secondary_actuation,
            secondary_helix=secondary_helix,
            engine_torque=self.input_boundary.evaluate(state.primary_angular_speed),
            output_boundary_evaluation=output_boundary_evaluation,
            inertias=self.inertias,
            sheave_half_angle=self.geometry.spec.sheave_half_angle,
        )

        _validate_snapshot(snapshot)
        return snapshot


def _require_output_helical_coupling(case: "CVTSimulationCase") -> HelicalPulleyCoupling:
    coupling = case.cvt.pulleys.output.helical_coupling
    if coupling is None:  # pragma: no cover - CVTAssemblySpec invariant.
        raise ValueError("Current shift dynamics require output helical coupling.")
    return coupling


def _operating_geometry_positions(
    geometry: BeltPulleyGeometry,
) -> tuple[GeometryPosition, ...]:
    """Evaluate the reachable shift endpoints plus the deadzone boundary."""

    spec = geometry.spec
    shifts = tuple(sorted({0.0, spec.deadzone_shift, spec.max_shift}))
    return tuple(geometry.evaluate(shift) for shift in shifts)


def _validate_secondary_helix_domain(
    *,
    helix_coupling: HelicalPulleyCoupling,
    positions: tuple[GeometryPosition, ...],
) -> None:
    """Ensure host output geometry remains inside the installed helix profile."""

    opening_travels = tuple(
        helix_coupling.opening_offset
        + helix_coupling.opening_per_axial_position
        * position.secondary_axial_coordinate.value
        for position in positions
    )
    minimum_opening = min(opening_travels)
    maximum_opening = max(opening_travels)

    if (
        minimum_opening < helix_coupling.profile.opening_travel_min
        or maximum_opening > helix_coupling.profile.opening_travel_max
    ):
        raise ValueError(
            "output helical_coupling does not cover the geometry-reachable "
            f"opening-travel interval [{minimum_opening}, {maximum_opening}]."
        )

def _validate_primary_ramp_domain(
    *,
    actuator: PulleyActuator,
    positions: tuple[GeometryPosition, ...],
) -> None:
    """Ensure any centrifugal primary-ramp profile covers the shift interval."""

    primary_positions = tuple(
        position.primary_axial_coordinate.value for position in positions
    )
    minimum_position = min(primary_positions)
    maximum_position = max(primary_positions)

    for force_law in actuator.force_laws:
        if not isinstance(force_law, CentrifugalRampForce):
            continue

        profile = force_law.spec.radial_displacement_profile
        if minimum_position < profile.x_min or maximum_position > profile.x_max:
            raise ValueError(
                "primary centrifugal-ramp profile does not cover the "
                f"geometry-reachable axial interval "
                f"[{minimum_position}, {maximum_position}]."
            )

        for axial_position in primary_positions:
            flyweight_radius = (
                force_law.spec.radius_at_zero_position
                + profile.evaluate(axial_position).value
            )
            if flyweight_radius <= 0.0:
                raise ValueError(
                    "primary centrifugal-ramp profile gives a non-positive "
                    "flyweight radius in the reachable shift range."
                )


def _validate_compression_spring_domains(
    *,
    primary_actuator: PulleyActuator,
    secondary_actuator: PulleyActuator,
    positions: tuple[GeometryPosition, ...],
) -> None:
    """Reject a compression spring that would be evaluated in tension."""

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
    *,
    name: str,
    actuator: PulleyActuator,
    axial_positions: tuple[float, ...],
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
        minimum_compression = min(compressions)

        if minimum_compression < 0.0:
            raise ValueError(
                f"{name} compression spring reaches negative compression "
                "within the geometry-reachable shift range."
            )



def _validate_snapshot(snapshot: DynamicsSnapshot) -> None:
    """Fail early if a component produces a non-finite snapshot value."""

    scalar_values = {
        "engine_torque": snapshot.engine_torque,
        "secondary_external_torque": snapshot.secondary_external_torque,
        "belt_transport_mass": snapshot.belt_transport_mass,
        "belt_linear_density": snapshot.belt_linear_density,
        "primary_rotational_inertia": snapshot.primary_rotational_inertia,
        "output_boundary_added_rotational_inertia": (
            snapshot.output_boundary_added_rotational_inertia
        ),
        "secondary_fixed_rotational_inertia": (
            snapshot.secondary_fixed_rotational_inertia
        ),
        "movable_secondary_rotational_inertia": (
            snapshot.movable_secondary_rotational_inertia
        ),
        "secondary_absolute_rotational_inertia": (
            snapshot.secondary_absolute_rotational_inertia
        ),
        "primary_axial_mass": snapshot.axial_translation_inertias.primary.mass,
        "secondary_axial_mass": snapshot.axial_translation_inertias.secondary.mass,
        "belt_axial_mass": snapshot.axial_translation_inertias.belt.mass,
        "primary_axial_reflected_mass": (
            snapshot.axial_translation_inertias.primary.reflected_mass
        ),
        "secondary_axial_reflected_mass": (
            snapshot.axial_translation_inertias.secondary.reflected_mass
        ),
        "belt_axial_reflected_mass": (
            snapshot.axial_translation_inertias.belt.reflected_mass
        ),
        "axial_generalized_mass": (
            snapshot.axial_translation_inertias.generalized_mass
        ),
        "axial_generalized_curvature_coefficient": (
            snapshot.axial_translation_inertias.generalized_curvature_coefficient
        ),
        "dtheta_ds": snapshot.secondary_helix.dtheta_ds,
        "d2theta_ds2": snapshot.secondary_helix.d2theta_ds2,
        "sheave_half_angle": snapshot.sheave_half_angle,
    }

    for name, value in scalar_values.items():
        if not isfinite(value):
            raise ValueError(f"Dynamics snapshot produced non-finite {name}.")

    if not 0.0 < snapshot.sheave_half_angle < 1.5707963267948966:
        raise ValueError(
            "Dynamics snapshot sheave_half_angle must lie strictly between "
            "zero and pi/2."
        )
