"""Literal axial translation mass for the global shift coordinate."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ConstantShiftKinematics:
    """
    Constant coordinate slopes for the present shift-mass approximation.

    Each field is the physical axial displacement of that body per unit global
    shift coordinate s. The signs retain the selected coordinate
    convention; the inertia contribution uses their squares.

    The current model is:

    x_p' = 1, x_s' = -1, and x_b' = 0.5.
    """

    primary_axial_coordinate_slope: float = 1.0
    secondary_axial_coordinate_slope: float = -1.0
    belt_axial_coordinate_slope: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (
            (
                "primary_axial_coordinate_slope",
                self.primary_axial_coordinate_slope,
            ),
            (
                "secondary_axial_coordinate_slope",
                self.secondary_axial_coordinate_slope,
            ),
            (
                "belt_axial_coordinate_slope",
                self.belt_axial_coordinate_slope,
            ),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")


@dataclass(frozen=True, slots=True)
class ShiftTranslationMass:
    """
    Breakdown of literal translating mass referred to the global shift coordinate.

    This intentionally includes only physical axial translation. The movable
    secondary sheave's rotational helix coupling remains in the secondary
    rotational and clamping relations.
    """

    primary_moving_sheave_mass: float
    secondary_moving_sheave_mass: float
    belt_mass: float

    primary_axial_coordinate_slope: float
    secondary_axial_coordinate_slope: float
    belt_axial_coordinate_slope: float

    @property
    def primary_moving_sheave_contribution(self) -> float:
        return (
            self.primary_moving_sheave_mass
            * self.primary_axial_coordinate_slope**2
        )

    @property
    def secondary_moving_sheave_contribution(self) -> float:
        return (
            self.secondary_moving_sheave_mass
            * self.secondary_axial_coordinate_slope**2
        )

    @property
    def belt_contribution(self) -> float:
        return self.belt_mass * self.belt_axial_coordinate_slope**2

    @property
    def total(self) -> float:
        """
        Return m_eq for the shift equation:

        m_eq = m_p,m (x_p')^2 + m_s,m (x_s')^2 + m_b (x_b')^2.
        """

        return (
            self.primary_moving_sheave_contribution
            + self.secondary_moving_sheave_contribution
            + self.belt_contribution
        )


def resolve_shift_translation_mass(
    *,
    primary_moving_sheave_mass: float,
    secondary_moving_sheave_mass: float,
    belt_mass: float,
    kinematics: ConstantShiftKinematics,
) -> ShiftTranslationMass:
    """Resolve the constant literal-translation mass for the current model."""

    for name, value in (
        ("primary_moving_sheave_mass", primary_moving_sheave_mass),
        ("secondary_moving_sheave_mass", secondary_moving_sheave_mass),
        ("belt_mass", belt_mass),
    ):
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative.")

    return ShiftTranslationMass(
        primary_moving_sheave_mass=primary_moving_sheave_mass,
        secondary_moving_sheave_mass=secondary_moving_sheave_mass,
        belt_mass=belt_mass,
        primary_axial_coordinate_slope=(
            kinematics.primary_axial_coordinate_slope
        ),
        secondary_axial_coordinate_slope=(
            kinematics.secondary_axial_coordinate_slope
        ),
        belt_axial_coordinate_slope=kinematics.belt_axial_coordinate_slope,
    )
