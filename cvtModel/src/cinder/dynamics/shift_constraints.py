"""Engaged-shift constraints and physical upper-stop reaction recovery.

The free engaged closure solves the primary axial equation for ``s_ddot``.
At the high-ratio mechanical stop, that degree of freedom is instead
constrained:

    s_dot = 0,
    s_ddot = 0.

The primary axial balance is not discarded.  Its residual is recovered after
solving as the unilateral stop reaction.  This keeps the canonical eight
closure unknowns unchanged and avoids a hidden state clamp or a ninth
algebraic unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, tan

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains, ClosureUnknowns

from .snapshot import DynamicsSnapshot


class EngagedShiftConstraint(str, Enum):
    """How the engaged primary shift coordinate is treated in one closure."""

    FREE = "free"
    UPPER_STOP = "upper_stop"


@dataclass(frozen=True, slots=True)
class UpperStopReaction:
    """Recovered unilateral reaction of the engaged upper mechanical stop.

    ``opening_direction_magnitude`` is positive when the high-ratio stop pushes
    against an otherwise positive, further-closing free-shift tendency.  The
    stop can remain active only while this magnitude is non-negative.
    """

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
    """Build the fourth state-fixed closure row for one engaged constraint.

    The free case is represented by the ordinary primary axial row elsewhere.
    At the upper stop, the replacement row is exactly ``s_ddot = 0``.  The
    primary axial balance is evaluated after the solve to recover the stop
    reaction, rather than adding a ninth unknown.
    """

    if constraint is not EngagedShiftConstraint.UPPER_STOP:
        raise ValueError(
            "build_shift_constraint_equation() is only valid for the upper stop."
        )

    return ClosureEquation(
        name="upper_shift_stop_constraint",
        residual=AffineClosureScalar(
            gains=ClosureGains(shift_acceleration=1.0),
        ),
    )


def recover_upper_stop_reaction(
    *,
    snapshot: DynamicsSnapshot,
    unknowns: ClosureUnknowns,
) -> UpperStopReaction:
    """Recover the upper-stop reaction from the omitted primary axial row.

    The free primary balance is

        m_p s_ddot + m_p x_p'' s_dot^2 + N_p/(2 tan(beta)) - F_p = 0.

    At the upper stop, the reaction acts in the opening direction, so

        R_high = F_p - m_p x_p'' s_dot^2
                 - m_p x_p' s_ddot - N_p/(2 tan(beta)).

    The constrained row enforces ``s_ddot = 0``.  Keeping the general form
    here makes this an exact negative of the omitted free primary-row residual
    and gives a useful diagnostic if a caller inspects a non-ideal trial.
    """

    if not isinstance(snapshot, DynamicsSnapshot):
        raise TypeError("snapshot must be a DynamicsSnapshot instance.")
    if not isinstance(unknowns, ClosureUnknowns):
        raise TypeError("unknowns must be a ClosureUnknowns instance.")

    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")

    inertia = snapshot.axial_translation_inertias.primary
    primary_force = snapshot.primary_actuation.force(unknowns)
    reaction = (
        primary_force
        - inertia.local_known_inertial_force(shift_speed=snapshot.state.shift_speed)
        - inertia.local_shift_acceleration_gain * unknowns.shift_acceleration
        - unknowns.primary_normal_resultant / (2.0 * tangent)
    )
    return UpperStopReaction(opening_direction_magnitude=reaction)
