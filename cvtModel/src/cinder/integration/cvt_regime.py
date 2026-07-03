"""Top-level CVT operating regimes independent of the engaged contact topology.

The contact regime is meaningful only when the primary has physically closed
far enough to engage the belt.  Mechanical stops are separate unilateral
constraints on the global shift coordinate.  Keeping those axes separate
avoids impossible combinations such as a deadzone contact branch or an
engaged lower-stop branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from cinder.contact import ContactRegime


class CVTEngagementState(str, Enum):
    """Whether the primary belt contact is physically disengaged or engaged."""

    DEADZONE = "deadzone"
    ENGAGED = "engaged"


class CVTShiftConstraint(str, Enum):
    """Admissible constraints on the global primary shift coordinate."""

    FREE = "free"
    LOWER_STOP = "lower_stop"
    UPPER_STOP = "upper_stop"


@dataclass(frozen=True, slots=True)
class CVTOperatingRegime:
    """One physically meaningful CVT segment regime.

    Valid combinations are deliberately limited to:

    * ``deadzone + free``;
    * ``deadzone + lower_stop``;
    * ``engaged + free + ContactRegime``; and
    * ``engaged + upper_stop + ContactRegime``.

    The lower mechanical stop lies below the primary engagement boundary, so
    it is necessarily a deadzone condition.  Conversely, the upper stop is
    necessarily an engaged condition.  A deadzone has no primary traction
    closure and therefore carries no :class:`ContactRegime`.
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
                raise ValueError("A deadzone regime cannot carry an engaged contact regime.")
            if self.shift_constraint not in (
                CVTShiftConstraint.FREE,
                CVTShiftConstraint.LOWER_STOP,
            ):
                raise ValueError("A deadzone regime may be free or at the lower stop only.")
            return

        if self.contact_regime is None:
            raise ValueError("An engaged regime requires a ContactRegime.")
        if self.shift_constraint not in (
            CVTShiftConstraint.FREE,
            CVTShiftConstraint.UPPER_STOP,
        ):
            raise ValueError("An engaged regime may be free or at the upper stop only.")

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
