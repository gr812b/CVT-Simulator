"""Open-belt length geometry and bracketed scalar closure solves."""

from __future__ import annotations

from math import asin, isfinite, pi, sqrt

from scipy.optimize import brentq


_ROOT_XTOL = 1e-12
_ROOT_RESIDUAL_TOL = 1e-12


def wrap_angles(
    *,
    center_distance: float,
    primary_outer_radius: float,
    secondary_outer_radius: float,
) -> tuple[float, float]:
    """
    Return primary and secondary wrap angles for one open belt loop.

    All radii refer to the belt outer surface.
    """

    _require_positive(
        center_distance=center_distance,
        primary_outer_radius=primary_outer_radius,
        secondary_outer_radius=secondary_outer_radius,
    )

    radius_difference = secondary_outer_radius - primary_outer_radius

    if abs(radius_difference) >= center_distance:
        raise ValueError(
            "The outer-radius difference must be smaller than the center "
            "distance."
        )

    alpha = asin(radius_difference / center_distance)

    return pi - 2.0 * alpha, pi + 2.0 * alpha


def open_belt_length(
    *,
    center_distance: float,
    primary_outer_radius: float,
    secondary_outer_radius: float,
) -> float:
    """Return the outer-surface length implied by one open belt loop."""

    primary_wrap_angle, secondary_wrap_angle = wrap_angles(
        center_distance=center_distance,
        primary_outer_radius=primary_outer_radius,
        secondary_outer_radius=secondary_outer_radius,
    )

    radius_difference = secondary_outer_radius - primary_outer_radius

    straight_span_length = sqrt(
        center_distance**2 - radius_difference**2
    )

    return (
        primary_outer_radius * primary_wrap_angle
        + secondary_outer_radius * secondary_wrap_angle
        + 2.0 * straight_span_length
    )


def belt_length_residual(
    *,
    belt_length: float,
    center_distance: float,
    primary_outer_radius: float,
    secondary_outer_radius: float,
) -> float:
    """Return implied outer-surface belt length minus specified length."""

    _require_positive(belt_length=belt_length)

    return (
        open_belt_length(
            center_distance=center_distance,
            primary_outer_radius=primary_outer_radius,
            secondary_outer_radius=secondary_outer_radius,
        )
        - belt_length
    )


def solve_center_distance(
    *,
    belt_length: float,
    primary_outer_radius: float,
    secondary_outer_radius: float,
) -> float:
    """
    Solve fixed center distance from one known reference geometry.

    Supplied belt length and pulley radii are measured at the belt outer
    surface.
    """

    _require_positive(
        belt_length=belt_length,
        primary_outer_radius=primary_outer_radius,
        secondary_outer_radius=secondary_outer_radius,
    )

    radius_difference = abs(
        secondary_outer_radius - primary_outer_radius
    )
    radius_sum = primary_outer_radius + secondary_outer_radius

    # Physical lower bound: outer belt envelopes cannot overlap.
    lower_bound = radius_sum

    # Tighter upper bound from the minimum possible wrapped length.
    straight_span_budget = belt_length - pi * radius_sum

    if straight_span_budget <= 0.0:
        raise ValueError(
            "The belt is too short for the supplied reference outer radii."
        )

    upper_bound = sqrt(
        radius_difference**2
        + (straight_span_budget / 2.0) ** 2
    )

    if lower_bound > upper_bound:
        raise ValueError(
            "No physical center-distance interval exists for the supplied "
            "belt length and reference outer radii."
        )

    def residual(center_distance: float) -> float:
        return belt_length_residual(
            belt_length=belt_length,
            center_distance=center_distance,
            primary_outer_radius=primary_outer_radius,
            secondary_outer_radius=secondary_outer_radius,
        )

    lower_value = residual(lower_bound)
    upper_value = residual(upper_bound)

    if abs(lower_value) <= _ROOT_RESIDUAL_TOL:
        return lower_bound

    if abs(upper_value) <= _ROOT_RESIDUAL_TOL:
        return upper_bound

    if lower_value * upper_value > 0.0:
        raise RuntimeError(
            "The center-distance root is not bracketed by the supplied "
            "reference geometry."
        )

    return brentq(
        residual,
        lower_bound,
        upper_bound,
        xtol=_ROOT_XTOL,
    )


def solve_secondary_outer_radius(
    *,
    belt_length: float,
    center_distance: float,
    primary_outer_radius: float,
    lower_bound: float,
    upper_bound: float,
) -> float:
    """
    Solve secondary outer radius inside a caller-supplied bracket.

    The caller is responsible for providing bounds that contain the
    physically reachable secondary-radius solution.
    """

    _require_positive(
        belt_length=belt_length,
        center_distance=center_distance,
        primary_outer_radius=primary_outer_radius,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )

    if lower_bound > upper_bound:
        raise ValueError("lower_bound cannot exceed upper_bound.")

    def residual(secondary_outer_radius: float) -> float:
        return belt_length_residual(
            belt_length=belt_length,
            center_distance=center_distance,
            primary_outer_radius=primary_outer_radius,
            secondary_outer_radius=secondary_outer_radius,
        )

    lower_value = residual(lower_bound)
    upper_value = residual(upper_bound)

    # At s = 0 or s = s_max, the solution is one cached endpoint. The
    # endpoint and C2C are floating-point roots, so accept numerical zero.
    if abs(lower_value) <= _ROOT_RESIDUAL_TOL:
        return lower_bound

    if abs(upper_value) <= _ROOT_RESIDUAL_TOL:
        return upper_bound

    if lower_value * upper_value > 0.0:
        raise RuntimeError(
            "The supplied secondary-radius bounds do not bracket the "
            "belt-length solution."
        )

    return brentq(
        residual,
        lower_bound,
        upper_bound,
        xtol=_ROOT_XTOL,
    )


def _require_positive(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive.")
