import pytest

from app.application.cvt_editor import (
    apply_initial_tune,
    initial_tune_surface,
    mechanism_preview,
    pulley_preview,
)
from app.application.physical_contracts import template_document


def _cvt():
    document = template_document("cvts")
    assert document.kind == "cvts"
    return document.data


def _fixed_pivot(cvt):
    return next(
        component
        for component in cvt.assembly["pulleys"]["primary"]["components"]
        if component["kind"] == "fixed_pivot_roller_flyweight"
    )


def test_initial_tune_surface_uses_current_hardware_without_rewriting_it():
    cvt = _cvt()
    before = cvt.model_dump()
    surface = initial_tune_surface(cvt)
    assert "primary_ramp_profile" in surface.values
    assert "primary_ramp_axial_offset" in surface.values
    assert apply_initial_tune(cvt, surface.values).model_dump() == before


def test_initial_ramp_offset_moves_ramp_not_pivot():
    cvt = _cvt()
    surface = initial_tune_surface(cvt)
    component = _fixed_pivot(cvt)
    before_pivot = component["geometry"]["pivot_axial_position_m"]
    before_ramp = component["geometry"]["ramp_reference_axial_position_m"]
    values = dict(surface.values)
    values["primary_ramp_axial_offset"] += 0.001
    changed = apply_initial_tune(cvt, values)
    geometry = _fixed_pivot(changed)["geometry"]
    assert geometry["pivot_axial_position_m"] == before_pivot
    assert geometry["ramp_reference_axial_position_m"] == pytest.approx(before_ramp + 0.001)


def test_pulley_preview_depends_only_on_canonical_pulley_geometry():
    cvt = _cvt()
    preview = pulley_preview(cvt.assembly["geometry"])
    assert len(preview.frames) == 65
    assert preview.geometry.max_shift_m == cvt.assembly["geometry"]["max_shift_m"]


def test_hardware_mechanism_preview_does_not_require_roller_contact():
    preview = mechanism_preview(_cvt())
    assert preview.geometry.mechanisms is not None
    assert preview.geometry.mechanisms.primary is not None
    assert len(preview.frames) == 1
    assert preview.geometry.mechanisms.poses[0].primary_roller_m is None
