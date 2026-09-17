"""Numerical shaft-speed replay through CINDER's existing shaft torque port.

The replay boundary is intentionally outside the CVT mechanics.  It does not
replace a closure equation, prescribe an acceleration, alter the five-state CVT
plant, or model a physical motor/dynamometer.  At each ordinary boundary
evaluation it returns only an external torque,

    tau_replay = K_omega * (omega_target - omega),

and CINDER advances its existing dynamics normally.

Numerical note
--------------
This is deliberately a stiff penalty boundary.  The Baja hard-replay audit
converged cleanly at the default K_omega = 400 N m s/rad with LSODA settings
rtol=1e-4, atol=1e-7 and max_step=0.05 s.  The same case at rtol=1e-2 could
drive LSODA trial states far outside the physical CVT domain before a rejected
step was possible.  That finding is execution guidance, not hidden boundary
behavior: this class never modifies integrator settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from cinder.model.reference import PiecewiseLinearReference
from cinder.model.system.ports import ShaftBoundaryValue


class _ShaftBoundaryContextLike(Protocol):
    """Structural subset of ShaftBoundaryContext used by the replay law."""

    time: float

    @property
    def shaft_speed(self) -> float: ...  # noqa: E704


@dataclass(frozen=True, slots=True)
class SpeedReplayShaftBoundary:
    """Drive one shaft tightly toward a supplied speed history.

    ``tracking_gain`` is a numerical penalty stiffness, not a hardware
    parameter or torque-authority limit.  Replay torque is intentionally
    unbounded.  The resulting external torque is the torque supplied by this
    numerical boundary at the chosen finite gain; it should not be interpreted
    as available motor/dyno torque without a separate hardware model.

    The default gain is the lowest tested round-number setting that kept the
    hard Baja replay below roughly 1 rpm RMS while retaining useful numerical
    margin when paired with replay-appropriate integration tolerances.
    """

    DEFAULT_TRACKING_GAIN_NM_S_PER_RAD = 400.0

    speed_reference: PiecewiseLinearReference
    tracking_gain: float = DEFAULT_TRACKING_GAIN_NM_S_PER_RAD

    def __post_init__(self) -> None:
        if not isinstance(self.speed_reference, PiecewiseLinearReference):
            raise TypeError("speed_reference must be a PiecewiseLinearReference.")
        if not isfinite(self.tracking_gain) or self.tracking_gain <= 0.0:
            raise ValueError("tracking_gain must be positive and finite.")

    def evaluate(
        self,
        context: _ShaftBoundaryContextLike,
    ) -> ShaftBoundaryValue:
        target_speed = self.speed_reference.value_at(context.time)
        tracking_error = target_speed - context.shaft_speed
        replay_torque = self.tracking_gain * tracking_error
        return ShaftBoundaryValue(
            external_torque=replay_torque,
            equivalent_inertia=0.0,
            metadata={
                "speed_replay_target_rad_per_s": target_speed,
                "speed_replay_error_rad_per_s": tracking_error,
                "speed_replay_gain_Nm_s_per_rad": self.tracking_gain,
                "speed_replay_torque_Nm": replay_torque,
            },
        )
