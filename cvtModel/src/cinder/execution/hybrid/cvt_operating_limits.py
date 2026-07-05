"""Physical shift boundaries for the complete CVT operating-regime graph."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class CVTShiftOperatingLimits:
    """Ordered lower stop, engagement boundary, and upper stop positions.

    The interval is intentionally divided as

    ``lower_stop <= s < engagement_shift``
        deadzone / neutral;

    ``engagement_shift <= s <= upper_stop``
        engaged primary-belt contact.

    This object describes physical regime boundaries.  It does not prescribe
    any stop reaction or deadzone dynamics; those belong to the corresponding
    RHS implementations.
    """

    lower_stop_shift: float
    engagement_shift: float
    upper_stop_shift: float

    def __post_init__(self) -> None:
        for name, value in (
            ("lower_stop_shift", self.lower_stop_shift),
            ("engagement_shift", self.engagement_shift),
            ("upper_stop_shift", self.upper_stop_shift),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if not self.lower_stop_shift < self.engagement_shift < self.upper_stop_shift:
            raise ValueError(
                "Shift limits must satisfy lower_stop_shift < engagement_shift < upper_stop_shift."
            )

    @classmethod
    def from_geometry_spec(cls, geometry_spec) -> "CVTShiftOperatingLimits":
        """Use the geometry domain endpoints as temporary physical stops."""

        return cls(
            lower_stop_shift=0.0,
            engagement_shift=float(geometry_spec.deadzone_shift),
            upper_stop_shift=float(geometry_spec.max_shift),
        )

    def validate_against_geometry_spec(self, geometry_spec) -> None:
        """Ensure every physical boundary lies in the geometry's legal domain."""

        if self.lower_stop_shift < 0.0:
            raise ValueError("lower_stop_shift must not lie below the geometry domain.")
        if self.upper_stop_shift > geometry_spec.max_shift:
            raise ValueError(
                "upper_stop_shift must not exceed geometry.spec.max_shift."
            )
        if self.engagement_shift != geometry_spec.deadzone_shift:
            raise ValueError(
                "engagement_shift must equal geometry.spec.deadzone_shift: the current "
                "geometry switches primary radius behavior at that same physical boundary."
            )

    def is_in_deadzone(self, shift_position: float) -> bool:
        return self.lower_stop_shift <= shift_position < self.engagement_shift

    def is_engaged(self, shift_position: float) -> bool:
        return self.engagement_shift <= shift_position <= self.upper_stop_shift
