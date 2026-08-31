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
    """Current individual axial inertias retained by the shift model.

    Only the primary and secondary movable members participate in axial shift
    inertia. Belt mass belongs to the belt-transport equation and is
    intentionally absent here.
    """

    primary: AxialTranslationInertia
    secondary: AxialTranslationInertia

    @property
    def generalized_mass(self) -> float:
        """Return the retained translational contribution to M_ss."""

        return self.primary.reflected_mass + self.secondary.reflected_mass

    @property
    def generalized_curvature_coefficient(self) -> float:
        """Return the retained translational curvature coefficient."""

        return (
            self.primary.generalized_curvature_coefficient
            + self.secondary.generalized_curvature_coefficient
        )


@dataclass(frozen=True, slots=True)
class AxialTranslationMasses:
    """Fixed physical masses participating in the retained shift inertia."""

    primary_moving_sheave_mass: float
    secondary_moving_sheave_mass: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_moving_sheave_mass", self.primary_moving_sheave_mass),
            ("secondary_moving_sheave_mass", self.secondary_moving_sheave_mass),
        ):
            _require_nonnegative(name, value)

    def evaluate(
        self,
        *,
        primary_axial_coordinate: AxialCoordinate,
        secondary_axial_coordinate: AxialCoordinate,
    ) -> AxialTranslationInertias:
        """Resolve the two literal axial inertias retained by the model."""

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
        )


def resolve_axial_translation_masses(
    *,
    primary_moving_sheave_mass: float,
    secondary_moving_sheave_mass: float,
) -> AxialTranslationMasses:
    """Store the physical masses retained in shift translation inertia."""

    return AxialTranslationMasses(
        primary_moving_sheave_mass=primary_moving_sheave_mass,
        secondary_moving_sheave_mass=secondary_moving_sheave_mass,
    )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
