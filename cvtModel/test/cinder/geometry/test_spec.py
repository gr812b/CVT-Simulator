# cvtModel/test/cinder/geometry/test_spec.py

from math import pi

import pytest

from cinder.geometry.belt_length import belt_length_residual
from cinder.geometry.spec import BeltPulleyGeometrySpec, BeltSectionSpec


def test_default_reference_geometry_resolves_consistently() -> None:
    belt_height = 0.0155702
    belt_width_top = 0.021336
    belt_width_bottom = 0.0168148

    # Legacy primary value is an inner radius; legacy secondary 4 in value
    # is already the outer belt radius.
    primary_outer_radius_at_zero_shift = 0.0206375 + belt_height
    secondary_outer_radius_at_zero_shift = 0.1016

    belt = BeltSectionSpec(
        height=belt_height,
        outer_width=belt_width_top,
        inner_width=belt_width_bottom,
        # Compatibility convention for now: the old model used mid-thickness
        # as its "effective" radius. Replace when measured cord depth is known.
        cord_depth_from_outer=belt_height / 2.0,
    )

    spec = BeltPulleyGeometrySpec(
        belt=belt,
        belt_outer_length=0.953262,
        primary_outer_radius_at_zero_shift=primary_outer_radius_at_zero_shift,
        secondary_outer_radius_at_zero_shift=secondary_outer_radius_at_zero_shift,
        sheave_half_angle=0.40142572795869574 / 2.0,
        deadzone_shift=0.0024892,
        max_shift=0.01905,
    )

    assert spec.primary_outer_radius_at_zero_shift == pytest.approx(0.0362077)
    assert spec.secondary_outer_radius_at_zero_shift == pytest.approx(0.1016)

    assert spec.primary_effective_radius_at_zero_shift == pytest.approx(0.0284226)
    assert spec.secondary_effective_radius_at_zero_shift == pytest.approx(0.0938149)

    assert spec.belt.center_of_mass_depth_from_outer == pytest.approx(
        0.007477566089658234
    )

    assert spec.center_distance == pytest.approx(
        0.2516169993634399,
        abs=1e-10,
    )

    assert spec.primary_outer_radius_at_max_shift == pytest.approx(
        0.07690716628008201,
        abs=1e-12,
    )
    assert spec.secondary_outer_radius_at_max_shift == pytest.approx(
        0.06619603577706444,
        abs=1e-12,
    )

    reference_residual = belt_length_residual(
        belt_length=spec.belt_outer_length,
        center_distance=spec.center_distance,
        primary_outer_radius=spec.primary_outer_radius_at_zero_shift,
        secondary_outer_radius=spec.secondary_outer_radius_at_zero_shift,
    )
    assert reference_residual == pytest.approx(0.0, abs=1e-10)

    max_shift_residual = belt_length_residual(
        belt_length=spec.belt_outer_length,
        center_distance=spec.center_distance,
        primary_outer_radius=spec.primary_outer_radius_at_max_shift,
        secondary_outer_radius=spec.secondary_outer_radius_at_max_shift,
    )
    assert max_shift_residual == pytest.approx(0.0, abs=1e-10)

    lower_bound = (
        spec.primary_outer_radius_at_zero_shift
        + spec.secondary_outer_radius_at_zero_shift
    )
    assert spec.center_distance >= lower_bound

    r_p = spec.primary_outer_radius_at_zero_shift
    r_s = spec.secondary_outer_radius_at_zero_shift
    tighter_upper_bound = (
        (r_s - r_p) ** 2 + ((spec.belt_outer_length - pi * (r_p + r_s)) / 2.0) ** 2
    ) ** 0.5
    assert spec.center_distance <= tighter_upper_bound
