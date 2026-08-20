"""Engaged-shift constraints and recovered unilateral reactions.

The free engaged closure solves the primary axial equation for ``s_ddot``.
Two non-free constraints can instead hold the primary coordinate:

* the low-ratio engagement seat at ``s = s_engage``; and
* the high-ratio mechanical stop at ``s = s_upper``.

Both constraints impose

    s_dot = 0,
    s_ddot = 0.

The primary axial balance is not discarded.  It is recovered after the
8-by-8 solve as a unilateral reaction, preserving the canonical closure
unknown basis and keeping the constraint force visible rather than hiding a
state clamp inside the RHS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import cos, isfinite

from cinder.model.cvt.closure import (
    AffineClosureScalar,
    ClosureEquation,
    ClosureGains,
    ClosureUnknowns,
)

from cinder.model.system.evaluator import DynamicsSnapshot


class EngagedShiftConstraint(str, Enum):
    """How one engaged-contact closure constrains the primary shift coordinate."""

    FREE = "free"
    LOW_RATIO_SEAT = "low_ratio_seat"
    UPPER_STOP = "upper_stop"


@dataclass(frozen=True, slots=True)
class LowRatioSeatReaction:
    """Recovered closing-direction reaction at the engaged low-ratio seat.

    A positive value means the seat must push in the positive global-shift
    direction to prevent further opening below the engaged minimum-radius
    configuration.  This reaction determines whether the *seat* can hold; it
    does not itself authorize primary disengagement.  Loss of primary actuator
    clamp is the separate condition that permits deadzone entry.
    """

    closing_direction_magnitude: float

    def __post_init__(self) -> None:
        if not isfinite(self.closing_direction_magnitude):
            raise ValueError("closing_direction_magnitude must be finite.")

    @property
    def is_unilaterally_admissible(self) -> bool:
        """Return whether the seat can push closed rather than pull open."""

        return self.closing_direction_magnitude >= 0.0


@dataclass(frozen=True, slots=True)
class UpperStopReaction:
    """Recovered opening-direction reaction of the high-ratio mechanical stop."""

    opening_direction_magnitude: float

    def __post_init__(self) -> None:
        if not isfinite(self.opening_direction_magnitude):
            raise ValueError("opening_direction_magnitude must be finite.")

    @property
    def is_unilaterally_admissible(self) -> bool:
        """Return whether the stop can push, rather than needing to pull."""

        return self.opening_direction_magnitude >= 0.0


def build_shift_constraint_equation(
    *,
    constraint: EngagedShiftConstraint,
) -> ClosureEquation:
    """Build the fourth state-fixed closure row for one fixed-shift constraint.

    The free case is represented by the ordinary primary axial row elsewhere.
    Both non-free constraints replace it with the exact kinematic row
    ``s_ddot = 0``.  The omitted primary axial balance is recovered after the
    solve with the direction appropriate to the active unilateral boundary.
    """

    if constraint is EngagedShiftConstraint.FREE:
        raise ValueError(
            "build_shift_constraint_equation() is only valid for a non-free "
            "engaged shift constraint."
        )

    if constraint is EngagedShiftConstraint.LOW_RATIO_SEAT:
        name = "low_ratio_seat_constraint"
    elif constraint is EngagedShiftConstraint.UPPER_STOP:
        name = "upper_shift_stop_constraint"
    else:  # pragma: no cover - defensive enum exhaustiveness.
        raise ValueError(f"Unsupported engaged shift constraint: {constraint!r}.")

    return ClosureEquation(
        name=name,
        residual=AffineClosureScalar(
            gains=ClosureGains(shift_acceleration=1.0),
        ),
    )


def recover_low_ratio_seat_reaction(
    *,
    snapshot: DynamicsSnapshot,
    unknowns: ClosureUnknowns,
) -> LowRatioSeatReaction:
    """Recover the low-ratio seat reaction from the omitted primary row.

    The unconstrained primary balance is

        m_p s_ddot + C_p + N_p cos(beta) / 2 - F_p = 0.

    Here ``N_p`` is the physical integrated face-normal resultant. At the
    low-ratio seat, a positive reaction acts in the closing/global
    positive-shift direction.  Therefore

        R_seat = m_p s_ddot + C_p + N_p cos(beta)/2 - F_p.

    The seat can hold only while ``R_seat >= 0``.  The separate engagement
    transition policy decides when a nonnegative primary clamp is sufficient to
    keep the belt engaged instead of allowing a deadzone transition.
    """

    residual = _free_primary_axial_residual(snapshot=snapshot, unknowns=unknowns)
    return LowRatioSeatReaction(closing_direction_magnitude=residual)


def recover_upper_stop_reaction(
    *,
    snapshot: DynamicsSnapshot,
    unknowns: ClosureUnknowns,
) -> UpperStopReaction:
    """Recover the upper-stop opening reaction from the omitted primary row.

    The high stop reaction is the negative of the unconstrained primary-row
    residual because its positive direction opposes further positive shift.
    """

    residual = _free_primary_axial_residual(snapshot=snapshot, unknowns=unknowns)
    return UpperStopReaction(opening_direction_magnitude=-residual)


def _free_primary_axial_residual(
    *,
    snapshot: DynamicsSnapshot,
    unknowns: ClosureUnknowns,
) -> float:
    """Evaluate the free primary axial-row residual at one closure solution."""

    if not isinstance(snapshot, DynamicsSnapshot):
        raise TypeError("snapshot must be a DynamicsSnapshot instance.")
    if not isinstance(unknowns, ClosureUnknowns):
        raise TypeError("unknowns must be a ClosureUnknowns instance.")

    cosine = cos(snapshot.sheave_half_angle)
    if not isfinite(cosine) or cosine <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite cosine.")

    inertia = snapshot.axial_translation_inertias.primary
    primary_force = snapshot.primary_actuation.evaluate(unknowns)
    return (
        inertia.local_known_inertial_force(shift_speed=snapshot.state.shift_speed)
        + inertia.local_shift_acceleration_gain * unknowns.shift_acceleration
        + 0.5 * cosine * unknowns.primary_normal_resultant
        - primary_force
    )
