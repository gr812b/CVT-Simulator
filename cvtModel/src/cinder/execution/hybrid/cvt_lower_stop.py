"""Event-facing lower mechanical-stop helpers for the deadzone regime."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite

from .state import CVTState


def apply_perfectly_inelastic_lower_stop_impact(
    *,
    state: CVTState,
    lower_stop_shift: float,
) -> CVTState:
    """Project deadzone arrival onto the low-ratio mechanical stop.

    LEGACY KINEMATIC HELPER ONLY.  Production hybrid transitions use the
    mass-metric momentum projector in ``cvt_impact``; this helper is retained
    for old preview/API compatibility and does not redistribute coupled
    momentum.

    This legacy first-order helper applies:

        s^+ = s_lower,
        s_dot^+ = 0.

    Primary, secondary, and belt speeds remain continuous.  A later
    generalized impulse projection can replace it if primary-ramp inertial
    coupling is promoted into the impact model.
    """

    if not isinstance(state, CVTState):
        raise TypeError("state must be a CVTState instance.")
    if not isfinite(lower_stop_shift):
        raise ValueError("lower_stop_shift must be finite.")

    return replace(
        state,
        shift_position=float(lower_stop_shift),
        shift_speed=0.0,
    )


def lower_stop_release_value(*, closing_reaction: float) -> float:
    """Return the unilateral low-stop release indicator ``R_low``.

    The lower stop is admissible while ``R_low >= 0`` and releases when the
    required closing-direction reaction crosses downward through zero.
    """

    if not isfinite(closing_reaction):
        raise ValueError("closing_reaction must be finite.")
    return float(closing_reaction)
