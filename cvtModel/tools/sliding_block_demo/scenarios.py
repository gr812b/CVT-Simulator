"""Measured-data-free example configurations: illustrative, NOT CVTech CAD."""
from __future__ import annotations

from dataclasses import replace
from .sliding_block import Mechanism, Profile, calibrate_zero


def _base() -> Mechanism:
    half = 0.005
    face_low = Profile("line", origin=0.0, offset=-0.0075, slope=-0.35, left=-half, right=half)
    face_high = Profile("line", origin=0.0, offset=+0.0075, slope=-1.65, left=-half, right=half)
    lower = Profile("line", origin=0.054, slope=+1.00, left=0.035, right=0.080)
    upper = Profile("line", origin=0.054, slope=-1.50, left=0.035, right=0.080)
    return Mechanism(lower, upper, face_low, face_high,
                     total_mass=0.750, gyration_radius=0.009,
                     display_count=3, radius_ref=0.054, x_max=0.015,
                     name="Straight ramps (Messick limit)")


def make(name: str) -> Mechanism:
    m = _base()
    if name == "straight":
        return calibrate_zero(m)
    if name == "curved-cup":
        # True circular-arc lower TRACK, line upper TRACK. Profile is a
        # *meridional* circle arc, not a claim about production CVTech.
        cup = Profile("circle", origin=-0.016710678, radius=0.100,
                      left=0.035, right=0.081, circle_sign=+1)
        return calibrate_zero(replace(m, lower_track=cup,
                                      name="Circular cup + straight ramp"))
    if name == "both-curved":
        low = Profile("quadratic", origin=0.054, slope=1.00, curvature=-70.0,
                      left=0.035, right=0.080)
        high = Profile("quadratic", origin=0.054, slope=-1.50, curvature=45.0,
                       left=0.035, right=0.080)
        blo = Profile("quadratic", origin=0, offset=-0.010, slope=+0.25,
                      curvature=+180.0, left=-0.005, right=0.005)
        bhi = Profile("quadratic", origin=0, offset=+0.010, slope=-2.20,
                      curvature=-180.0, left=-0.005, right=0.005)
        return calibrate_zero(replace(m, lower_track=low, upper_track=high,
                                      lower_face=blo, upper_face=bhi, x_max=0.015,
                                      name="Curved block faces + curved ramps"))
    if name == "short-track":
        m = replace(m, upper_track=replace(m.upper_track, right=0.0615),
                    name="Contact runs beyond track support")
        return calibrate_zero(m)
    if name == "parallel":
        # Both active contacts produce the same motion constraint; the
        # two-contact geometry cannot determine r(x).
        m = replace(m, upper_track=replace(m.upper_track, slope=+1.00),
                    name="Parallel contact slopes (singular)")
        return calibrate_zero(m)
    raise ValueError(f"unknown example {name!r}")


EXAMPLES = ("straight", "curved-cup", "both-curved", "short-track", "parallel")
