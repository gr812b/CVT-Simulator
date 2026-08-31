"""Reduced free-motion RHS for the primary-disengaged CVT deadzone."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isclose

import numpy as np

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureGains,
    ClosureUnknown,
    ClosureUnknowns,
)
from cinder.model.system.evaluator import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues
from cinder.model.system.state import CVTState, CVTStateDerivative

from .result import DeadzoneEvaluation
from .snapshot import DeadzoneSnapshot, build_deadzone_snapshot


@dataclass(slots=True)
class DeadzoneDynamicsEvaluator:
    """Evaluate neutral/free and neutral/lower-stop CVT mechanics."""

    model: MechanicalCVTPlant
    belt_secondary_lock_absolute_tolerance: float = 1.0e-9
    belt_secondary_lock_relative_tolerance: float = 1.0e-9

    def __post_init__(self) -> None:
        if not isinstance(self.model, MechanicalCVTPlant):
            raise TypeError("model must be a MechanicalCVTPlant instance.")
        if self.belt_secondary_lock_absolute_tolerance < 0.0:
            raise ValueError(
                "belt_secondary_lock_absolute_tolerance must be non-negative."
            )
        if self.belt_secondary_lock_relative_tolerance < 0.0:
            raise ValueError(
                "belt_secondary_lock_relative_tolerance must be non-negative."
            )

    def snapshot(
        self,
        *,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> DeadzoneSnapshot:
        """Build the deadzone snapshot at the explicit static time origin ``t = 0``."""

        return self.snapshot_at_time(
            time=0.0, state=state, shaft_boundaries=shaft_boundaries
        )

    def snapshot_at_time(
        self,
        *,
        time: float,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> DeadzoneSnapshot:
        snapshot = build_deadzone_snapshot(
            time=time,
            model=self.model,
            state=self._geometry_safe_state(state),
            shaft_boundaries=shaft_boundaries,
        )
        self._validate_belt_secondary_lock(snapshot=snapshot)
        return snapshot

    def _geometry_safe_state(self, state: CVTState) -> CVTState:
        spec = self.model.geometry.spec
        safe_shift = float(np.clip(state.shift_position, 0.0, spec.deadzone_shift))
        if safe_shift == state.shift_position:
            return state
        return replace(state, shift_position=safe_shift)

    def evaluate_free(
        self,
        *,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> DeadzoneEvaluation:
        """Evaluate free deadzone mechanics at the static time origin ``t = 0``."""

        return self.evaluate_free_at_time(
            time=0.0, state=state, shaft_boundaries=shaft_boundaries
        )

    def evaluate_free_at_time(
        self,
        *,
        time: float,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> DeadzoneEvaluation:
        """Return free deadzone dynamics.

        The primary is contact-free, so ``tau_p = N_p = lambda_p = 0``. Its
        installed mechanism may nevertheless couple shaft acceleration and
        axial acceleration. Those two equations are solved together:

            T_ext,p + T_mech,p - I_rigid alpha_p = 0,
            F_mech,p - F_inertia,p = 0.

        For a mechanism with no acceleration coupling this reduces exactly to
        the old direct divisions. The secondary/belt lock remains the same
        reduced fixed-geometry relation.
        """

        snapshot = self.snapshot_at_time(
            time=time, state=state, shaft_boundaries=shaft_boundaries
        )
        derivative = build_deadzone_free_derivative(snapshot=snapshot)
        self._require_mechanism_contacts(
            time=time,
            snapshot=snapshot,
            derivative=derivative,
        )
        return DeadzoneEvaluation(
            state=state,
            snapshot=snapshot,
            state_derivative=derivative,
        )

    def evaluate_lower_stop(
        self,
        *,
        state: CVTState,
        lower_stop_shift: float,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> DeadzoneEvaluation:
        """Evaluate the lower-stop constraint at static time origin ``t = 0``."""

        return self.evaluate_lower_stop_at_time(
            time=0.0,
            state=state,
            lower_stop_shift=lower_stop_shift,
            shaft_boundaries=shaft_boundaries,
        )

    def evaluate_lower_stop_at_time(
        self,
        *,
        time: float,
        state: CVTState,
        lower_stop_shift: float,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> DeadzoneEvaluation:
        from .lower_stop import evaluate_deadzone_lower_stop

        snapshot = self.snapshot_at_time(
            time=time, state=state, shaft_boundaries=shaft_boundaries
        )
        evaluation = evaluate_deadzone_lower_stop(
            snapshot=snapshot,
            lower_stop_shift=lower_stop_shift,
        )
        self._require_mechanism_contacts(
            time=time,
            snapshot=snapshot,
            derivative=evaluation.state_derivative,
        )
        return evaluation

    def _require_mechanism_contacts(
        self,
        *,
        time: float,
        snapshot: DeadzoneSnapshot,
        derivative: CVTStateDerivative,
    ) -> None:
        """Fail if a unilateral mounted mechanism would have to pull."""

        radius = snapshot.belt_secondary_lock_radius
        secondary_belt_torque = (
            -snapshot.inertias.belt.mass * radius * derivative.belt_acceleration
        )
        unknowns = ClosureUnknowns.from_components(
            primary_angular_acceleration=derivative.primary_angular_acceleration,
            secondary_angular_acceleration=derivative.secondary_angular_acceleration,
            belt_acceleration=derivative.belt_acceleration,
            shift_acceleration=derivative.shift_acceleration,
            primary_torque=0.0,
            secondary_torque=secondary_belt_torque,
        )
        primary_context = self.model.primary_actuation_context(
            time=time,
            state=snapshot.state,
            geometry=snapshot.primary_geometry,
        )
        secondary_context = self.model.secondary_actuation_context(
            time=time,
            state=snapshot.state,
            geometry=snapshot.locked_geometry,
        )
        margins = tuple(
            (f"primary/{key}", value)
            for key, value in self.model.primary_actuator.compressive_contact_margins(
                primary_context, unknowns
            )
        ) + tuple(
            (f"secondary/{key}", value)
            for key, value in self.model.secondary_actuator.compressive_contact_margins(
                secondary_context, unknowns
            )
        )
        failed = tuple((key, value) for key, value in margins if value < 0.0)
        if failed:
            detail = ", ".join(f"{key}={value:.9g}" for key, value in failed)
            raise RuntimeError(
                "Unilateral pulley-mechanism contact became inadmissible in "
                f"deadzone: {detail}. The missing contact topology is not modeled."
            )

    def _validate_belt_secondary_lock(self, *, snapshot: DeadzoneSnapshot) -> None:
        expected_speed = (
            snapshot.belt_secondary_lock_radius * snapshot.state.secondary_angular_speed
        )
        if not isclose(
            snapshot.state.belt_speed,
            expected_speed,
            rel_tol=self.belt_secondary_lock_relative_tolerance,
            abs_tol=self.belt_secondary_lock_absolute_tolerance,
        ):
            raise ValueError(
                "Deadzone requires the imposed belt-secondary lock v_b = r_s omega_s; "
                f"got residual {snapshot.belt_secondary_speed_residual:.6e} m/s."
            )


def _primary_deadzone_relations(
    snapshot: DeadzoneSnapshot,
) -> tuple[AffineClosureScalar, AffineClosureScalar]:
    """Return free primary rotational and axial residual relations."""

    rotation = (
        AffineClosureScalar(bias=snapshot.primary_external_torque)
        + snapshot.primary_mechanism.shaft_torque
        + AffineClosureScalar(
            gains=ClosureGains(
                primary_angular_acceleration=-snapshot.primary_rotational_inertia
            )
        )
    )

    inertia = snapshot.primary_axial_inertia
    axial_inertial_reaction = AffineClosureScalar(
        bias=-inertia.local_known_inertial_force(
            shift_speed=snapshot.state.shift_speed
        ),
        gains=ClosureGains(shift_acceleration=-inertia.local_shift_acceleration_gain),
    )
    axial = snapshot.primary_mechanism.closing_force + axial_inertial_reaction
    return rotation, axial


def solve_deadzone_primary_free(
    snapshot: DeadzoneSnapshot,
) -> tuple[float, float]:
    """Solve the mechanism-equivalent 2x2 deadzone primary closure."""

    rotation, axial = _primary_deadzone_relations(snapshot)
    unknowns = (
        ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION,
        ClosureUnknown.SHIFT_ACCELERATION,
    )
    matrix = np.asarray(
        [
            [relation.gains[unknown] for unknown in unknowns]
            for relation in (rotation, axial)
        ],
        dtype=float,
    )
    rhs = -np.asarray([rotation.bias, axial.bias], dtype=float)

    # Row scaling changes only numerical conditioning, never the physical
    # residuals or recovered unknowns.
    scales = np.maximum(np.max(np.abs(matrix), axis=1), np.abs(rhs))
    scales = np.where(scales > 0.0, scales, 1.0)
    try:
        solution = np.linalg.solve(matrix / scales[:, None], rhs / scales)
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "Deadzone primary rotation/shift closure is singular for the installed mechanism."
        ) from exc
    if not np.all(np.isfinite(solution)):
        raise RuntimeError(
            "Deadzone primary closure produced non-finite accelerations."
        )
    return float(solution[0]), float(solution[1])


def solve_deadzone_primary_rotation_at_fixed_shift(
    snapshot: DeadzoneSnapshot,
) -> float:
    """Solve primary shaft acceleration with ``s_ddot = 0`` at a deadzone stop."""

    rotation, _ = _primary_deadzone_relations(snapshot)
    coefficient = rotation.gains.primary_angular_acceleration
    if coefficient == 0.0:
        raise RuntimeError(
            "Fixed-shift deadzone primary rotational closure is singular."
        )
    return float(-rotation.bias / coefficient)


def deadzone_primary_axial_residual(
    *,
    snapshot: DeadzoneSnapshot,
    primary_angular_acceleration: float,
    shift_acceleration: float,
) -> float:
    """Evaluate the free primary axial residual at selected accelerations."""

    _, axial = _primary_deadzone_relations(snapshot)
    return (
        axial.bias
        + axial.gains.primary_angular_acceleration * primary_angular_acceleration
        + axial.gains.shift_acceleration * shift_acceleration
    )


def build_deadzone_free_derivative(
    *,
    snapshot: DeadzoneSnapshot,
) -> CVTStateDerivative:
    primary_angular_acceleration, shift_acceleration = solve_deadzone_primary_free(
        snapshot
    )
    secondary_angular_acceleration = solve_deadzone_secondary_rotation(snapshot)

    return CVTStateDerivative(
        primary_angular_acceleration=primary_angular_acceleration,
        secondary_angular_acceleration=secondary_angular_acceleration,
        belt_acceleration=(
            snapshot.belt_secondary_lock_radius * secondary_angular_acceleration
        ),
        shift_position_rate=snapshot.state.shift_speed,
        shift_acceleration=shift_acceleration,
    )


def solve_deadzone_secondary_rotation(snapshot: DeadzoneSnapshot) -> float:
    """Solve the belt-locked secondary shaft with all mounted element torques.

    Secondary local axial travel is fixed in deadzone. A helix therefore
    contributes its movable-member absolute inertia, while any flyweight
    contributes its current shaft-axis inertia. The rigid term excludes
    inertia already returned by those mounted elements.
    """

    rotation = (
        AffineClosureScalar(bias=snapshot.secondary_external_torque)
        + snapshot.secondary_mechanism.shaft_torque
        + AffineClosureScalar(
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    -snapshot.secondary_rigid_belt_locked_inertia
                )
            )
        )
    )
    gains = rotation.gains
    for unknown in ClosureUnknown:
        if unknown is ClosureUnknown.SECONDARY_ANGULAR_ACCELERATION:
            continue
        if gains[unknown] != 0.0:
            raise RuntimeError(
                "A secondary-mounted element introduced a deadzone coupling "
                f"to unsupported closure unknown {unknown.name}."
            )
    coefficient = gains.secondary_angular_acceleration
    if coefficient == 0.0:
        raise RuntimeError("Deadzone secondary rotational closure is singular.")
    return float(-rotation.bias / coefficient)
