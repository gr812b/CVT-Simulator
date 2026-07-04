"""Physical engaged-shift travel guards for the current CVT coordinate.

The continuous engaged-contact equations are valid only while the movable
primary sheave lies strictly between its two mechanical travel stops.  These
limits are intentionally independent of the geometry's mathematical domain:
the geometry can still describe the complete belt path, while the hybrid
system stops before it continues through a metal-on-metal end stop without a
separate reaction/impact model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class EngagedShiftTravelLimits:
    """Closed physical travel interval used by the engaged hybrid system.

    ``minimum_shift`` and ``maximum_shift`` are positions of the physical
    axial travel stops in CINDER's primary-moving-sheave coordinate.  Reaching
    either stop is currently terminal: the next model extension will add a
    constrained stop-reaction branch and an impact/reset policy for nonzero
    arrival speed.

    The lower stop may be placed above ``deadzone_shift`` while deadzone is
    unmodelled.  That is useful for engaged-only diagnostics because it keeps
    every accepted trajectory out of the unimplemented pre-engagement range.
    """

    minimum_shift: float
    maximum_shift: float

    def __post_init__(self) -> None:
        for name, value in (
            ("minimum_shift", self.minimum_shift),
            ("maximum_shift", self.maximum_shift),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if not self.minimum_shift < self.maximum_shift:
            raise ValueError("minimum_shift must be strictly below maximum_shift.")

    @classmethod
    def from_geometry_spec(cls, geometry_spec) -> "EngagedShiftTravelLimits":
        """Return the default engaged interval from one geometry specification."""

        return cls(
            minimum_shift=float(geometry_spec.deadzone_shift),
            maximum_shift=float(geometry_spec.max_shift),
        )

    def validate_against_geometry_spec(self, geometry_spec) -> None:
        """Ensure these hardware stops remain in the engaged geometry domain."""

        if self.minimum_shift < geometry_spec.deadzone_shift:
            raise ValueError(
                "Engaged minimum_shift must not enter the unimplemented deadzone; "
                f"got {self.minimum_shift:.9g} < {geometry_spec.deadzone_shift:.9g}."
            )
        if self.maximum_shift > geometry_spec.max_shift:
            raise ValueError(
                "Engaged maximum_shift must not exceed the geometry domain; "
                f"got {self.maximum_shift:.9g} > {geometry_spec.max_shift:.9g}."
            )

    def contains(self, shift_position: float) -> bool:
        """Return whether a position lies in the closed physical interval."""

        return self.minimum_shift <= shift_position <= self.maximum_shift

    def contains_strictly(self, shift_position: float) -> bool:
        """Return whether a free-motion initial state lies between the stops."""

        return self.minimum_shift < shift_position < self.maximum_shift
