from __future__ import annotations

from math import hypot, isclose

import numpy as np

from cinder.model.cvt.actuation import (
    PivotedRollerFollowerGeometry,
    PivotedRollerFollowerGeometrySpec,
)
from cinder.model.cvt.profiles import CircularSegment, LinearSegment, PiecewiseRamp


INCH = 0.0254
MM = 1.0e-3


def _provisional_geometry() -> PivotedRollerFollowerGeometry:
    ramp = PiecewiseRamp(
        (
            LinearSegment(length=5.0 * MM, angle_degrees=20.0),
            CircularSegment(
                length=30.0 * MM,
                angle_start_degrees=35.0,
                angle_end_degrees=10.0,
                quadrant=2,
            ),
        )
    )
    return PivotedRollerFollowerGeometry(
        PivotedRollerFollowerGeometrySpec(
            pivot_axial_position=0.0,
            pivot_radius=1.675 * INCH,
            arm_length=1.241 * INCH,
            roller_radius=6.5 * MM,
            ramp_reference_axial_position=1.5 * INCH,
            ramp_reference_radius=(1.675 + 0.2776) * INCH,
            ramp_profile=ramp,
            ramp_axial_direction=-1,
            axial_position_min=0.0,
            axial_position_max=0.75 * INCH,
            roller_side_sign=1,
            root_scan_points=513,
            validation_positions=65,
        )
    )


def test_c0_junction_does_not_create_false_brent_root() -> None:
    geometry = _provisional_geometry()
    x = 1.09 * MM

    # At this location the smooth offset curves do not satisfy the rigid arm
    # circle. The physically valid contact is the sharp corner itself.
    roots = geometry._contact_roots(x)
    assert all(abs(root - 5.0 * MM) > 1.0e-8 for root in roots)

    candidates = geometry.contact_candidates(x)
    corners = [candidate for candidate in candidates if candidate.corner_contact]
    assert len(corners) == 1


def test_corner_contact_keeps_arm_and_roller_radii_exact() -> None:
    geometry = _provisional_geometry()
    x = 1.09 * MM
    candidate = next(
        candidate
        for candidate in geometry.contact_candidates(x)
        if candidate.corner_contact
    )

    arm_length = hypot(
        candidate.roller_center_axial_position
        - geometry.spec.pivot_axial_position,
        candidate.roller_center_radius - geometry.spec.pivot_radius,
    )
    roller_radius = hypot(
        candidate.roller_center_axial_position - candidate.contact_axial_position,
        candidate.roller_center_radius - candidate.contact_radius,
    )

    assert isclose(
        arm_length,
        geometry.spec.arm_length,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    )
    assert isclose(
        roller_radius,
        geometry.spec.roller_radius,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    )


def test_selected_branch_crosses_line_corner_and_circle_without_stretching() -> None:
    geometry = _provisional_geometry()
    positions = np.linspace(0.0, 0.75 * INCH, 401)
    trace = geometry.trace_contact_branch(positions)

    assert len(trace) == len(positions)
    assert np.all(np.diff([sample.angle for sample in trace]) > 0.0)

    for sample in trace:
        arm_length = hypot(
            sample.roller_center_axial_position
            - geometry.spec.pivot_axial_position,
            sample.roller_center_radius - geometry.spec.pivot_radius,
        )
        assert isclose(
            arm_length,
            geometry.spec.arm_length,
            rel_tol=0.0,
            abs_tol=2.0e-10,
        )
