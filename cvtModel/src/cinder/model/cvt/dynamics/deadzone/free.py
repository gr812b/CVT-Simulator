"""Reduced free-motion RHS for the primary-disengaged CVT deadzone."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isclose

import numpy as np

from cinder.model.system.evaluator import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues
from cinder.model.system.state import CVTState, CVTStateDerivative

from .result import DeadzoneEvaluation
from .snapshot import DeadzoneSnapshot, build_deadzone_snapshot


@dataclass(slots=True)
class DeadzoneDynamicsEvaluator:
    """Evaluate neutral/free and neutral/lower-stop CVT mechanics.

    This evaluator is intentionally independent of the engaged lambda closure.
    It treats the primary as a free rotational/axial subsystem and imposes the
    chosen deadzone assumption that the belt is locked to the secondary at the
    low-ratio geometry.
    """

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
        """Construct and validate one deadzone frozen snapshot.

        During event localization, a rejected Runge--Kutta stage can lie just
        beyond the deadzone geometry interval before ``solve_ivp`` locates an
        engagement or lower-stop event.  The snapshot is evaluated at the
        nearest legal deadzone coordinate for that rejected stage only.  Event
        functions retain the raw state, and accepted segments still terminate
        at the physical boundary; this is not a continuous-state clamp.
        """

        snapshot = build_deadzone_snapshot(
            model=self.model,
            state=self._geometry_safe_state(state),
            shaft_boundaries=shaft_boundaries,
        )
        self._validate_belt_secondary_lock(snapshot=snapshot)
        return snapshot

    def _geometry_safe_state(self, state: CVTState) -> CVTState:
        """Project only out-of-domain integration stages into deadzone geometry."""

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
        """Return the reduced RHS for free primary travel below engagement.

        The governing equations are

            I_p alpha_p = tau_eng,
            m_p x_p'' s_dot^2 + m_p x_p' s_ddot = F_p,
            (I_s + m_b r_s^2) alpha_s = tau_ext,s,
            v_b_dot = r_s alpha_s.

        No primary belt torque, primary normal resultant, lambda utilization,
        or tension-loop equation is present.
        """

        snapshot = self.snapshot(state=state, shaft_boundaries=shaft_boundaries)
        derivative = build_deadzone_free_derivative(snapshot=snapshot)
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
        """Return constrained deadzone dynamics at the lower mechanical stop."""

        from .lower_stop import evaluate_deadzone_lower_stop

        snapshot = self.snapshot(state=state, shaft_boundaries=shaft_boundaries)
        return evaluate_deadzone_lower_stop(
            snapshot=snapshot,
            lower_stop_shift=lower_stop_shift,
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


def build_deadzone_free_derivative(
    *,
    snapshot: DeadzoneSnapshot,
) -> CVTStateDerivative:
    """Assemble the direct reduced deadzone derivative from one snapshot."""

    require_known_primary_actuation(snapshot=snapshot)

    primary_angular_acceleration = (
        snapshot.primary_external_torque / snapshot.primary_rotational_inertia
    )

    primary_inertia = snapshot.primary_axial_inertia
    shift_acceleration = (
        snapshot.primary_actuation.bias
        - primary_inertia.local_known_inertial_force(
            shift_speed=snapshot.state.shift_speed,
        )
    ) / primary_inertia.local_shift_acceleration_gain

    secondary_angular_acceleration = (
        snapshot.secondary_external_torque / snapshot.secondary_belt_locked_inertia
    )

    return CVTStateDerivative(
        primary_angular_acceleration=primary_angular_acceleration,
        secondary_angular_acceleration=secondary_angular_acceleration,
        belt_acceleration=(
            snapshot.belt_secondary_lock_radius * secondary_angular_acceleration
        ),
        shift_position_rate=snapshot.state.shift_speed,
        shift_acceleration=shift_acceleration,
    )


def require_known_primary_actuation(*, snapshot: DeadzoneSnapshot) -> None:
    """Reject an un-derived deadzone coupling hidden in primary actuation."""

    gains = snapshot.primary_actuation.gains.as_tuple()
    if any(value != 0.0 for value in gains):
        raise NotImplementedError(
            "Deadzone free dynamics currently requires primary actuation to be a "
            "known force. Add an explicit reduced deadzone closure before using "
            "a primary force law with closure-unknown gains."
        )
