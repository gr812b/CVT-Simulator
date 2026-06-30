"""State-frozen inputs for repeated trial-lambda closure solves."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.actuation import (
    PulleyActuationResult,
    PulleyActuationState,
    PulleyActuator,
    SecondaryHelixActuationState,
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
    """
    All quantities fixed across repeated lambda trials at one ODE state.

    It intentionally contains no trial lambda pair, no matrix, and no
    intermediate road-profile data. A later trial-system object will use this
    snapshot to assemble only the lambda-dependent pieces of the six-row
    closure system.

    At fixed state, the following are evaluated exactly once:

    * pulley geometry and all shift derivatives;
    * literal shift-translation inertia;
    * primary and secondary affine actuator relations;
    * secondary helix shift kinematics;
    * engine torque;
    * local road-load torque.

    Vehicle distance and the sampled road profile are construction-time
    intermediates only. The six-by-six rows consume the resulting
    ``RoadLoadResult``, not the route query that produced it.
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
    """
    Fixed assembled components needed to create a ``DynamicsSnapshot``.

    This is the system-level dependency container. It owns no mutable
    simulation state and performs no lambda solve. The shared
    ``secondary_helix_profile`` remains explicit because later rotational-row
    assembly needs the same geometry independently of the actuator.

    ``road_profile`` is defined in physical vehicle distance. The snapshot
    converts the integrated secondary-shaft angle to that distance using the
    final drive owned by ``road_load`` before sampling it.
    """

    geometry: BeltPulleyGeometry
    primary_actuator: PulleyActuator
    secondary_actuator: PulleyActuator
    secondary_helix_profile: HelixProfile

    inertias: ResolvedInertias
    sheave_half_angle: float
    engine: FullThrottleTorqueCurve
    road_load: RoadLoadModel
    road_profile: RoadProfile = ConstantGradeRoadProfile()

    def __post_init__(self) -> None:
        # The closed secondary reference is x_s = 0, hence q = -x_s = 0.
        # Reject a model whose helix cannot represent that reference point.
        if not (
            self.secondary_helix_profile.opening_travel_min
            <= 0.0
            <= self.secondary_helix_profile.opening_travel_max
        ):
            raise ValueError(
                "secondary_helix_profile must include q=0 at the closed "
                "secondary reference."
            )

        if not isinstance(self.road_profile, RoadProfile):
            raise TypeError("road_profile must implement RoadProfile.sample().")

    def snapshot(
        self,
        *,
        state: CVTDynamicState,
    ) -> DynamicsSnapshot:
        """
        Evaluate every state-dependent, lambda-independent quantity once.

        A root solver should call this once per ODE RHS evaluation, then reuse
        the result for every trial ``(lambda_p, lambda_s)`` pair.
        """

        geometry = self.geometry.evaluate(state.shift_position)

        primary_coordinate = geometry.primary_axial_coordinate
        secondary_coordinate = geometry.secondary_axial_coordinate

        primary_actuation = self.primary_actuator.evaluate(
            PulleyActuationState(
                axial_position=primary_coordinate.value,
                axial_speed=(
                    primary_coordinate.d_value_ds * state.shift_speed
                ),
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
                local_axial_coordinate_slope=secondary_coordinate.d_value_ds,
                local_axial_coordinate_curvature=(
                    secondary_coordinate.d2_value_ds2
                ),
            )
        )

        secondary_helix = self.secondary_helix_profile.evaluate_shift_kinematics(
            opening_travel=-secondary_coordinate.value,
            d_opening_ds=-secondary_coordinate.d_value_ds,
            d2_opening_ds2=-secondary_coordinate.d2_value_ds2,
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


def _validate_snapshot(snapshot: DynamicsSnapshot) -> None:
    """Fail early if a component ever produces a non-finite snapshot value."""

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
