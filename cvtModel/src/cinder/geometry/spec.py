# cinder/geometry/spec.py

from __future__ import annotations

from dataclasses import dataclass, field
from math import inf, nextafter, pi, tan

from .belt_length import (
    solve_center_distance,
    solve_secondary_outer_radius,
)


@dataclass(frozen=True, slots=True)
class BeltSectionSpec:
    """
    Fixed trapezoidal belt cross-section.

    All depths are measured inward from the belt outer radial surface.
    """

    height: float
    outer_width: float
    inner_width: float
    cord_depth_from_outer: float

    center_of_mass_depth_from_outer: float = field(init=False)

    def __post_init__(self) -> None:
        if self.height <= 0.0:
            raise ValueError("height must be positive.")

        if self.outer_width <= 0.0:
            raise ValueError("outer_width must be positive.")

        if self.inner_width <= 0.0:
            raise ValueError("inner_width must be positive.")

        if not 0.0 <= self.cord_depth_from_outer <= self.height:
            raise ValueError(
                "cord_depth_from_outer must lie within the belt height."
            )

        center_of_mass_depth = (
            self.height
            * (self.outer_width + 2.0 * self.inner_width)
            / (3.0 * (self.outer_width + self.inner_width))
        )

        object.__setattr__(
            self,
            "center_of_mass_depth_from_outer",
            center_of_mass_depth,
        )


@dataclass(frozen=True, slots=True)
class BeltPulleyGeometrySpec:
    """
    Fixed resolved geometry for one belt-pulley CVT.

    Reference radii and belt length are measured at the belt outer surface
    in the s = 0 configuration. Effective radii, C2C, and the secondary
    outer radius at s = max_shift are resolved once during construction.
    """

    belt: BeltSectionSpec

    belt_outer_length: float

    primary_outer_radius_at_zero_shift: float
    secondary_outer_radius_at_zero_shift: float

    sheave_half_angle: float
    deadzone_shift: float
    max_shift: float

    center_distance: float = field(init=False)

    primary_effective_radius_at_zero_shift: float = field(init=False)
    secondary_effective_radius_at_zero_shift: float = field(init=False)

    primary_outer_radius_at_max_shift: float = field(init=False)
    secondary_outer_radius_at_max_shift: float = field(init=False)

    def __post_init__(self) -> None:
        if self.belt_outer_length <= 0.0:
            raise ValueError("belt_outer_length must be positive.")

        if self.primary_outer_radius_at_zero_shift <= 0.0:
            raise ValueError(
                "primary_outer_radius_at_zero_shift must be positive."
            )

        if self.secondary_outer_radius_at_zero_shift <= 0.0:
            raise ValueError(
                "secondary_outer_radius_at_zero_shift must be positive."
            )

        if not 0.0 < self.sheave_half_angle < pi / 2.0:
            raise ValueError(
                "sheave_half_angle must lie between 0 and pi / 2."
            )

        if self.deadzone_shift < 0.0:
            raise ValueError("deadzone_shift cannot be negative.")

        if self.max_shift < self.deadzone_shift:
            raise ValueError(
                "max_shift must be greater than or equal to deadzone_shift."
            )

        primary_effective_radius = (
            self.primary_outer_radius_at_zero_shift
            - self.belt.cord_depth_from_outer
        )
        secondary_effective_radius = (
            self.secondary_outer_radius_at_zero_shift
            - self.belt.cord_depth_from_outer
        )

        if primary_effective_radius <= 0.0:
            raise ValueError("primary outer radius must exceed cord depth.")

        if secondary_effective_radius <= 0.0:
            raise ValueError("secondary outer radius must exceed cord depth.")

        center_distance = solve_center_distance(
            belt_length=self.belt_outer_length,
            primary_outer_radius=self.primary_outer_radius_at_zero_shift,
            secondary_outer_radius=self.secondary_outer_radius_at_zero_shift,
        )

        active_shift_at_max = self.max_shift - self.deadzone_shift
        primary_outer_radius_at_max_shift = (
            self.primary_outer_radius_at_zero_shift
            + active_shift_at_max / (2.0 * tan(self.sheave_half_angle))
        )

        # One broad setup solve establishes the lower endpoint used by all
        # later runtime secondary-radius solves.
        #
        # r_s <= C - r_p prevents outer belt envelopes from overlapping.
        # r_s <= L / pi - r_p follows from L >= pi(r_p + r_s).
        setup_upper_bound = min(
            center_distance - primary_outer_radius_at_max_shift,
            self.belt_outer_length / pi - primary_outer_radius_at_max_shift,
        )

        if setup_upper_bound <= 0.0:
            raise ValueError(
                "max_shift drives the primary radius beyond the reachable "
                "belt-pulley geometry."
            )

        # Zero is the physical limiting lower bound. The solver requires a
        # strictly positive radius, so use the nearest representable float
        # above zero rather than an arbitrary engineering offset.
        setup_lower_bound = nextafter(0.0, inf)

        secondary_outer_radius_at_max_shift = solve_secondary_outer_radius(
            belt_length=self.belt_outer_length,
            center_distance=center_distance,
            primary_outer_radius=primary_outer_radius_at_max_shift,
            lower_bound=setup_lower_bound,
            upper_bound=setup_upper_bound,
        )

        object.__setattr__(
            self,
            "primary_effective_radius_at_zero_shift",
            primary_effective_radius,
        )
        object.__setattr__(
            self,
            "secondary_effective_radius_at_zero_shift",
            secondary_effective_radius,
        )
        object.__setattr__(self, "center_distance", center_distance)
        object.__setattr__(
            self,
            "primary_outer_radius_at_max_shift",
            primary_outer_radius_at_max_shift,
        )
        object.__setattr__(
            self,
            "secondary_outer_radius_at_max_shift",
            secondary_outer_radius_at_max_shift,
        )
