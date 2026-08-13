"""Top-level CVT operating regimes independent of contact topology.

The contact topology is meaningful only while the primary has physically
closed enough to engage the belt. Primary travel constraints are a separate
axis. With a positive-width deadzone, the engaged low-ratio seat at the
engagement boundary is distinct from the lower mechanical stop below neutral.
With a zero-width deadzone those positions coincide physically, but the active
regime is still the engaged low-ratio-seat closure rather than a deadzone stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from cinder.model.cvt.contact import ContactRegime


class CVTEngagementState(str, Enum):
    """Whether the primary belt contact is physically disengaged or engaged."""

    DEADZONE = "deadzone"
    ENGAGED = "engaged"


class CVTShiftConstraint(str, Enum):
    """Admissible constraints on the global primary shift coordinate."""

    FREE = "free"
    LOWER_STOP = "lower_stop"
    LOW_RATIO_SEAT = "low_ratio_seat"
    UPPER_STOP = "upper_stop"


@dataclass(frozen=True, slots=True)
class CVTOperatingRegime:
    """One physically meaningful CVT segment regime.

    Valid combinations are deliberately limited to:

    * ``deadzone + free``;
    * ``deadzone + lower_stop``;
    * ``engaged + free + ContactRegime``;
    * ``engaged + low_ratio_seat + ContactRegime``; and
    * ``engaged + upper_stop + ContactRegime``.

    The low-ratio seat is an engaged minimum-radius boundary at which the
    primary may still clamp the belt. For a positive-width deadzone it is
    distinct from the lower deadzone stop and may release to neutral only after
    the primary actuator itself loses closing force. For a zero-width deadzone
    it is also the physical lower travel boundary and there is no neutral
    successor.
    """

    engagement: CVTEngagementState
    shift_constraint: CVTShiftConstraint
    contact_regime: ContactRegime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.engagement, CVTEngagementState):
            raise TypeError("engagement must be a CVTEngagementState.")
        if not isinstance(self.shift_constraint, CVTShiftConstraint):
            raise TypeError("shift_constraint must be a CVTShiftConstraint.")

        if self.engagement is CVTEngagementState.DEADZONE:
            if self.contact_regime is not None:
                raise ValueError(
                    "A deadzone regime cannot carry an engaged contact regime."
                )
            if self.shift_constraint not in (
                CVTShiftConstraint.FREE,
                CVTShiftConstraint.LOWER_STOP,
            ):
                raise ValueError(
                    "A deadzone regime may be free or at the lower stop only."
                )
            return

        if self.contact_regime is None:
            raise ValueError("An engaged regime requires a ContactRegime.")
        if self.shift_constraint not in (
            CVTShiftConstraint.FREE,
            CVTShiftConstraint.LOW_RATIO_SEAT,
            CVTShiftConstraint.UPPER_STOP,
        ):
            raise ValueError(
                "An engaged regime may be free, at the low-ratio seat, or at the upper stop."
            )

    @classmethod
    def deadzone_free(cls) -> "CVTOperatingRegime":
        return cls(
            engagement=CVTEngagementState.DEADZONE,
            shift_constraint=CVTShiftConstraint.FREE,
        )

    @classmethod
    def deadzone_lower_stop(cls) -> "CVTOperatingRegime":
        return cls(
            engagement=CVTEngagementState.DEADZONE,
            shift_constraint=CVTShiftConstraint.LOWER_STOP,
        )

    @classmethod
    def engaged_free(cls, *, contact_regime: ContactRegime) -> "CVTOperatingRegime":
        return cls(
            engagement=CVTEngagementState.ENGAGED,
            shift_constraint=CVTShiftConstraint.FREE,
            contact_regime=contact_regime,
        )

    @classmethod
    def engaged_low_ratio_seat(
        cls,
        *,
        contact_regime: ContactRegime,
    ) -> "CVTOperatingRegime":
        return cls(
            engagement=CVTEngagementState.ENGAGED,
            shift_constraint=CVTShiftConstraint.LOW_RATIO_SEAT,
            contact_regime=contact_regime,
        )

    @classmethod
    def engaged_upper_stop(
        cls,
        *,
        contact_regime: ContactRegime,
    ) -> "CVTOperatingRegime":
        return cls(
            engagement=CVTEngagementState.ENGAGED,
            shift_constraint=CVTShiftConstraint.UPPER_STOP,
            contact_regime=contact_regime,
        )

    @property
    def is_deadzone(self) -> bool:
        return self.engagement is CVTEngagementState.DEADZONE

    @property
    def is_engaged(self) -> bool:
        return self.engagement is CVTEngagementState.ENGAGED

    @property
    def is_free_shift(self) -> bool:
        return self.shift_constraint is CVTShiftConstraint.FREE
