"""Regression checks for the fixed-pivot primary concrete-design service."""

from __future__ import annotations

from dataclasses import replace

from app.engineering.fixed_pivot_primary import (
    ArchitectureDesign,
    FixedPivotPrimaryDesignService,
    OperatingCondition,
    RampDesign,
)


def _design_from_defaults(service: FixedPivotPrimaryDesignService):
    defaults = service.defaults()
    return (
        ArchitectureDesign(**defaults["architecture"]),
        RampDesign(**defaults["ramp"]),
        defaults["operating"],
    )


def test_reference_concrete_design_is_full_range_and_below_90_deg() -> None:
    service = FixedPivotPrimaryDesignService()
    architecture, ramp, _ = _design_from_defaults(service)
    analysis = service.analyze_concrete(
        architecture=architecture,
        ramp=ramp,
        sample_count=81,
    )

    assert analysis["validity"]["valid"] is True
    assert abs(
        analysis["contact_valid_travel_m"] - analysis["requested_travel_m"]
    ) < 1.0e-9
    assert analysis["summary"]["max_arm_angle_deg"] < 90.0
    assert len(analysis["geometry"]["axis_values"]) == 81


def test_zero_speed_quasistatic_force_is_zero_and_reference_speed_is_positive() -> None:
    service = FixedPivotPrimaryDesignService()
    architecture, ramp, operating_defaults = _design_from_defaults(service)
    analysis = service.analyze_concrete(
        architecture=architecture,
        ramp=ramp,
        sample_count=61,
    )
    analysis_id = analysis["analysis_id"]

    zero = service.evaluate_concrete_response(
        analysis_id=analysis_id,
        operating=OperatingCondition(
            tip_mass_per_flyweight_kg=operating_defaults[
                "tip_mass_per_flyweight_kg"
            ],
            shaft_speed_rad_s=0.0,
        ),
    )
    zero_force = zero["loads"]["fields"]["flyweight_total_closing_force_N"]
    assert max(abs(value) for value in zero_force if value is not None) < 1.0e-10

    running = service.evaluate_concrete_response(
        analysis_id=analysis_id,
        operating=OperatingCondition(**operating_defaults),
    )
    force = running["loads"]["fields"]["flyweight_total_closing_force_N"]
    assert max(value for value in force if value is not None) > 0.0


def test_contact_loss_does_not_change_requested_travel_contract() -> None:
    service = FixedPivotPrimaryDesignService()
    architecture, ramp, _ = _design_from_defaults(service)
    steep = replace(
        ramp,
        kind="constant",
        linear_angle_deg=55.0,
        constant_length_m=38.0e-3,
    )
    analysis = service.analyze_concrete(
        architecture=architecture,
        ramp=steep,
        sample_count=81,
    )

    assert analysis["requested_travel_m"] == architecture.required_travel_m
    assert analysis["contact_valid_travel_m"] < analysis["requested_travel_m"]
    assert analysis["validity"]["valid"] is False
    assert analysis["validity"]["failure"]["code"] == "CONTACT_LOST"


def test_progressive_profile_keeps_linear_and_circular_start_tangents_independent() -> None:
    from app.engineering.fixed_pivot_primary.cinder_adapter import build_ramp

    service = FixedPivotPrimaryDesignService()
    _, ramp, _ = _design_from_defaults(service)
    changed = replace(
        ramp,
        linear_angle_deg=32.0,
        circular_start_angle_deg=38.0,
        circular_end_angle_deg=20.0,
    )
    profile = build_ramp(changed)
    assert profile.x_max > profile.x_min


def test_rejected_physical_design_still_returns_requested_ramp_and_failure_location() -> None:
    service = FixedPivotPrimaryDesignService()
    architecture, ramp, _ = _design_from_defaults(service)
    steep = replace(
        ramp,
        kind="constant",
        linear_angle_deg=55.0,
        constant_length_m=38.0e-3,
    )
    analysis = service.analyze_concrete(
        architecture=architecture,
        ramp=steep,
        sample_count=81,
    )

    assert analysis["validity"]["valid"] is False
    assert analysis["validity"]["failure"]["shift_m"] is not None
    assert len(analysis["ramp_surface_open"]["x_m"]) > 2
    assert len(analysis["ramp_surface_open"]["x_m"]) == len(
        analysis["ramp_surface_open"]["r_m"]
    )


def test_runtime_map_compile_failure_is_warning_not_physical_geometry_failure(monkeypatch) -> None:
    import app.engineering.fixed_pivot_primary.cinder_adapter as adapter

    service = FixedPivotPrimaryDesignService()
    architecture, ramp, _ = _design_from_defaults(service)

    def reject_runtime_map(*args, **kwargs):
        del args, kwargs
        raise ValueError(
            "The compiled fixed-pivot flyweight map reverses or reaches a singular motion ratio."
        )

    monkeypatch.setattr(adapter, "_build_production_map", reject_runtime_map)
    analysis = service.analyze_concrete(
        architecture=architecture,
        ramp=ramp,
        sample_count=81,
    )

    assert analysis["validity"]["valid"] is True
    warning_codes = {item["code"] for item in analysis["validity"]["warnings"]}
    assert "RUNTIME_MAP_COMPILE_FAILED" in warning_codes
    assert analysis["summary"]["runtime_map_compiled"] is False
    assert analysis["contact_valid_travel_m"] == analysis["requested_travel_m"]


def test_exact_double_contact_event_preempts_later_sampled_branch_result(monkeypatch) -> None:
    import app.engineering.fixed_pivot_primary.cinder_adapter as adapter

    service = FixedPivotPrimaryDesignService()
    architecture, ramp, _ = _design_from_defaults(service)
    event = adapter.DoubleContactEvent(
        shift_m=4.25e-3,
        angle_rad=0.42,
        roller_center_x_m=25.0e-3,
        roller_center_r_m=55.0e-3,
        contact_coordinate_1_m=7.0e-3,
        contact_x_1_m=22.0e-3,
        contact_r_1_m=50.0e-3,
        contact_coordinate_2_m=24.0e-3,
        contact_x_2_m=28.0e-3,
        contact_r_2_m=51.0e-3,
    )

    monkeypatch.setattr(
        adapter,
        "_first_selected_double_contact_event",
        lambda *args, **kwargs: event,
    )
    analysis = service.analyze_concrete(
        architecture=architecture,
        ramp=ramp,
        sample_count=81,
    )

    failure = analysis["validity"]["failure"]
    assert analysis["validity"]["valid"] is False
    assert failure["code"] == "SECOND_CONTACT"
    assert abs(failure["shift_m"] - event.shift_m) < 1.0e-12
    assert failure["geometry"]["kind"] == "double_contact"
    assert {item["label"] for item in failure["geometry"]["contacts"]} == {"C1", "C2"}
