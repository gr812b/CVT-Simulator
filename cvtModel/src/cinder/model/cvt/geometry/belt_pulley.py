"""Fixed-length belt-pulley geometry evaluated at one global shift state."""

from __future__ import annotations

from math import isfinite, pi, sqrt, tan
from typing import Final

from .belt_length import (
    solve_secondary_outer_radius,
    wrap_angles,
)
from .position import (
    AxialCoordinateAtShift,
    GeometryPosition,
    RadiusAtShift,
)
from .spec import BeltPulleyGeometrySpec

_SHIFT_DOMAIN_ABSOLUTE_TOLERANCE: Final[float] = 1.0e-12


class BeltPulleyGeometry:
    """
    Evaluate fixed belt-pulley geometry at one global shift coordinate.

    The global coordinate ``shift = s`` is the primary movable-sheave
    coordinate. The returned ``GeometryPosition`` also supplies the three
    physical axial coordinates used by local actuator laws and by shift
    translation inertia:

        x_p(s) = s

        x_s(s) = 2 tan(beta) [r_s,out(s) - r_s,out(0)]

        x_b(s) = 0,                         s <= s_deadzone
                = (s - s_deadzone) / 2,      s >  s_deadzone

    Positive local coordinates close their respective pulley. Thus an
    upshift has x_p > 0 and x_s < 0. The belt coordinate is a present
    lumped axial-motion approximation: the belt remains stationary during
    primary deadzone travel, then its representative axial motion is half
    of the active primary displacement. Replace this mapping later only
    when a distributed belt axial-motion model is introduced.

    Each ``evaluate(shift)`` call performs exactly one secondary-radius root
    solve, using cached reachable endpoint radii as its bracket.
    """

    def __init__(self, spec: BeltPulleyGeometrySpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> BeltPulleyGeometrySpec:
        return self._spec

    def evaluate(self, shift: float) -> GeometryPosition:
        """Evaluate geometry using the ordinary piecewise convention.

        At the deadzone/engaged boundary this retains the historical
        deadzone-side derivative.  Hybrid code that already knows which side
        of the topology boundary is active should call :meth:`evaluate_deadzone`
        or :meth:`evaluate_engaged` instead so the correct one-sided tangent is
        used at the exact same position.
        """

        return self._evaluate(shift, engaged_side_at_boundary=None)

    def evaluate_deadzone(self, shift: float) -> GeometryPosition:
        """Evaluate the deadzone-side geometry/tangent at ``shift``.

        In particular, at ``shift == deadzone_shift`` the primary/belt radius
        and belt-axial derivatives remain zero because belt contact has not yet
        been activated in the deadzone topology.
        """

        return self._evaluate(shift, engaged_side_at_boundary=False)

    def evaluate_engaged(self, shift: float) -> GeometryPosition:
        """Evaluate the engaged-side geometry/tangent at ``shift``.

        The geometry is position-continuous at ``deadzone_shift`` but its
        derivative is intentionally discontinuous.  Once engaged contact is
        active, the exact boundary must therefore use the right-hand tangent.
        """

        return self._evaluate(shift, engaged_side_at_boundary=True)

    def _evaluate(
        self,
        shift: float,
        *,
        engaged_side_at_boundary: bool | None,
    ) -> GeometryPosition:
        shift = self._coerce_shift_to_domain(shift)
        if engaged_side_at_boundary is not None:
            shift = self._coerce_shift_to_topology_side(
                shift, engaged_side_at_boundary=engaged_side_at_boundary
            )

        (
            primary_outer_radius,
            d_primary_radius_ds,
            d2_primary_radius_ds2,
        ) = self._primary_outer_radius_kinematics(
            shift,
            engaged_side_at_boundary=bool(engaged_side_at_boundary),
        )

        secondary_outer_radius = solve_secondary_outer_radius(
            belt_length=self._spec.belt_outer_length,
            center_distance=self._spec.center_distance,
            primary_outer_radius=primary_outer_radius,
            lower_bound=(self._spec.secondary_outer_radius_at_max_shift),
            upper_bound=(self._spec.secondary_outer_radius_at_zero_shift),
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
            primary_axial_coordinate=AxialCoordinateAtShift(
                value=shift,
                d_value_ds=1.0,
                d2_value_ds2=0.0,
            ),
            secondary_axial_coordinate=(
                self._secondary_axial_coordinate(
                    secondary_outer_radius=secondary_outer_radius,
                    d_secondary_radius_ds=d_secondary_radius_ds,
                    d2_secondary_radius_ds2=d2_secondary_radius_ds2,
                )
            ),
            belt_axial_coordinate=self._belt_axial_coordinate(
                shift,
                engaged_side_at_boundary=bool(engaged_side_at_boundary),
            ),
        )

    def secondary_opening_travel_at_shift(self, shift: float) -> float:
        """Return positive secondary opening travel at one shift coordinate."""

        return -self.evaluate(shift).secondary_axial_coordinate.value

    @property
    def secondary_opening_travel_at_max_shift(self) -> float:
        """Return positive secondary opening travel at the upper shift stop."""

        return self.secondary_opening_travel_at_shift(self._spec.max_shift)

    def _primary_outer_radius_kinematics(
        self,
        shift: float,
        *,
        engaged_side_at_boundary: bool = False,
    ) -> tuple[float, float, float]:
        """Return r_p,out, dr_p,out/ds, and d²r_p,out/ds²."""

        if shift < self._spec.deadzone_shift or (
            shift == self._spec.deadzone_shift and not engaged_side_at_boundary
        ):
            return (
                self._spec.primary_outer_radius_at_zero_shift,
                0.0,
                0.0,
            )

        radius_slope = 1.0 / (2.0 * tan(self._spec.sheave_half_angle))

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
        Return dr_s,out/ds and d²r_s,out/ds² from differentiated constant
        outer-belt-length closure.
        """

        radius_slope_ratio = primary_wrap_angle / secondary_wrap_angle

        d_secondary_radius_ds = -radius_slope_ratio * d_primary_radius_ds

        straight_span_length = sqrt(
            self._spec.center_distance**2
            - (secondary_outer_radius - primary_outer_radius) ** 2
        )

        d2_secondary_radius_ds2 = -radius_slope_ratio * d2_primary_radius_ds2 - (
            8.0
            * pi**2
            * d_primary_radius_ds**2
            / (secondary_wrap_angle**3 * straight_span_length)
        )

        return d_secondary_radius_ds, d2_secondary_radius_ds2

    def _secondary_axial_coordinate(
        self,
        *,
        secondary_outer_radius: float,
        d_secondary_radius_ds: float,
        d2_secondary_radius_ds2: float,
    ) -> AxialCoordinateAtShift:
        """
        Map secondary belt radius into local actuator coordinate x_s.

        x_s = 0 at s = 0. Positive x_s closes the secondary, so x_s becomes
        negative as the primary shifts out and the secondary opens.
        """

        axial_distance_per_radius = 2.0 * tan(self._spec.sheave_half_angle)

        return AxialCoordinateAtShift(
            value=(
                axial_distance_per_radius
                * (
                    secondary_outer_radius
                    - self._spec.secondary_outer_radius_at_zero_shift
                )
            ),
            d_value_ds=(axial_distance_per_radius * d_secondary_radius_ds),
            d2_value_ds2=(axial_distance_per_radius * d2_secondary_radius_ds2),
        )

    def _belt_axial_coordinate(
        self,
        shift: float,
        *,
        engaged_side_at_boundary: bool = False,
    ) -> AxialCoordinateAtShift:
        """Return present lumped belt axial coordinate x_b(s)."""

        if shift < self._spec.deadzone_shift or (
            shift == self._spec.deadzone_shift and not engaged_side_at_boundary
        ):
            return AxialCoordinateAtShift(
                value=0.0,
                d_value_ds=0.0,
                d2_value_ds2=0.0,
            )

        return AxialCoordinateAtShift(
            value=(shift - self._spec.deadzone_shift) / 2.0,
            d_value_ds=0.5,
            d2_value_ds2=0.0,
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
            effective=(outer_radius - self._spec.belt.cord_depth_from_outer),
            outer=outer_radius,
            center_of_mass=(
                outer_radius - self._spec.belt.center_of_mass_depth_from_outer
            ),
            d_effective_ds=d_radius_ds,
            d2_effective_ds2=d2_radius_ds2,
            d_center_of_mass_ds=d_radius_ds,
            d2_center_of_mass_ds2=d2_radius_ds2,
        )

    def _coerce_shift_to_topology_side(
        self,
        shift: float,
        *,
        engaged_side_at_boundary: bool,
    ) -> float:
        """Snap only roundoff-sized excursions across the active topology boundary.

        ``evaluate_deadzone`` and ``evaluate_engaged`` represent different
        one-sided tangents at ``s_deadzone``.  A caller that is genuinely on
        the wrong side must not silently receive the opposite derivative, but
        event localization can land one or a few ULPs across the exact surface.
        Those roundoff-sized excursions are snapped back to the common position.
        """

        boundary = self._spec.deadzone_shift
        tolerance = 256.0 * max(1.0, abs(boundary)) * 2.220446049250313e-16
        if engaged_side_at_boundary:
            if shift < boundary - tolerance:
                raise ValueError(
                    f"engaged geometry requires shift >= {boundary}; got {shift}."
                )
            if shift < boundary:
                return boundary
        else:
            if shift > boundary + tolerance:
                raise ValueError(
                    f"deadzone geometry requires shift <= {boundary}; got {shift}."
                )
            if shift > boundary:
                return boundary
        return shift

    def _coerce_shift_to_domain(self, shift: float) -> float:
        """Return ``shift`` clipped to the geometry domain within roundoff.

        Hybrid event localization and dense-output reconstruction can produce
        endpoint states such as ``nextafter(max_shift, +inf)`` even though the
        physical event landed on the stop.  Those values should evaluate the
        stop geometry, not fail a strict floating-point inequality.  Larger
        excursions are still rejected because they indicate a real caller or
        event-handling error.
        """

        if not isfinite(shift):
            raise ValueError("shift must be finite.")

        tolerance = max(
            _SHIFT_DOMAIN_ABSOLUTE_TOLERANCE,
            128.0 * abs(self._spec.max_shift) * 2.220446049250313e-16,
        )
        if shift < -tolerance or shift > self._spec.max_shift + tolerance:
            raise ValueError(
                f"shift={shift} is outside " f"[0, {self._spec.max_shift}]."
            )

        if shift < 0.0:
            return 0.0
        if shift > self._spec.max_shift:
            return self._spec.max_shift
        return shift
