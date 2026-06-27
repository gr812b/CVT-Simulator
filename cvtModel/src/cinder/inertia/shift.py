"""Literal axial translation mass in the global shift coordinate."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.geometry.position import GeometryPosition


@dataclass(frozen=True, slots=True)
class ShiftTranslationMass:
    """
    Fixed physical masses that translate through the shift coordinate.

    The corresponding generalized mass is state-dependent because the
    secondary and belt coordinate slopes come from current geometry.
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
            if not isfinite(value) or value < 0.0:
                raise ValueError(
                    f"{name} must be finite and non-negative."
                )

    def at_position(
        self,
        *,
        position: GeometryPosition,
    ) -> ShiftTranslationMassAtPosition:
        """
        Evaluate literal translating mass from current geometry.

            M_trans(s) =
                m_p (dx_p/ds)^2
                + m_s (dx_s/ds)^2
                + m_b (dx_b/ds)^2.

        The associated known quadratic-speed coefficient is

            C_trans(s) =
                m_p (dx_p/ds)(d²x_p/ds²)
                + m_s (dx_s/ds)(d²x_s/ds²)
                + m_b (dx_b/ds)(d²x_b/ds²),

        so the translation contribution to the shift equation is

            M_trans(s) s_ddot + C_trans(s) s_dot².

        The movable secondary sheave's *rotational* helix coupling is not
        included here; it remains in the secondary rotational and clamping
        relations.
        """

        return ShiftTranslationMassAtPosition(
            shift=position.shift,
            primary_moving_sheave_mass=(
                self.primary_moving_sheave_mass
            ),
            secondary_moving_sheave_mass=(
                self.secondary_moving_sheave_mass
            ),
            belt_mass=self.belt_mass,
            primary_axial_coordinate_slope=(
                position.primary_axial_coordinate.d_value_ds
            ),
            secondary_axial_coordinate_slope=(
                position.secondary_axial_coordinate.d_value_ds
            ),
            belt_axial_coordinate_slope=(
                position.belt_axial_coordinate.d_value_ds
            ),
            primary_axial_coordinate_curvature=(
                position.primary_axial_coordinate.d2_value_ds2
            ),
            secondary_axial_coordinate_curvature=(
                position.secondary_axial_coordinate.d2_value_ds2
            ),
            belt_axial_coordinate_curvature=(
                position.belt_axial_coordinate.d2_value_ds2
            ),
        )


@dataclass(frozen=True, slots=True)
class ShiftTranslationMassAtPosition:
    """Breakdown of literal translating mass at one global shift position."""

    shift: float

    primary_moving_sheave_mass: float
    secondary_moving_sheave_mass: float
    belt_mass: float

    primary_axial_coordinate_slope: float
    secondary_axial_coordinate_slope: float
    belt_axial_coordinate_slope: float

    primary_axial_coordinate_curvature: float
    secondary_axial_coordinate_curvature: float
    belt_axial_coordinate_curvature: float

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
        return (
            self.belt_mass
            * self.belt_axial_coordinate_slope**2
        )

    @property
    def total(self) -> float:
        """Return M_trans(s), the coefficient of s_ddot."""

        return (
            self.primary_moving_sheave_contribution
            + self.secondary_moving_sheave_contribution
            + self.belt_contribution
        )

    @property
    def primary_quadratic_speed_coefficient(self) -> float:
        return (
            self.primary_moving_sheave_mass
            * self.primary_axial_coordinate_slope
            * self.primary_axial_coordinate_curvature
        )

    @property
    def secondary_quadratic_speed_coefficient(self) -> float:
        return (
            self.secondary_moving_sheave_mass
            * self.secondary_axial_coordinate_slope
            * self.secondary_axial_coordinate_curvature
        )

    @property
    def belt_quadratic_speed_coefficient(self) -> float:
        return (
            self.belt_mass
            * self.belt_axial_coordinate_slope
            * self.belt_axial_coordinate_curvature
        )

    @property
    def quadratic_speed_coefficient(self) -> float:
        """Return C_trans(s), the coefficient of s_dot²."""

        return (
            self.primary_quadratic_speed_coefficient
            + self.secondary_quadratic_speed_coefficient
            + self.belt_quadratic_speed_coefficient
        )


def resolve_shift_translation_mass(
    *,
    primary_moving_sheave_mass: float,
    secondary_moving_sheave_mass: float,
    belt_mass: float,
) -> ShiftTranslationMass:
    """Resolve fixed physical masses used by shift translation."""

    return ShiftTranslationMass(
        primary_moving_sheave_mass=primary_moving_sheave_mass,
        secondary_moving_sheave_mass=secondary_moving_sheave_mass,
        belt_mass=belt_mass,
    )
