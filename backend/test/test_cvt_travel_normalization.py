"""CVT editor travel is derived from measurable groove and belt widths."""

import math

from app.application.physical_contracts import template_document, with_belt


def _fixed_pivot_geometry(data):
    return next(
        component["geometry"]
        for component in data.assembly["pulleys"]["primary"]["components"]
        if component["kind"] == "fixed_pivot_roller_flyweight"
    )


def test_existing_cvt_normalizes_total_travel_from_deadzone_and_belt_bottom_width():
    data = template_document("cvts").data
    geometry = data.assembly["geometry"]
    free_travel = geometry["deadzone_shift_m"]
    expected_groove_width = free_travel + data.belt.data.inner_width_m

    # Simulate one of the handful of pre-Patch-C records whose stored maximum
    # does not follow the measurable groove-width convention.
    geometry["max_shift_m"] = expected_groove_width + 0.004
    contact = _fixed_pivot_geometry(data)
    contact["axial_position_min_m"] = -0.001
    contact["axial_position_max_m"] = 0.050

    normalized = with_belt(data)
    normalized_geometry = normalized.assembly["geometry"]
    normalized_contact = _fixed_pivot_geometry(normalized)

    assert math.isclose(
        normalized_geometry["max_shift_m"],
        expected_groove_width,
        rel_tol=0,
        abs_tol=1e-12,
    )
    assert normalized_contact["axial_position_min_m"] == 0.0
    assert math.isclose(
        normalized_contact["axial_position_max_m"],
        expected_groove_width,
        rel_tol=0,
        abs_tol=1e-12,
    )


def test_frontend_style_belt_swap_preserves_groove_width_via_deadzone():
    data = template_document("cvts").data
    normalized = with_belt(data)
    groove_width = normalized.assembly["geometry"]["max_shift_m"]

    belt_data = normalized.belt.data.model_copy(
        update={"inner_width_m": normalized.belt.data.inner_width_m * 0.9}
    )
    selected = normalized.model_copy(
        update={"belt": normalized.belt.model_copy(update={"data": belt_data})},
        deep=True,
    )
    selected.assembly["geometry"]["deadzone_shift_m"] = (
        groove_width - belt_data.inner_width_m
    )

    result = with_belt(selected)
    assert math.isclose(
        result.assembly["geometry"]["max_shift_m"],
        groove_width,
        rel_tol=0,
        abs_tol=1e-12,
    )


def test_legacy_belt_only_change_preserves_stored_groove_width_and_rederives_deadzone():
    data = template_document("cvts").data
    normalized = with_belt(data)
    groove_width = normalized.assembly["geometry"]["max_shift_m"]

    belt_data = normalized.belt.data.model_copy(
        update={"inner_width_m": normalized.belt.data.inner_width_m * 0.95}
    )
    selected = normalized.model_copy(
        update={"belt": normalized.belt.model_copy(update={"data": belt_data})},
        deep=True,
    )
    # Deliberately leave assembly.geometry.belt unchanged to model an older
    # client that changed only the reusable belt choice.
    result = with_belt(selected)

    assert math.isclose(
        result.assembly["geometry"]["max_shift_m"],
        groove_width,
        rel_tol=0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        result.assembly["geometry"]["deadzone_shift_m"],
        groove_width - belt_data.inner_width_m,
        rel_tol=0,
        abs_tol=1e-12,
    )
