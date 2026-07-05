"""Individual axial-translation inertia data evaluated at one shift state."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


class AxialCoordinate(Protocol):
    """Minimum geometry data for one physical axial coordinate ``x(s)``."""

    d_value_ds: float
    d2_value_ds2: float


@dataclass(frozen=True, slots=True)
class AxialTranslationInertia:
    """One literal translating mass and its current coordinate mapping.

    For a physical axial coordinate ``x(s)``, the local inertial force is

        m x_ddot = m x'(s) s_ddot + m x''(s) s_dot^2.

    The local terms belong in a physical component balance. ``reflected_mass``
    and ``generalized_curvature_coefficient`` are exposed separately for any
    later generalized-coordinate row; they are not silently substituted into a
    pulley-local force balance.
    """

    mass: float
    d_coordinate_ds: float
    d2_coordinate_ds2: float

    def __post_init__(self) -> None:
        _require_nonnegative("mass", self.mass)
        _require_finite("d_coordinate_ds", self.d_coordinate_ds)
        _require_finite("d2_coordinate_ds2", self.d2_coordinate_ds2)

    @property
    def local_shift_acceleration_gain(self) -> float:
        """Return the ``s_ddot`` coefficient in ``m x_ddot``."""

        return self.mass * self.d_coordinate_ds

    def local_known_inertial_force(self, *, shift_speed: float) -> float:
        """Return the known ``m x''(s) s_dot^2`` term in ``m x_ddot``."""

        _require_finite("shift_speed", shift_speed)
        return self.mass * self.d2_coordinate_ds2 * shift_speed**2

    @property
    def reflected_mass(self) -> float:
        """Return ``m [x'(s)]^2`` for a later generalized shift row."""

        return self.mass * self.d_coordinate_ds**2

    @property
    def generalized_curvature_coefficient(self) -> float:
        """Return ``m x'(s) x''(s)`` for a later generalized shift row."""

        return self.mass * self.d_coordinate_ds * self.d2_coordinate_ds2


@dataclass(frozen=True, slots=True)
class AxialTranslationInertias:
    """Current individual axial inertias for primary, secondary, and belt.

    ``primary`` and ``secondary`` feed their respective physical pulley axial
    rows directly. ``belt`` remains explicit so a later belt axial-force model
    can use the same geometry-owned representative coordinate without hiding
    that mass inside either pulley row.
    """

    primary: AxialTranslationInertia
    secondary: AxialTranslationInertia
    belt: AxialTranslationInertia

    @property
    def generalized_mass(self) -> float:
        """Return the sum of individual reflected masses, if needed later."""

        return (
            self.primary.reflected_mass
            + self.secondary.reflected_mass
            + self.belt.reflected_mass
        )

    @property
    def generalized_curvature_coefficient(self) -> float:
        """Return the sum of individual generalized curvature coefficients."""

        return (
            self.primary.generalized_curvature_coefficient
            + self.secondary.generalized_curvature_coefficient
            + self.belt.generalized_curvature_coefficient
        )


@dataclass(frozen=True, slots=True)
class AxialTranslationMasses:
    """Fixed physical masses participating in the present axial-motion model."""

    primary_moving_sheave_mass: float
    secondary_moving_sheave_mass: float
    belt_mass: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_moving_sheave_mass", self.primary_moving_sheave_mass),
            ("secondary_moving_sheave_mass", self.secondary_moving_sheave_mass),
            ("belt_mass", self.belt_mass),
        ):
            _require_nonnegative(name, value)

    def evaluate(
        self,
        *,
        primary_axial_coordinate: AxialCoordinate,
        secondary_axial_coordinate: AxialCoordinate,
        belt_axial_coordinate: AxialCoordinate,
    ) -> AxialTranslationInertias:
        """Resolve each literal axial inertia at the current geometry state."""

        return AxialTranslationInertias(
            primary=AxialTranslationInertia(
                mass=self.primary_moving_sheave_mass,
                d_coordinate_ds=primary_axial_coordinate.d_value_ds,
                d2_coordinate_ds2=primary_axial_coordinate.d2_value_ds2,
            ),
            secondary=AxialTranslationInertia(
                mass=self.secondary_moving_sheave_mass,
                d_coordinate_ds=secondary_axial_coordinate.d_value_ds,
                d2_coordinate_ds2=secondary_axial_coordinate.d2_value_ds2,
            ),
            belt=AxialTranslationInertia(
                mass=self.belt_mass,
                d_coordinate_ds=belt_axial_coordinate.d_value_ds,
                d2_coordinate_ds2=belt_axial_coordinate.d2_value_ds2,
            ),
        )


def resolve_axial_translation_masses(
    *,
    primary_moving_sheave_mass: float,
    secondary_moving_sheave_mass: float,
    belt_mass: float,
) -> AxialTranslationMasses:
    """Store physical masses for later live-geometry axial-inertia evaluation."""

    return AxialTranslationMasses(
        primary_moving_sheave_mass=primary_moving_sheave_mass,
        secondary_moving_sheave_mass=secondary_moving_sheave_mass,
        belt_mass=belt_mass,
    )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
