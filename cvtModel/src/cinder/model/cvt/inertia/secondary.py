"""CVT-core output-pulley inertia data."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class SecondaryInertia:
    """CVT-owned output-pulley inertia data.

    ``fixed_rotating_hardware_inertia`` covers only CVT components rigidly
    attached directly to the secondary shaft. Gearbox, wheel, vehicle, dyno,
    sled, or other downstream inertia belongs to the selected output boundary
    and is added at runtime. The movable sheave remains separate because it has
    both absolute pulley rotation and relative helix rotation.
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
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")

    @property
    def fixed_rotational_inertia(self) -> float:
        """Compatibility alias for existing callers."""

        return self.fixed_rotating_hardware_inertia


@dataclass(frozen=True, slots=True)
class SecondaryFixedInertia:
    """Resolved constant output-pulley inertia owned by the CVT core."""

    fixed_rotating_hardware_inertia: float

    @property
    def total(self) -> float:
        return self.fixed_rotating_hardware_inertia

    @property
    def output_fixed_rotational_inertia(self) -> float:
        """Compatibility alias for existing callers."""

        return self.fixed_rotating_hardware_inertia


@dataclass(frozen=True, slots=True)
class ResolvedSecondaryInertia:
    """Output-pulley rotational constants supplied by the CVT core."""

    fixed_side: SecondaryFixedInertia
    movable_sheave_rotational_inertia: float

    @property
    def absolute_rotation_inertia(self) -> float:
        """Return CVT-core fixed-side plus movable-sheave inertia."""

        return self.fixed_side.total + self.movable_sheave_rotational_inertia


def resolve_secondary_inertia(
    *, secondary: SecondaryInertia
) -> ResolvedSecondaryInertia:
    """Resolve constant output-pulley inertia owned by the CVT assembly."""

    return ResolvedSecondaryInertia(
        fixed_side=SecondaryFixedInertia(
            fixed_rotating_hardware_inertia=secondary.fixed_rotating_hardware_inertia,
        ),
        movable_sheave_rotational_inertia=secondary.movable_sheave_rotational_inertia,
    )
