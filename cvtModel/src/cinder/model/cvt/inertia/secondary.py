"""CVT-core output-pulley inertia data."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class SecondaryInertia:
    """Fixed CVT-side output-pulley inertia data.

    ``fixed_rotational_inertia`` covers components rigidly attached directly to
    the output pulley shaft. ``gearbox_input_rotational_inertia`` covers any
    inertia on the CVT-side input of a rigid reduction. The movable sheave is
    separate because it has both absolute pulley rotation and relative helix
    rotation.

    Wheel and vehicle inertia belong to the selected output boundary and are
    reflected at runtime by that boundary.
    """

    fixed_rotational_inertia: float
    gearbox_input_rotational_inertia: float
    movable_sheave_rotational_inertia: float
    moving_sheave_mass: float

    def __post_init__(self) -> None:
        for name, value in (
            ("fixed_rotational_inertia", self.fixed_rotational_inertia),
            ("gearbox_input_rotational_inertia", self.gearbox_input_rotational_inertia),
            (
                "movable_sheave_rotational_inertia",
                self.movable_sheave_rotational_inertia,
            ),
            ("moving_sheave_mass", self.moving_sheave_mass),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True, slots=True)
class SecondaryFixedInertia:
    """Resolved constant output-pulley inertia owned by the CVT core."""

    output_fixed_rotational_inertia: float
    gearbox_input_rotational_inertia: float

    @property
    def total(self) -> float:
        return (
            self.output_fixed_rotational_inertia + self.gearbox_input_rotational_inertia
        )


@dataclass(frozen=True, slots=True)
class ResolvedSecondaryInertia:
    """Output-pulley rotational constants supplied by the CVT core."""

    fixed_side: SecondaryFixedInertia
    movable_sheave_rotational_inertia: float

    @property
    def absolute_rotation_inertia(self) -> float:
        """Return fixed-side plus movable-sheave absolute rotation inertia."""

        return self.fixed_side.total + self.movable_sheave_rotational_inertia


def resolve_secondary_inertia(
    *, secondary: SecondaryInertia
) -> ResolvedSecondaryInertia:
    """Resolve constant output-pulley inertia owned by the CVT assembly."""

    return ResolvedSecondaryInertia(
        fixed_side=SecondaryFixedInertia(
            output_fixed_rotational_inertia=secondary.fixed_rotational_inertia,
            gearbox_input_rotational_inertia=secondary.gearbox_input_rotational_inertia,
        ),
        movable_sheave_rotational_inertia=secondary.movable_sheave_rotational_inertia,
    )
