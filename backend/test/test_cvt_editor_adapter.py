"""Application-adapter regressions for physical CVT editor semantics."""

import math

from app.application.physical_contracts import template_document, with_belt


def test_belt_change_preserves_primary_shaft_radius() -> None:
    document = template_document("cvts")
    data = document.data
    geometry = data.assembly["geometry"]
    stored_outer = geometry["primary_outer_radius_at_zero_shift_m"]
    stored_height = geometry["belt"]["height_m"]
    shaft_radius = stored_outer - stored_height

    next_height = data.belt.data.height_m * 0.8
    belt_data = data.belt.data.model_copy(
        update={
            "height_m": next_height,
            "outer_width_m": data.belt.data.inner_width_m
            + 2 * next_height * math.tan(data.belt.data.half_angle_rad),
        }
    )
    belt = data.belt.model_copy(update={"data": belt_data}, deep=True)
    changed = data.model_copy(update={"belt": belt}, deep=True)
    result = with_belt(changed)

    assert math.isclose(
        result.assembly["geometry"]["primary_outer_radius_at_zero_shift_m"],
        shaft_radius + next_height,
        rel_tol=0,
        abs_tol=1e-12,
    )
    assert result.assembly["geometry"]["belt"]["height_m"] == next_height
    assert geometry["primary_outer_radius_at_zero_shift_m"] == stored_outer


def test_reapplying_same_belt_keeps_existing_primary_geometry_exact() -> None:
    document = template_document("cvts")
    data = document.data
    stored = data.assembly["geometry"]["primary_outer_radius_at_zero_shift_m"]

    result = with_belt(data)

    assert result.assembly["geometry"]["primary_outer_radius_at_zero_shift_m"] == stored
