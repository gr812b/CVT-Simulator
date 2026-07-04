"""State-frozen inputs for repeated trial-lambda closure solves."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
from cinder.downstream import (
    LockedFinalDriveVehicle,
    SecondaryAttachment,
    SecondaryBoundary,
)
from cinder.inertia import AxialTranslationInertias, ResolvedInertias
from cinder.profiles import HelixProfile, HelixShiftKinematics
from cinder.vehicle import ConstantGradeRoadProfile, RoadLoadModel, RoadLoadResult, RoadProfile

from cinder.integration import CVTDynamicState


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

    primary_actuation: PulleyActuationResult
    secondary_actuation: PulleyActuationResult
    secondary_helix: HelixShiftKinematics

    engine_torque: float
    secondary_boundary: SecondaryBoundary

    inertias: ResolvedInertias
    sheave_half_angle: float

    @property
    def road_load(self) -> RoadLoadResult | None:
        """Return road data when the attachment is vehicle-backed.

        Direct secondary-shaft loads have no vehicle observables and return
        ``None`` here.  Vehicle-specific callers should use
        :attr:`vehicle_road_load` for an explicit checked access path.
        """

        return self.secondary_boundary.road_load

    @property
    def vehicle_road_load(self) -> RoadLoadResult:
        """Return vehicle road data or raise for a non-vehicle attachment.

        This keeps launch/reporting code explicit about the fact that vehicle
        observables belong to the locked vehicle attachment, not to every CVT
        simulation.
        """

        road_load = self.secondary_boundary.road_load
        if road_load is None:
            raise RuntimeError(
                "This secondary attachment does not provide vehicle road-load data."
            )
        return road_load

    @property
    def vehicle_distance(self) -> float:
        """Return attachment vehicle distance or raise for a direct shaft load."""

        distance = self.secondary_boundary.vehicle_distance
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
    def secondary_attachment_rotational_inertia(self) -> float:
        """Return state-frozen downstream inertia referred to the secondary."""

        return self.secondary_boundary.added_rotational_inertia

    @property
    def secondary_fixed_rotational_inertia(self) -> float:
        """Return core fixed-side plus downstream secondary inertia."""

        return (
            self.inertias.secondary.fixed_side.total
            + self.secondary_attachment_rotational_inertia
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

        return self.secondary_boundary.external_torque


@dataclass(frozen=True, slots=True)
class CVTDynamicsModel:
    """Fixed components needed to create a :class:`DynamicsSnapshot`.

    The preferred construction path passes a ``secondary_attachment``.  The
    attachment owns the downstream boundary condition and may be a locked
    final-drive vehicle, a dyno load, or another future driveline component.
    The CVT core then remains responsible only for primary, belt, secondary,
    shift, and contact mechanics.

    ``road_load`` and ``road_profile`` remain as a compatibility path for
    existing callers.  That path creates a locked vehicle attachment whose
    inertia contribution is disabled because the legacy inertia resolver has
    already reflected it into the CVT core.  New assembly should use
    ``secondary_attachment`` and resolve core inertias without vehicle terms.
    """

    geometry: BeltPulleyGeometry
    primary_actuator: PulleyActuator
    secondary_actuator: PulleyActuator
    secondary_helix_profile: HelixProfile

    inertias: ResolvedInertias
    engine: FullThrottleTorqueCurve
    road_load: RoadLoadModel | None = None
    road_profile: RoadProfile = ConstantGradeRoadProfile()
    secondary_attachment: SecondaryAttachment | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.road_profile, RoadProfile):
            raise TypeError("road_profile must implement RoadProfile.sample().")

        attachment = self.secondary_attachment
        if attachment is None:
            if self.road_load is None:
                raise ValueError(
                    "Provide secondary_attachment, or provide legacy road_load and road_profile."
                )
            attachment = LockedFinalDriveVehicle(
                road_load=self.road_load,
                road_profile=self.road_profile,
                include_reflected_vehicle_inertia=False,
            )
            object.__setattr__(self, "secondary_attachment", attachment)
        else:
            if self.road_load is not None:
                raise ValueError(
                    "Provide either secondary_attachment or legacy road_load/road_profile, not both."
                )
            if not callable(getattr(attachment, "evaluate", None)):
                raise TypeError(
                    "secondary_attachment must implement evaluate(state=...) -> SecondaryBoundary."
                )

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
            central_inertia=(self.inertias.secondary.movable_sheave_rotational_inertia),
        )

    @property
    def locked_vehicle_attachment(self) -> LockedFinalDriveVehicle:
        """Return the locked vehicle attachment or raise for a direct shaft load."""

        attachment = self.secondary_attachment
        if not isinstance(attachment, LockedFinalDriveVehicle):
            raise RuntimeError(
                "This model is not attached to a LockedFinalDriveVehicle."
            )
        return attachment

    def with_road_profile(self, road_profile: RoadProfile) -> "CVTDynamicsModel":
        """Return a locked-vehicle model with a replacement road profile.

        This is the narrow replacement for ``dataclasses.replace(model,
        road_profile=...)`` in launch tools.  It deliberately fails for a
        direct secondary load, where a road profile has no physical meaning.
        """

        if not isinstance(road_profile, RoadProfile):
            raise TypeError("road_profile must implement RoadProfile.sample().")
        attachment = self.locked_vehicle_attachment.with_road_profile(road_profile)
        return replace(
            self,
            road_load=None,
            road_profile=road_profile,
            secondary_attachment=attachment,
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
                axial_speed=(secondary_coordinate.d_value_ds * state.shift_speed),
                shaft_speed=state.secondary_angular_speed,
                global_shift_speed=state.shift_speed,
                helix_kinematics=secondary_helix,
                movable_sheave_rotational_inertia=(
                    self.inertias.secondary.movable_sheave_rotational_inertia
                ),
            )
        )

        attachment = self.secondary_attachment
        if attachment is None:  # pragma: no cover - __post_init__ invariant.
            raise RuntimeError("CVTDynamicsModel has no secondary attachment.")
        secondary_boundary = attachment.evaluate(state=state)
        if not isinstance(secondary_boundary, SecondaryBoundary):
            raise TypeError(
                "secondary_attachment.evaluate() must return SecondaryBoundary."
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
            engine_torque=self.engine.evaluate(state.primary_angular_speed),
            secondary_boundary=secondary_boundary,
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
        "secondary_attachment_rotational_inertia": (
            snapshot.secondary_attachment_rotational_inertia
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
