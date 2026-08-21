"""One-sided geometry semantics at the deadzone/engagement hybrid boundary."""

from __future__ import annotations

from math import radians

import pytest

from cinder.model.cvt.geometry import (
    BeltPulleyGeometry,
    BeltPulleyGeometrySpec,
    BeltSectionSpec,
)


def _geometry(*, deadzone_shift: float) -> BeltPulleyGeometry:
    belt = BeltSectionSpec(
        height=0.00762,
        outer_width=0.029972,
        inner_width=0.02667,
        cord_depth_from_outer=0.00127,
    )
    return BeltPulleyGeometry(
        BeltPulleyGeometrySpec(
            belt=belt,
            belt_outer_length=0.87157964534,
            primary_outer_radius_at_zero_shift=0.03491778,
            secondary_outer_radius_at_zero_shift=0.08507,
            sheave_half_angle=radians(15.0),
            deadzone_shift=deadzone_shift,
            max_shift=deadzone_shift + 0.02687649,
        )
    )


def _assert_same_position(left, right) -> None:
    assert left.shift == pytest.approx(right.shift)
    assert left.primary.effective == pytest.approx(right.primary.effective)
    assert left.secondary.effective == pytest.approx(right.secondary.effective)
    assert left.primary_axial_coordinate.value == pytest.approx(
        right.primary_axial_coordinate.value
    )
    assert left.secondary_axial_coordinate.value == pytest.approx(
        right.secondary_axial_coordinate.value
    )
    assert left.belt_axial_coordinate.value == pytest.approx(
        right.belt_axial_coordinate.value
    )


@pytest.mark.parametrize("deadzone_shift", [0.0, 0.002])
def test_engaged_geometry_uses_right_hand_derivatives_at_engagement(
    deadzone_shift: float,
) -> None:
    geometry = _geometry(deadzone_shift=deadzone_shift)

    deadzone_side = geometry.evaluate(deadzone_shift)
    engaged_side = geometry.evaluate_engaged(deadzone_shift)
    _assert_same_position(deadzone_side, engaged_side)

    assert deadzone_side.primary.d_effective_ds == pytest.approx(0.0)
    assert deadzone_side.secondary.d_effective_ds == pytest.approx(0.0)
    assert deadzone_side.belt_axial_coordinate.d_value_ds == pytest.approx(0.0)

    assert engaged_side.primary.d_effective_ds > 0.0
    assert engaged_side.secondary.d_effective_ds < 0.0
    assert engaged_side.belt_axial_coordinate.d_value_ds == pytest.approx(0.5)


def test_engaged_side_matches_limit_from_inside_engaged_domain() -> None:
    geometry = _geometry(deadzone_shift=0.0)
    at_boundary = geometry.evaluate_engaged(0.0)
    just_inside = geometry.evaluate(1.0e-10)

    assert at_boundary.primary.d_effective_ds == pytest.approx(
        just_inside.primary.d_effective_ds
    )
    assert at_boundary.secondary.d_effective_ds == pytest.approx(
        just_inside.secondary.d_effective_ds,
        rel=1.0e-7,
    )
    assert at_boundary.belt_axial_coordinate.d_value_ds == pytest.approx(
        just_inside.belt_axial_coordinate.d_value_ds
    )
