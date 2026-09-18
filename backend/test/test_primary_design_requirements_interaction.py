"""Regression coverage for retained path-conditioner helpers."""

from __future__ import annotations

from math import pi

import numpy as np

from app.engineering.fixed_pivot_primary.models import ArchitectureDesign
from app.engineering.fixed_pivot_primary.path_domain import (
    ForceRequirement,
    PathSegment,
    _requirement_mass_mask,
    compile_path_domain,
)
from app.engineering.fixed_pivot_primary.path_domain_refinement import (
    _requirement_mass_masks_for_layer,
)
from app.schemas.primary_design import FixedPivotPathDomainConditionRequest

INCH = 0.0254


def _architecture() -> ArchitectureDesign:
    return ArchitectureDesign(
        pivot_axial_position_m=0.0,
        pivot_radius_m=1.675 * INCH,
        arm_length_m=1.241 * INCH,
        roller_radius_m=6.5e-3,
        required_travel_m=0.75 * INCH,
        number_of_flyweights=3,
        arm_mass_per_flyweight_kg=13.646e-3,
        ramp_axial_direction=-1,
        roller_side_sign=1,
        max_tip_mass_per_flyweight_kg=0.650,
    )


def _compiled():
    return compile_path_domain(
        _architecture(),
        (),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=3,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )


def test_condition_request_allows_zero_representatives() -> None:
    request = FixedPivotPathDomainConditionRequest(
        domain_id="domain",
        requirements=[],
        max_tip_mass_per_flyweight_kg=0.300,
        representative_solution_count=0,
    )
    assert request.representative_solution_count == 0


def test_vectorized_requirement_masks_match_scalar_reference() -> None:
    compiled = _compiled()
    layer = 1
    dx = compiled.architecture.required_travel_m / (compiled.shift_station_count - 1)
    shift = (layer + 0.37) * dx
    requirement = ForceRequirement(
        id="mask-check",
        shift_m=shift,
        force_N=250.0,
        shaft_speed_rad_s=3800.0 * 2.0 * pi / 60.0,
        tolerance_N=7.0,
    )
    maximum_mass = 0.300
    count = 257

    vectorized = _requirement_mass_masks_for_layer(
        compiled,
        layer,
        requirement,
        maximum_mass,
        count,
    )
    scalar: list[int] = []
    x0 = layer * dx
    for edge in compiled.viable_edges[layer]:
        template = compiled.templates[edge.template_index]
        segment = PathSegment(
            x0_m=x0,
            x1_m=x0 + dx,
            q0_rad=template.q0_rad,
            q1_rad=template.q1_rad,
            m0_rad_per_m=template.m0_rad_per_m,
            m1_rad_per_m=template.m1_rad_per_m,
        )
        scalar.append(
            _requirement_mass_mask(
                compiled.architecture,
                segment,
                requirement,
                maximum_mass,
                count,
            )
        )

    assert vectorized == scalar
    assert np.count_nonzero(vectorized) >= 0
