"""Primary-side physical inertia data."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class PrimaryInertia:
    """
    Fixed primary-side physical properties.

    ``cvt_rotational_inertia`` includes every CVT component rotating directly
    with the primary shaft, including the primary movable sheave's spin
    inertia. Its axial translation is represented separately by
    ``moving_sheave_mass`` in the shift equation.
    """

    engine_rotational_inertia: float
    cvt_rotational_inertia: float
    moving_sheave_mass: float

    def __post_init__(self) -> None:
        _require_nonnegative(
            "engine_rotational_inertia",
            self.engine_rotational_inertia,
        )
        _require_nonnegative(
            "cvt_rotational_inertia",
            self.cvt_rotational_inertia,
        )
        _require_nonnegative("moving_sheave_mass", self.moving_sheave_mass)

    @property
    def rotational_inertia(self) -> float:
        """Return I_p = engine inertia + primary-CVT inertia."""

        return self.engine_rotational_inertia + self.cvt_rotational_inertia


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
