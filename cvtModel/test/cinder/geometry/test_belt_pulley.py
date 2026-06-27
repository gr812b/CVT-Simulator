# cvtModel/test/cinder/geometry/test_belt_pulley.py

from __future__ import annotations

import json
from math import pi, tan
from pathlib import Path

import pytest

from cinder.geometry.belt_length import belt_length_residual
from cinder.geometry.belt_pulley import BeltPulleyGeometry
from cinder.geometry.spec import BeltPulleyGeometrySpec, BeltSectionSpec


_REFERENCE_PATH = (
    Path(__file__).parent
    / "data"
    / "default_geometry_positions.json"
)

_REFERENCE_POSITIONS = json.loads(
    _REFERENCE_PATH.read_text()
)["positions"]


def _default_spec() -> BeltPulleyGeometrySpec:
    belt_height = 0.0155702

    return BeltPulleyGeometrySpec(
        belt=BeltSectionSpec(
            height=belt_height,
            outer_width=0.021336,
            inner_width=0.0168148,
            cord_depth_from_outer=belt_height / 2.0,
        ),
        belt_outer_length=0.953262,
        primary_outer_radius_at_zero_shift=0.0206375 + belt_height,
        secondary_outer_radius_at_zero_shift=0.1016,
        sheave_half_angle=0.40142572795869574 / 2.0,
        deadzone_shift=0.0024892,
        max_shift=0.01905,
    )


@pytest.fixture
def geometry() -> BeltPulleyGeometry:
    return BeltPulleyGeometry(_default_spec())


@pytest.mark.parametrize(
    "expected",
    _REFERENCE_POSITIONS,
    ids=lambda item: f"s={item['shift']:.7f}",
)
def test_geometry_matches_reference_positions(
    geometry: BeltPulleyGeometry,
    expected: dict[str, float],
) -> None:
    """Regression test across the deadzone and active shift range."""

    position = geometry.evaluate(expected["shift"])

    assert position.primary.outer == pytest.approx(
        expected["primary_outer_radius"],
        abs=1e-11,
    )
    assert position.secondary.outer == pytest.approx(
        expected["secondary_outer_radius"],
        abs=1e-11,
    )

    assert position.primary.effective == pytest.approx(
        expected["primary_effective_radius"],
        abs=1e-11,
    )
    assert position.secondary.effective == pytest.approx(
        expected["secondary_effective_radius"],
        abs=1e-11,
    )

    assert position.primary.center_of_mass == pytest.approx(
        expected["primary_center_of_mass_radius"],
        abs=1e-11,
    )
    assert position.secondary.center_of_mass == pytest.approx(
        expected["secondary_center_of_mass_radius"],
        abs=1e-11,
    )

    assert position.primary_wrap_angle == pytest.approx(
        expected["primary_wrap_angle"],
        abs=1e-11,
    )
    assert position.secondary_wrap_angle == pytest.approx(
        expected["secondary_wrap_angle"],
        abs=1e-11,
    )

    assert position.primary.d_effective_ds == pytest.approx(
        expected["d_primary_radius_ds"],
        abs=1e-10,
    )
    assert position.secondary.d_effective_ds == pytest.approx(
        expected["d_secondary_radius_ds"],
        abs=1e-10,
    )

    assert position.primary.d2_effective_ds2 == pytest.approx(
        expected["d2_primary_radius_ds2"],
        abs=1e-9,
    )
    assert position.secondary.d2_effective_ds2 == pytest.approx(
        expected["d2_secondary_radius_ds2"],
        abs=1e-8,
    )


@pytest.mark.parametrize(
    "expected",
    _REFERENCE_POSITIONS,
    ids=lambda item: f"s={item['shift']:.7f}",
)
def test_geometry_satisfies_identities(
    geometry: BeltPulleyGeometry,
    expected: dict[str, float],
) -> None:
    """Check relations that do not depend on the saved regression values."""

    position = geometry.evaluate(expected["shift"])
    spec = geometry.spec

    residual = belt_length_residual(
        belt_length=spec.belt_outer_length,
        center_distance=spec.center_distance,
        primary_outer_radius=position.primary.outer,
        secondary_outer_radius=position.secondary.outer,
    )
    assert residual == pytest.approx(0.0, abs=1e-10)

    assert (
        position.primary_wrap_angle + position.secondary_wrap_angle
    ) == pytest.approx(2.0 * pi, abs=1e-12)

    assert position.primary.effective == pytest.approx(
        position.primary.outer - spec.belt.cord_depth_from_outer,
        abs=1e-12,
    )
    assert position.secondary.effective == pytest.approx(
        position.secondary.outer - spec.belt.cord_depth_from_outer,
        abs=1e-12,
    )

    assert position.primary.center_of_mass == pytest.approx(
        position.primary.outer
        - spec.belt.center_of_mass_depth_from_outer,
        abs=1e-12,
    )
    assert position.secondary.center_of_mass == pytest.approx(
        position.secondary.outer
        - spec.belt.center_of_mass_depth_from_outer,
        abs=1e-12,
    )


@pytest.mark.parametrize(
    "shift",
    (
        0.0066294,
        0.0107696,
        0.0149098,
    ),
)
def test_active_radius_derivatives_match_finite_differences(
    geometry: BeltPulleyGeometry,
    shift: float,
) -> None:
    """
    Independently check the analytic derivatives away from the deadzone and
    shift endpoints.
    """

    step = 1e-6

    before = geometry.evaluate(shift - step)
    current = geometry.evaluate(shift)
    after = geometry.evaluate(shift + step)

    primary_first_difference = (
        after.primary.outer - before.primary.outer
    ) / (2.0 * step)
    secondary_first_difference = (
        after.secondary.outer - before.secondary.outer
    ) / (2.0 * step)

    primary_second_difference = (
        after.primary.outer
        - 2.0 * current.primary.outer
        + before.primary.outer
    ) / step**2
    secondary_second_difference = (
        after.secondary.outer
        - 2.0 * current.secondary.outer
        + before.secondary.outer
    ) / step**2

    assert current.primary.d_effective_ds == pytest.approx(
        primary_first_difference,
        abs=2e-6,
    )
    assert current.secondary.d_effective_ds == pytest.approx(
        secondary_first_difference,
        abs=2e-6,
    )

    assert current.primary.d2_effective_ds2 == pytest.approx(
        primary_second_difference,
        abs=2e-3,
    )
    assert current.secondary.d2_effective_ds2 == pytest.approx(
        secondary_second_difference,
        abs=2e-3,
    )


def test_primary_slope_matches_sheave_geometry(
    geometry: BeltPulleyGeometry,
) -> None:
    spec = geometry.spec
    active_shift = (
        spec.deadzone_shift
        + 0.5 * (spec.max_shift - spec.deadzone_shift)
    )

    position = geometry.evaluate(active_shift)

    assert position.primary.d_effective_ds == pytest.approx(
        1.0 / (2.0 * tan(spec.sheave_half_angle)),
        abs=1e-12,
    )
