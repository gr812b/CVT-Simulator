"""Primary-side CVT-core inertia data."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class PrimaryInertia:
    """CVT-owned primary-pulley inertia data.

    ``fixed_rotating_hardware_inertia`` covers CVT hardware rigidly attached to
    the primary shaft. ``movable_sheave_rotational_inertia`` is separate so a
    primary-mounted relative-rotation coupling can consume the movable member's
    inertia in the same way as a secondary helix. Engine/flywheel/coupler
    inertia belongs to the selected primary shaft boundary.
    """

    fixed_rotating_hardware_inertia: float
    movable_sheave_rotational_inertia: float
    moving_sheave_mass: float

    def __post_init__(self) -> None:
        for name, value in (
            (
                "fixed_rotating_hardware_inertia",
                self.fixed_rotating_hardware_inertia,
            ),
            (
                "movable_sheave_rotational_inertia",
                self.movable_sheave_rotational_inertia,
            ),
            ("moving_sheave_mass", self.moving_sheave_mass),
        ):
            _require_nonnegative(name, value)

    @property
    def absolute_rotation_inertia(self) -> float:
        """Return fixed-side plus movable-sheave primary inertia."""

        return (
            self.fixed_rotating_hardware_inertia
            + self.movable_sheave_rotational_inertia
        )


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
