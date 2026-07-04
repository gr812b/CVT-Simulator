"""Small event-facing helpers for the engaged upper mechanical stop.

The constrained closure itself lives in :mod:`cinder.dynamics.shift_constraints`.
This module contains only the hybrid-layer pieces that do not know contact
lambda algebra: the perfectly inelastic arrival reset and the scalar release
quantity consumed by a later event factory.
"""

from __future__ import annotations

from dataclasses import replace
from math import isfinite

from .state import CVTDynamicState


def apply_perfectly_inelastic_upper_stop_impact(
    *,
    state: CVTDynamicState,
    upper_stop_shift: float,
) -> CVTDynamicState:
    """Project one free engaged arrival onto the high-ratio mechanical stop.

    This first stop model is intentionally perfectly inelastic in the axial
    coordinate:

        s^+ = s_upper,
        s_dot^+ = 0.

    Shaft and belt speeds remain continuous.  A later generalized-momentum
    impact map can replace this helper if the secondary helix's impulse
    redistribution is modelled explicitly.
    """

    if not isinstance(state, CVTDynamicState):
        raise TypeError("state must be a CVTDynamicState instance.")
    if not isfinite(upper_stop_shift):
        raise ValueError("upper_stop_shift must be finite.")

    return replace(
        state,
        shift_position=float(upper_stop_shift),
        shift_speed=0.0,
    )


def upper_stop_release_value(*, opening_reaction: float) -> float:
    """Return the unilateral high-stop event value.

    The upper stop is admissible while ``R_high >= 0``.  A future terminal
    release event should use this value with a negative crossing direction:

        R_high = 0,  from positive to negative.
    """

    if not isfinite(opening_reaction):
        raise ValueError("opening_reaction must be finite.")
    return float(opening_reaction)
