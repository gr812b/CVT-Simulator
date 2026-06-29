"""Physical translation masses and their current shift-coordinate inertia."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


class AxialCoordinate(Protocol):
    """Minimum geometry data for one physical axial coordinate x(s)."""

    d_value_ds: float
    d2_value_ds2: float


@dataclass(frozen=True, slots=True)
class ShiftTranslationMasses:
    """
    Fixed physical masses participating in coordinated axial motion.

    These are physical inputs, not already-reflected generalized masses.
    Their coordinate slopes and curvatures come from ``GeometryPosition``
    at each RHS evaluation.

    The movable secondary sheave's rotational helix coupling is excluded
    here. It belongs to the later secondary helix dynamics coupling, where
    its rotational inertia ``I_M`` enters both the secondary-rotation and
    generalized-shift rows exactly once.
    """

    primary_moving_sheave_mass: float
    secondary_moving_sheave_mass: float
    belt_mass: float

    def __post_init__(self) -> None:
        for name, value in (
            (
                "primary_moving_sheave_mass",
                self.primary_moving_sheave_mass,
            ),
            (
                "secondary_moving_sheave_mass",
                self.secondary_moving_sheave_mass,
            ),
            ("belt_mass", self.belt_mass),
        ):
            _require_nonnegative(name, value)

    def evaluate(
        self,
        *,
        primary_axial_coordinate: AxialCoordinate,
        secondary_axial_coordinate: AxialCoordinate,
        belt_axial_coordinate: AxialCoordinate,
    ) -> "ShiftTranslationInertia":
        """
        Refer literal axial translation to the present global shift s.

            M_trans(s) = sum_i m_i [x_i'(s)]^2

            C_trans(s) = sum_i m_i x_i'(s) x_i''(s)

        The eventual generalized shift row is:

            M_trans s_ddot + C_trans s_dot^2 = Q_s.
        """

        return ShiftTranslationInertia(
            primary_moving_sheave_mass=(self.primary_moving_sheave_mass),
            secondary_moving_sheave_mass=(self.secondary_moving_sheave_mass),
            belt_mass=self.belt_mass,
            primary_axial_coordinate_slope=(primary_axial_coordinate.d_value_ds),
            primary_axial_coordinate_curvature=(primary_axial_coordinate.d2_value_ds2),
            secondary_axial_coordinate_slope=(secondary_axial_coordinate.d_value_ds),
            secondary_axial_coordinate_curvature=(
                secondary_axial_coordinate.d2_value_ds2
            ),
            belt_axial_coordinate_slope=(belt_axial_coordinate.d_value_ds),
            belt_axial_coordinate_curvature=(belt_axial_coordinate.d2_value_ds2),
        )


@dataclass(frozen=True, slots=True)
class ShiftTranslationInertia:
    """Current literal axial translation inertia in the global s coordinate."""

    primary_moving_sheave_mass: float
    secondary_moving_sheave_mass: float
    belt_mass: float

    primary_axial_coordinate_slope: float
    primary_axial_coordinate_curvature: float
    secondary_axial_coordinate_slope: float
    secondary_axial_coordinate_curvature: float
    belt_axial_coordinate_slope: float
    belt_axial_coordinate_curvature: float

    @property
    def primary_moving_sheave_contribution(self) -> float:
        return self.primary_moving_sheave_mass * self.primary_axial_coordinate_slope**2

    @property
    def secondary_moving_sheave_contribution(self) -> float:
        return (
            self.secondary_moving_sheave_mass * self.secondary_axial_coordinate_slope**2
        )

    @property
    def belt_contribution(self) -> float:
        return self.belt_mass * self.belt_axial_coordinate_slope**2

    @property
    def mass(self) -> float:
        """Return M_trans(s)."""

        return (
            self.primary_moving_sheave_contribution
            + self.secondary_moving_sheave_contribution
            + self.belt_contribution
        )

    @property
    def coordinate_curvature_coefficient(self) -> float:
        """Return C_trans(s), the coefficient multiplying s_dot squared."""

        return (
            self.primary_moving_sheave_mass
            * self.primary_axial_coordinate_slope
            * self.primary_axial_coordinate_curvature
            + self.secondary_moving_sheave_mass
            * self.secondary_axial_coordinate_slope
            * self.secondary_axial_coordinate_curvature
            + self.belt_mass
            * self.belt_axial_coordinate_slope
            * self.belt_axial_coordinate_curvature
        )


def resolve_shift_translation_masses(
    *,
    primary_moving_sheave_mass: float,
    secondary_moving_sheave_mass: float,
    belt_mass: float,
) -> ShiftTranslationMasses:
    """Store fixed physical masses for later live-geometry evaluation."""

    return ShiftTranslationMasses(
        primary_moving_sheave_mass=primary_moving_sheave_mass,
        secondary_moving_sheave_mass=secondary_moving_sheave_mass,
        belt_mass=belt_mass,
    )


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
