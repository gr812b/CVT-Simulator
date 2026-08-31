"""Lower mechanical-stop constraint for the primary-disengaged deadzone."""

from __future__ import annotations

from math import isclose, isfinite

from cinder.model.system.state import CVTStateDerivative

from .free import (
    deadzone_primary_axial_residual,
    solve_deadzone_primary_rotation_at_fixed_shift,
    solve_deadzone_secondary_rotation,
)
from .result import DeadzoneEvaluation, LowerStopReaction
from .snapshot import DeadzoneSnapshot


def evaluate_deadzone_lower_stop(
    *,
    snapshot: DeadzoneSnapshot,
    lower_stop_shift: float,
) -> DeadzoneEvaluation:
    """Evaluate the lower-stop constrained deadzone RHS.

    The stop fixes ``s_dot = s_ddot = 0`` but does not remove any rotational
    coupling of the installed primary mechanism. Shaft acceleration is solved
    with fixed shift, then the omitted free axial balance recovers the stop
    reaction. A positive reaction pushes in the closing direction.
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

    primary_angular_acceleration = solve_deadzone_primary_rotation_at_fixed_shift(
        snapshot
    )
    secondary_angular_acceleration = solve_deadzone_secondary_rotation(snapshot)
    derivative = CVTStateDerivative(
        primary_angular_acceleration=primary_angular_acceleration,
        secondary_angular_acceleration=secondary_angular_acceleration,
        belt_acceleration=(
            snapshot.belt_secondary_lock_radius * secondary_angular_acceleration
        ),
        shift_position_rate=0.0,
        shift_acceleration=0.0,
    )

    free_axial_residual = deadzone_primary_axial_residual(
        snapshot=snapshot,
        primary_angular_acceleration=primary_angular_acceleration,
        shift_acceleration=0.0,
    )
    reaction = LowerStopReaction(closing_direction_magnitude=-free_axial_residual)
    return DeadzoneEvaluation(
        state=snapshot.state,
        snapshot=snapshot,
        state_derivative=derivative,
        lower_stop_reaction=reaction,
    )
