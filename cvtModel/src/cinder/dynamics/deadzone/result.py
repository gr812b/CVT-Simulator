"""Results returned by the reduced primary-disengaged deadzone model."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.integration import CVTDynamicState, CVTDynamicStateDerivative

from .snapshot import DeadzoneSnapshot


@dataclass(frozen=True, slots=True)
class LowerStopReaction:
    """Recovered unilateral lower-stop reaction.

    ``closing_direction_magnitude`` is positive when the low-ratio stop pushes
    in positive global-shift direction, opposing an otherwise opening primary
    tendency.  The lower stop is admissible only while this value is
    non-negative; it releases as it crosses downward through zero.
    """

    closing_direction_magnitude: float

    def __post_init__(self) -> None:
        if not isfinite(self.closing_direction_magnitude):
            raise ValueError("closing_direction_magnitude must be finite.")

    @property
    def is_unilaterally_admissible(self) -> bool:
        """Return whether the lower stop can push without needing to pull."""

        return self.closing_direction_magnitude >= 0.0


@dataclass(frozen=True, slots=True)
class DeadzoneEvaluation:
    """One auditable RHS evaluation in free or lower-stop deadzone motion.

    No engaged-contact quantities are invented here.  The primary normal and
    primary transmitted torque are identically zero by model assumption;
    secondary normal/lambda quantities are intentionally absent because the
    belt-secondary lock is imposed rather than solved through engaged-wrap
    contact closure.
    """

    state: CVTDynamicState
    snapshot: DeadzoneSnapshot
    state_derivative: CVTDynamicStateDerivative
    lower_stop_reaction: LowerStopReaction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, CVTDynamicState):
            raise TypeError("state must be a CVTDynamicState instance.")
        if not isinstance(self.snapshot, DeadzoneSnapshot):
            raise TypeError("snapshot must be a DeadzoneSnapshot instance.")
        if not isinstance(self.state_derivative, CVTDynamicStateDerivative):
            raise TypeError("state_derivative must be a CVTDynamicStateDerivative instance.")

    @property
    def primary_normal_resultant(self) -> float:
        """Return the absent primary-contact normal resultant, exactly zero."""

        return 0.0

    @property
    def primary_transmitted_torque(self) -> float:
        """Return the absent primary-contact transmitted torque, exactly zero."""

        return 0.0

    @property
    def secondary_normal_resultant(self) -> None:
        """Secondary normal is not solved under the imposed belt-secondary lock."""

        return None

    @property
    def belt_secondary_speed_residual(self) -> float:
        """Return ``v_b - r_s omega_s`` at the evaluated state."""

        return self.snapshot.belt_secondary_speed_residual

    @property
    def belt_secondary_acceleration_residual(self) -> float:
        """Return ``v_b_dot - r_s alpha_s`` under fixed deadzone geometry."""

        return (
            self.state_derivative.belt_acceleration
            - self.snapshot.belt_secondary_lock_radius
            * self.state_derivative.secondary_angular_acceleration
        )

    @property
    def stop_reaction(self) -> float | None:
        """Return the scalar reaction magnitude for generic future dispatch."""

        if self.lower_stop_reaction is None:
            return None
        return self.lower_stop_reaction.closing_direction_magnitude
