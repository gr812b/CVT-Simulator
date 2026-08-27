from __future__ import annotations

from math import isclose, radians, tan

import numpy as np

from cinder.model.cvt.actuation import (
    FlyweightMassGeometry,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometry,
    PivotedRollerFollowerGeometrySpec,
)
from cinder.model.cvt.profiles import LinearSegment, PiecewiseRamp


def test_negative_ramp_axial_direction_matches_inward_outward_convention() -> None:
    geometry = PivotedRollerFollowerGeometry(
        PivotedRollerFollowerGeometrySpec(
            pivot_axial_position=0.0,
            pivot_radius=0.05,
            arm_length=0.04,
            roller_radius=0.005,
            ramp_reference_axial_position=0.04,
            ramp_reference_radius=0.06,
            ramp_profile=PiecewiseRamp(
                (LinearSegment(length=0.02, angle_degrees=15.0),)
            ),
            ramp_axial_direction=-1,
            axial_position_min=0.0,
            axial_position_max=0.005,
            roller_side_sign=1,
        )
    )

    x0, r0 = geometry.ramp_surface_point(
        contact_coordinate=0.0,
        axial_position=0.0,
    )
    x1, r1 = geometry.ramp_surface_point(
        contact_coordinate=0.01,
        axial_position=0.0,
    )

    assert isclose(x0, 0.04)
    assert isclose(r0, 0.06)
    assert isclose(x1, 0.03)
    assert isclose(r1, 0.06 + 0.01 * tan(radians(15.0)))


def _two_solution_geometry() -> PivotedRollerFollowerGeometrySpec:
    # This straight-ramp configuration deliberately admits two distinct
    # instantaneous arm orientations.  The smaller-q branch has positive q'
    # and remains continuous through the test interval.
    return PivotedRollerFollowerGeometrySpec(
        pivot_axial_position=0.0,
        pivot_radius=0.05,
        arm_length=0.04,
        roller_radius=0.005,
        ramp_reference_axial_position=0.02,
        ramp_reference_radius=0.08,
        ramp_profile=PiecewiseRamp(
            (LinearSegment(length=0.15, angle_degrees=5.0),)
        ),
        ramp_axial_direction=-1,
        axial_position_min=0.0,
        axial_position_max=0.005,
        roller_side_sign=-1,
        root_scan_points=257,
        validation_positions=17,
    )


def test_branch_trace_selects_smallest_initial_q_then_stays_continuous() -> None:
    geometry = PivotedRollerFollowerGeometry(_two_solution_geometry())
    initial_candidates = geometry.contact_candidates(0.0)
    assert len(initial_candidates) == 2

    positions = np.linspace(0.0, 0.005, 41)
    trace = geometry.trace_contact_branch(positions)
    assert len(trace) == len(positions)

    expected_initial = min(candidate.angle for candidate in initial_candidates)
    assert isclose(trace[0].angle, expected_initial, abs_tol=1.0e-10)

    # The chosen branch is the lower-q branch at the start and its q increases
    # continuously.  The other instantaneous solution is allowed to exist.
    angles = np.asarray([sample.angle for sample in trace])
    assert np.all(np.diff(angles) > 0.0)
    assert all(sample.angle_gradient > 0.0 for sample in trace)


def test_runtime_map_compiles_the_same_selected_branch() -> None:
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=3,
        arm_length=0.04,
        arm_mass_per_flyweight=0.01,
        end_mass_per_flyweight=0.02,
    )
    mechanism = PivotedRollerFollowerFlyweightMap(
        geometry_spec=_two_solution_geometry(),
        mass_geometry=mass,
        compilation_points=65,
    )

    initial = mechanism.contact_at(0.0)
    final = mechanism.contact_at(0.005)
    assert final.angle > initial.angle
    assert mechanism.evaluate(0.0025).angle_gradient > 0.0
