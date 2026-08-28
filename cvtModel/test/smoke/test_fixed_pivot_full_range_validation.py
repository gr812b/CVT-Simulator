from __future__ import annotations

from cinder.model.cvt.actuation import (
    PivotedRollerFollowerGeometry,
    PivotedRollerFollowerGeometrySpec,
)
from cinder.model.cvt.profiles import (
    C3TransitionSegment,
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
)


INCH = 0.0254
MM = 1.0e-3


def _geometry(*, smooth: bool) -> PivotedRollerFollowerGeometry:
    line = LinearSegment(length=5.0 * MM, angle_degrees=20.0)
    circle = CircularSegment(
        length=30.0 * MM,
        angle_start_degrees=35.0,
        angle_end_degrees=10.0,
        quadrant=2,
    )
    if smooth:
        transition = C3TransitionSegment.between_segments(
            left=line,
            right=circle,
            length=3.0 * MM,
        )
        profile = PiecewiseRamp((line, transition, circle))
    else:
        profile = PiecewiseRamp((line, circle))

    return PivotedRollerFollowerGeometry(
        PivotedRollerFollowerGeometrySpec(
            pivot_axial_position=0.0,
            pivot_radius=1.675 * INCH,
            arm_length=1.241 * INCH,
            roller_radius=6.5 * MM,
            ramp_reference_axial_position=1.5 * INCH,
            ramp_reference_radius=(1.675 + 0.2776) * INCH,
            ramp_profile=profile,
            ramp_axial_direction=-1,
            axial_position_min=0.0,
            axial_position_max=0.75 * INCH,
            roller_side_sign=1,
            root_scan_points=513,
            validation_positions=65,
        )
    )


def test_dynamic_audit_rejects_raw_derivative_discontinuity() -> None:
    report = _geometry(smooth=False).audit_operating_interval(sample_count=129)
    assert not report.is_valid
    assert "profile.not_c3" in {item.code for item in report.errors}


def test_smoothed_provisional_geometry_passes_full_range_audit() -> None:
    report = _geometry(smooth=True).audit_operating_interval(sample_count=257)
    assert report.is_valid, [item.as_dict() for item in report.findings]
    assert report.traced_positions == report.requested_positions
    assert report.minimum_angle_gradient is not None
    assert report.minimum_angle_gradient > 0.0
    assert report.maximum_arm_length_error is not None
    assert report.maximum_arm_length_error < 1.0e-8
