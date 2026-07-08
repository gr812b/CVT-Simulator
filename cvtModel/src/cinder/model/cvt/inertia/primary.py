"""Primary-side CVT-core inertia data."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class PrimaryInertia:
    """
    CVT-owned primary-side physical properties.

    ``rotating_hardware_inertia`` includes only CVT components rotating
    directly with the primary shaft, including the primary movable sheave's
    spin inertia. Engine/flywheel/coupler inertia belongs to the selected
    input boundary and is added at runtime. Axial translation is represented
    separately by ``moving_sheave_mass`` in the shift equation.
    """

    rotating_hardware_inertia: float
    moving_sheave_mass: float

    def __post_init__(self) -> None:
        _require_nonnegative(
            "rotating_hardware_inertia",
            self.rotating_hardware_inertia,
        )
        _require_nonnegative("moving_sheave_mass", self.moving_sheave_mass)

    @property
    def rotational_inertia(self) -> float:
        """Return CVT-owned primary hardware inertia only."""

        return self.rotating_hardware_inertia

    @property
    def cvt_rotational_inertia(self) -> float:
        """Compatibility alias for existing callers."""

        return self.rotating_hardware_inertia


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
