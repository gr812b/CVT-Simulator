"""State-frozen inputs for repeated trial-lambda closure solves."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from cinder.actuation import (
    PulleyActuationResult,
    PulleyActuationState,
    PulleyActuator,
    SecondaryHelixActuationState,
)
from cinder.actuation.forces import (
    AxialSpringForce,
    CentrifugalRampForce,
    SecondaryHelixForce,
)
from cinder.engine import FullThrottleTorqueCurve
from cinder.geometry import BeltPulleyGeometry, GeometryPosition
from cinder.inertia import ResolvedInertias, ShiftTranslationInertia
from cinder.profiles import HelixProfile, HelixShiftKinematics
from cinder.vehicle import (
    ConstantGradeRoadProfile,
    RoadLoadModel,
    RoadLoadResult,
    RoadProfile,
)

from .state import CVTDynamicState


@dataclass(frozen=True, slots=True)
class DynamicsSnapshot:
    """All quantities fixed across repeated lambda trials at one ODE state.

    The snapshot intentionally contains no trial lambda pair, no assembled
    matrix, and no intermediate road-profile sample. It captures only the
    state-dependent quantities that rows may reuse across a full outer lambda
    iteration.
    """

    state: CVTDynamicState

    geometry: GeometryPosition
    shift_translation_inertia: ShiftTranslationInertia

    primary_actuation: PulleyActuationResult
    secondary_actuation: PulleyActuationResult
    secondary_helix: HelixShiftKinematics

    engine_torque: float
    road_load: RoadLoadResult

    inertias: ResolvedInertias
    sheave_half_angle: float

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
    def secondary_fixed_rotational_inertia(self) -> float:
        """Return I_s,F."""

        return self.inertias.secondary.fixed_side.total

    @property
    def movable_secondary_rotational_inertia(self) -> float:
        """Return I_M."""

        return self.inertias.secondary.movable_sheave_rotational_inertia

    @property
    def secondary_absolute_rotational_inertia(self) -> float:
        """Return I_s,F + I_M."""

        return self.inertias.secondary.absolute_rotation_inertia

    @property
    def secondary_external_torque(self) -> float:
        """Return the known signed road torque applied at the secondary."""

        return self.road_load.secondary_external_torque


@dataclass(frozen=True, slots=True)
class CVTDynamicsModel:
    """Fixed components needed to create a :class:`DynamicsSnapshot`.

    ``secondary_helix_profile`` is evaluated exactly once per snapshot. The
    resulting :class:`HelixShiftKinematics` is passed into the secondary
    actuator and retained in the snapshot for the secondary rotational row.

    The road profile is defined in physical vehicle distance. Snapshot
    construction maps the integrated secondary-shaft angle to that distance
    through the final drive before evaluating the local road load.

    Construction validates intersections between component domains and the
    geometry's reachable shift range. This catches profile-range, spring-
    compression, and shared-inertia mismatches before the ODE is evaluated.
    """

    geometry: BeltPulleyGeometry
    primary_actuator: PulleyActuator
    secondary_actuator: PulleyActuator
    secondary_helix_profile: HelixProfile

    inertias: ResolvedInertias
    engine: FullThrottleTorqueCurve
    road_load: RoadLoadModel
    road_profile: RoadProfile = ConstantGradeRoadProfile()

    def __post_init__(self) -> None:
        if not isinstance(self.road_profile, RoadProfile):
            raise TypeError("road_profile must implement RoadProfile.sample().")

        operating_positions = _operating_geometry_positions(self.geometry)
        _validate_secondary_helix_domain(
            helix_profile=self.secondary_helix_profile,
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
        _validate_shared_movable_sheave_inertia(
            secondary_actuator=self.secondary_actuator,
            central_inertia=(
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

        # Evaluate shared helix geometry before secondary actuation. The force
        # law and the secondary rotational row use this same immutable object.
        secondary_helix = self.secondary_helix_profile.evaluate_shift_kinematics(
            opening_travel=-secondary_coordinate.value,
            d_opening_ds=-secondary_coordinate.d_value_ds,
            d2_opening_ds2=-secondary_coordinate.d2_value_ds2,
        )

        primary_actuation = self.primary_actuator.evaluate(
            PulleyActuationState(
                axial_position=primary_coordinate.value,
                axial_speed=primary_coordinate.d_value_ds * state.shift_speed,
                shaft_speed=state.primary_angular_speed,
            )
        )

        secondary_actuation = self.secondary_actuator.evaluate(
            SecondaryHelixActuationState(
                axial_position=secondary_coordinate.value,
                axial_speed=(
                    secondary_coordinate.d_value_ds * state.shift_speed
                ),
                shaft_speed=state.secondary_angular_speed,
                global_shift_speed=state.shift_speed,
                helix_kinematics=secondary_helix,
                movable_sheave_rotational_inertia=(
                    self.inertias.secondary.movable_sheave_rotational_inertia
                ),
            )
        )

        vehicle_distance = (
            self.road_load.final_drive.vehicle_distance_from_secondary_angle(
                secondary_shaft_angle=state.secondary_shaft_angle,
            )
        )
        grade_angle = self.road_profile.sample(
            vehicle_distance=vehicle_distance,
        ).grade_angle
        road_load = self.road_load.evaluate(
            secondary_angular_speed=state.secondary_angular_speed,
            grade_angle=grade_angle,
        )

        snapshot = DynamicsSnapshot(
            state=state,
            geometry=geometry,
            shift_translation_inertia=self.inertias.shift.evaluate(
                primary_axial_coordinate=primary_coordinate,
                secondary_axial_coordinate=secondary_coordinate,
                belt_axial_coordinate=geometry.belt_axial_coordinate,
            ),
            primary_actuation=primary_actuation,
            secondary_actuation=secondary_actuation,
            secondary_helix=secondary_helix,
            engine_torque=self.engine.evaluate(state.primary_angular_speed),
            road_load=road_load,
            inertias=self.inertias,
            sheave_half_angle=self.geometry.spec.sheave_half_angle,
        )

        _validate_snapshot(snapshot)
        return snapshot


def _operating_geometry_positions(
    geometry: BeltPulleyGeometry,
) -> tuple[GeometryPosition, ...]:
    """Evaluate the reachable shift endpoints plus the deadzone boundary."""

    spec = geometry.spec
    shifts = tuple(sorted({0.0, spec.deadzone_shift, spec.max_shift}))
    return tuple(geometry.evaluate(shift) for shift in shifts)


def _validate_secondary_helix_domain(
    *,
    helix_profile: HelixProfile,
    positions: tuple[GeometryPosition, ...],
) -> None:
    """Ensure the reachable secondary opening travel lies on the helix profile."""

    opening_travels = tuple(
        -position.secondary_axial_coordinate.value for position in positions
    )
    minimum_opening = min(opening_travels)
    maximum_opening = max(opening_travels)

    if (
        minimum_opening < helix_profile.opening_travel_min
        or maximum_opening > helix_profile.opening_travel_max
    ):
        raise ValueError(
            "secondary_helix_profile does not cover the geometry-reachable "
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


def _validate_shared_movable_sheave_inertia(
    *,
    secondary_actuator: PulleyActuator,
    central_inertia: float,
) -> None:
    """Reject legacy helix-spec inertia values that disagree with central I_M."""

    for force_law in secondary_actuator.force_laws:
        if not isinstance(force_law, SecondaryHelixForce):
            continue

        configured_inertia = force_law.spec.movable_sheave_rotational_inertia
        if configured_inertia is None:
            continue

        if not isclose(
            configured_inertia,
            central_inertia,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "SecondaryHelixForceSpec movable_sheave_rotational_inertia "
                "must match the central SecondaryInertia value."
            )


def _validate_snapshot(snapshot: DynamicsSnapshot) -> None:
    """Fail early if a component produces a non-finite snapshot value."""

    scalar_values = {
        "engine_torque": snapshot.engine_torque,
        "secondary_external_torque": snapshot.secondary_external_torque,
        "belt_transport_mass": snapshot.belt_transport_mass,
        "belt_linear_density": snapshot.belt_linear_density,
        "primary_rotational_inertia": snapshot.primary_rotational_inertia,
        "secondary_fixed_rotational_inertia": (
            snapshot.secondary_fixed_rotational_inertia
        ),
        "movable_secondary_rotational_inertia": (
            snapshot.movable_secondary_rotational_inertia
        ),
        "secondary_absolute_rotational_inertia": (
            snapshot.secondary_absolute_rotational_inertia
        ),
        "shift_translation_mass": snapshot.shift_translation_inertia.mass,
        "shift_translation_curvature_coefficient": (
            snapshot.shift_translation_inertia.coordinate_curvature_coefficient
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
