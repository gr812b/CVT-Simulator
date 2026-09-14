"""Regression checks for the fixed-pivot primary concrete-design service."""

from __future__ import annotations

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
