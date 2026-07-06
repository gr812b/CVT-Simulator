"""Lower mechanical-stop constraint for the primary-disengaged deadzone."""

from __future__ import annotations

from math import isclose, isfinite

from cinder.execution.hybrid import CVTDynamicStateDerivative

from .free import build_deadzone_free_derivative, require_known_primary_actuation
from .result import DeadzoneEvaluation, LowerStopReaction
from .snapshot import DeadzoneSnapshot


def evaluate_deadzone_lower_stop(
    *,
    snapshot: DeadzoneSnapshot,
    lower_stop_shift: float,
) -> DeadzoneEvaluation:
    """Evaluate the lower-stop constrained deadzone RHS.

    The free primary axial balance is

        m_p x_p'' s_dot^2 + m_p x_p' s_ddot - F_p = 0.

    At the lower stop, ``s_dot = s_ddot = 0``.  Define a positive reaction as
    acting in the closing/global-positive shift direction.  The omitted axial
    balance then recovers

        R_low = m_p x_p'' s_dot^2 - F_p.

    The stop is unilateral and can hold only while ``R_low >= 0``.
    """

    if not isinstance(snapshot, DeadzoneSnapshot):
        raise TypeError("snapshot must be a DeadzoneSnapshot instance.")
    if not isfinite(lower_stop_shift):
        raise ValueError("lower_stop_shift must be finite.")
    if not isclose(
        snapshot.state.shift_position,
        lower_stop_shift,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise ValueError(
            "A lower-stop evaluation requires state.shift_position at lower_stop_shift."
        )
    if not isclose(
        snapshot.state.shift_speed,
        0.0,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise ValueError(
            "A lower-stop evaluation requires zero shift_speed after impact projection."
        )

    require_known_primary_actuation(snapshot=snapshot)
    free_derivative = build_deadzone_free_derivative(snapshot=snapshot)
    derivative = CVTDynamicStateDerivative(
        primary_angular_acceleration=free_derivative.primary_angular_acceleration,
        secondary_angular_acceleration=free_derivative.secondary_angular_acceleration,
        belt_acceleration=free_derivative.belt_acceleration,
        shift_position_rate=0.0,
        shift_acceleration=0.0,
        secondary_shaft_angle_rate=free_derivative.secondary_shaft_angle_rate,
    )

    primary_inertia = snapshot.primary_axial_inertia
    reaction = LowerStopReaction(
        closing_direction_magnitude=(
            primary_inertia.local_known_inertial_force(
                shift_speed=snapshot.state.shift_speed,
            )
            - snapshot.primary_actuation.bias
        )
    )
    return DeadzoneEvaluation(
        state=snapshot.state,
        snapshot=snapshot,
        state_derivative=derivative,
        lower_stop_reaction=reaction,
    )
