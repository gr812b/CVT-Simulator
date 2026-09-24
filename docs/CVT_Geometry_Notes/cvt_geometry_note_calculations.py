"""Recompute the numerical comparisons used in CVT_Geometry_Notes.tex.

Only the Python standard library is required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceGeometry:
    belt_length: float = 0.953262
    belt_thickness: float = 0.0155702
    cord_depth: float = 0.00254
    sheave_half_angle: float = 0.200712864
    primary_outer_min: float = 0.0362077
    secondary_outer_max: float = 0.1016
    deadzone: float = 0.0024892
    shift_max: float = 0.01905


def belt_length_exact(rp: float, rs: float, center_distance: float) -> float:
    """Exact outer-surface belt-path length used by the CINDER geometry."""
    dr = rs - rp
    return (
        math.pi * (rp + rs)
        + 2.0 * dr * math.asin(dr / center_distance)
        + 2.0 * math.sqrt(center_distance**2 - dr**2)
    )


def belt_length_small_angle(rp: float, rs: float, center_distance: float) -> float:
    """Small-angle form obtained by dropping the unequal-wrap correction."""
    dr = rs - rp
    return math.pi * (rp + rs) + 2.0 * math.sqrt(center_distance**2 - dr**2)


def _bisect(fun, a: float, b: float, tol: float = 1e-14) -> float:
    fa, fb = fun(a), fun(b)
    if fa * fb > 0:
        raise ValueError("Root is not bracketed.")
    for _ in range(250):
        c = 0.5 * (a + b)
        fc = fun(c)
        if abs(fc) < tol or abs(b - a) < tol:
            return c
        if fa * fc <= 0:
            b, fb = c, fc
        else:
            a, fa = c, fc
    return 0.5 * (a + b)


def exact_center_distance(g: ReferenceGeometry) -> float:
    dr = abs(g.secondary_outer_max - g.primary_outer_min)
    return _bisect(
        lambda C: belt_length_exact(
            g.primary_outer_min, g.secondary_outer_max, C
        ) - g.belt_length,
        dr * (1.0 + 1e-12),
        1.0,
    )


def approximate_center_distance(g: ReferenceGeometry) -> float:
    rp, rs, Lb = g.primary_outer_min, g.secondary_outer_max, g.belt_length
    return math.sqrt(
        (rs - rp) ** 2
        + 0.25 * (Lb - math.pi * (rp + rs)) ** 2
    )


def approximate_secondary_radius(
    rp: float, center_distance: float, belt_length: float
) -> float:
    pi = math.pi
    radicand = (
        (pi**2 + 4.0) * center_distance**2
        - belt_length**2
        + 4.0 * pi * belt_length * rp
        - 4.0 * pi**2 * rp**2
    )
    return (
        pi * belt_length
        + (4.0 - pi**2) * rp
        - 2.0 * math.sqrt(radicand)
    ) / (pi**2 + 4.0)


def exact_secondary_radius(
    rp: float, center_distance: float, belt_length: float
) -> float:
    lo = max(1e-9, rp - center_distance + 1e-10)
    hi = rp + center_distance - 1e-10
    n = 20000
    x_prev = lo
    f_prev = belt_length_exact(rp, x_prev, center_distance) - belt_length

    for i in range(1, n + 1):
        x = lo + (hi - lo) * i / n
        f = belt_length_exact(rp, x, center_distance) - belt_length
        if f_prev == 0 or f_prev * f < 0:
            return _bisect(
                lambda rs: belt_length_exact(rp, rs, center_distance)
                - belt_length,
                x_prev,
                x,
            )
        x_prev, f_prev = x, f

    raise ValueError("No compatible secondary-radius root found.")


def effective_ratio(rp: float, rs: float, cord_depth: float) -> float:
    return (rs - cord_depth) / (rp - cord_depth)


def main() -> None:
    g = ReferenceGeometry()
    C_exact = exact_center_distance(g)
    C_approx = approximate_center_distance(g)

    rp_max = (
        g.primary_outer_min
        + (g.shift_max - g.deadzone)
        / (2.0 * math.tan(g.sheave_half_angle))
    )
    rs_exact = exact_secondary_radius(rp_max, C_exact, g.belt_length)
    rs_approx_inferred_C = approximate_secondary_radius(
        rp_max, C_approx, g.belt_length
    )
    rs_approx_true_C = approximate_secondary_radius(
        rp_max, C_exact, g.belt_length
    )

    R_exact = effective_ratio(rp_max, rs_exact, g.cord_depth)
    R_bad = effective_ratio(rp_max, rs_approx_inferred_C, g.cord_depth)
    R_true_C = effective_ratio(rp_max, rs_approx_true_C, g.cord_depth)

    print(f"C_exact                = {C_exact:.12f} m")
    print(f"C_approx               = {C_approx:.12f} m")
    print(
        "center-distance error   = "
        f"{100*(C_approx-C_exact)/C_exact:.6f} %"
    )
    print(f"r_p(s_max)              = {rp_max:.12f} m")
    print(f"r_s exact               = {rs_exact:.12f} m")
    print(f"r_s approx, inferred C  = {rs_approx_inferred_C:.12f} m")
    print(f"r_s approx, true C      = {rs_approx_true_C:.12f} m")
    print(f"R_eff exact             = {R_exact:.9f}")
    print(f"R_eff approx inferred C = {R_bad:.9f}")
    print(f"R_eff approx true C     = {R_true_C:.9f}")
    print(
        "R_eff error, inferred C = "
        f"{100*abs(R_bad-R_exact)/R_exact:.6f} %"
    )
    print(
        "R_eff error, true C     = "
        f"{100*abs(R_true_C-R_exact)/R_exact:.6f} %"
    )


if __name__ == "__main__":
    main()
