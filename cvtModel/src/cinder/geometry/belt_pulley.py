# cinder/geometry/belt_pulley.py

from __future__ import annotations

from math import pi, sqrt, tan

from .belt_length import (
    solve_secondary_outer_radius,
    wrap_angles,
)
from .position import GeometryPosition, RadiusAtShift
from .spec import BeltPulleyGeometrySpec


class BeltPulleyGeometry:
    """
    Evaluate fixed belt-pulley geometry at a current shift position.

    Each evaluate(shift) call performs exactly one secondary-radius root
    solve, using the cached reachable endpoint radii as its bracket.
    """

    def __init__(self, spec: BeltPulleyGeometrySpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> BeltPulleyGeometrySpec:
        return self._spec

    def evaluate(self, shift: float) -> GeometryPosition:
        self._validate_shift(shift)

        (
            primary_outer_radius,
            d_primary_radius_ds,
            d2_primary_radius_ds2,
        ) = self._primary_outer_radius_kinematics(shift)

        secondary_outer_radius = solve_secondary_outer_radius(
            belt_length=self._spec.belt_outer_length,
            center_distance=self._spec.center_distance,
            primary_outer_radius=primary_outer_radius,
            lower_bound=self._spec.secondary_outer_radius_at_max_shift,
            upper_bound=self._spec.secondary_outer_radius_at_zero_shift,
        )

        primary_wrap_angle, secondary_wrap_angle = wrap_angles(
            center_distance=self._spec.center_distance,
            primary_outer_radius=primary_outer_radius,
            secondary_outer_radius=secondary_outer_radius,
        )

        (
            d_secondary_radius_ds,
            d2_secondary_radius_ds2,
        ) = self._secondary_outer_radius_derivatives(
            primary_wrap_angle=primary_wrap_angle,
            secondary_wrap_angle=secondary_wrap_angle,
            primary_outer_radius=primary_outer_radius,
            secondary_outer_radius=secondary_outer_radius,
            d_primary_radius_ds=d_primary_radius_ds,
            d2_primary_radius_ds2=d2_primary_radius_ds2,
        )

        return GeometryPosition(
            shift=shift,
            primary=self._radius_at_shift(
                outer_radius=primary_outer_radius,
                d_radius_ds=d_primary_radius_ds,
                d2_radius_ds2=d2_primary_radius_ds2,
            ),
            secondary=self._radius_at_shift(
                outer_radius=secondary_outer_radius,
                d_radius_ds=d_secondary_radius_ds,
                d2_radius_ds2=d2_secondary_radius_ds2,
            ),
            primary_wrap_angle=primary_wrap_angle,
            secondary_wrap_angle=secondary_wrap_angle,
        )

    def _primary_outer_radius_kinematics(
        self,
        shift: float,
    ) -> tuple[float, float, float]:
        """
        Return r_p,out, dr_p,out/ds, and d²r_p,out/ds².
        """

        if shift <= self._spec.deadzone_shift:
            return (
                self._spec.primary_outer_radius_at_zero_shift,
                0.0,
                0.0,
            )

        radius_slope = 1.0 / (
            2.0 * tan(self._spec.sheave_half_angle)
        )

        return (
            self._spec.primary_outer_radius_at_zero_shift
            + radius_slope * (shift - self._spec.deadzone_shift),
            radius_slope,
            0.0,
        )

    def _secondary_outer_radius_derivatives(
        self,
        *,
        primary_wrap_angle: float,
        secondary_wrap_angle: float,
        primary_outer_radius: float,
        secondary_outer_radius: float,
        d_primary_radius_ds: float,
        d2_primary_radius_ds2: float,
    ) -> tuple[float, float]:
        """
        Return dr_s,out/ds and d²r_s,out/ds² from the differentiated
        constant outer-belt-length constraint.
        """

        radius_slope_ratio = (
            primary_wrap_angle / secondary_wrap_angle
        )

        d_secondary_radius_ds = (
            -radius_slope_ratio * d_primary_radius_ds
        )

        straight_span_length = sqrt(
            self._spec.center_distance**2
            - (secondary_outer_radius - primary_outer_radius) ** 2
        )

        d2_secondary_radius_ds2 = (
            -radius_slope_ratio * d2_primary_radius_ds2
            - (
                8.0 * pi**2 * d_primary_radius_ds**2
                / (
                    secondary_wrap_angle**3
                    * straight_span_length
                )
            )
        )

        return (
            d_secondary_radius_ds,
            d2_secondary_radius_ds2,
        )

    def _radius_at_shift(
        self,
        *,
        outer_radius: float,
        d_radius_ds: float,
        d2_radius_ds2: float,
    ) -> RadiusAtShift:
        """
        Derive effective and center-of-mass radii from one outer radius.

        Constant belt-depth offsets do not change dr/ds or d²r/ds².
        """

        return RadiusAtShift(
            effective=(
                outer_radius
                - self._spec.belt.cord_depth_from_outer
            ),
            outer=outer_radius,
            center_of_mass=(
                outer_radius
                - self._spec.belt.center_of_mass_depth_from_outer
            ),
            d_effective_ds=d_radius_ds,
            d2_effective_ds2=d2_radius_ds2,
        )

    def _validate_shift(self, shift: float) -> None:
        if not 0.0 <= shift <= self._spec.max_shift:
            raise ValueError(
                f"shift={shift} is outside "
                f"[0, {self._spec.max_shift}]."
            )
