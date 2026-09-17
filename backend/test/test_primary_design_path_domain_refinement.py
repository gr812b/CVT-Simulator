"""Regression tests for refined Phase-3.5 force-domain presentation/search."""

from __future__ import annotations

from math import pi

from app.engineering.fixed_pivot_primary.models import ArchitectureDesign
from app.engineering.fixed_pivot_primary.path_domain import ForceRequirement, _normalized_force_gain
from app.engineering.fixed_pivot_primary.path_domain_refinement import (
    _mask_runs,
    _merge_intervals,
    condition_path_domain_refined,
    refresh_compiled_domain_views,
)
from app.engineering.fixed_pivot_primary.path_domain import (
    compile_path_domain,
    _path_from_state_indices,
)

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
        representative_path_count=4,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )


def test_interval_merge_preserves_real_holes() -> None:
    assert _merge_intervals([(10.0, 20.0), (18.0, 30.0), (50.0, 70.0)]) == [
        (10.0, 30.0),
        (50.0, 70.0),
    ]


def test_mass_mask_runs_preserve_disconnected_mass_sets() -> None:
    mask = 0b111001110011
    assert _mask_runs(mask) == [(0, 1), (4, 6), (9, 11)]


def test_refreshed_architecture_capability_is_densely_edge_sampled() -> None:
    compiled = _compiled()
    refresh_compiled_domain_views(compiled, representative_count=6, capability_samples_per_layer=9)
    stations = compiled.document["capability"]["stations"]
    assert len(stations) > compiled.shift_station_count
    assert len(compiled.document["representative_paths"]) <= 6
    assert len(compiled.document["representative_paths"]) > 0


def test_conditioned_solution_examples_are_extracted_from_conditioned_graph() -> None:
    compiled = _compiled()
    assert compiled.representative_state_paths
    state_path = compiled.representative_state_paths[0]
    path = _path_from_state_indices(
        compiled.architecture,
        compiled.states,
        list(state_path),
        compiled.shift_station_count,
    )
    omega = 3800.0 * 2.0 * pi / 60.0
    mass = 0.200
    shifts = (
        0.35 * compiled.architecture.required_travel_m,
        0.70 * compiled.architecture.required_travel_m,
    )
    requirements = []
    for index, shift in enumerate(shifts):
        row = path.evaluate(shift)
        arm, tip, _ = _normalized_force_gain(
            compiled.architecture,
            row["q_rad"],
            row["dq_dx_rad_per_m"],
        )
        force = omega * omega * (arm + mass * tip)
        requirements.append(
            ForceRequirement(
                id=f"p{index}",
                shift_m=shift,
                force_N=force,
                shaft_speed_rad_s=omega,
                tolerance_N=3.0,
            )
        )

    result = condition_path_domain_refined(
        compiled,
        tuple(requirements),
        max_tip_mass_per_flyweight_kg=0.300,
        mass_sample_count=257,
        representative_solution_count=6,
        reference_shaft_speed_rad_s=omega,
        force_samples_per_layer=9,
    )
    assert result["summary"]["jointly_feasible"] is True
    assert result["representative_solutions"]
    for solution in result["representative_solutions"]:
        assert solution["solution"]["tip_mass_min_kg"] <= solution["solution"]["tip_mass_max_kg"]


def test_force_projection_exposes_interval_union_for_frontend_hit_testing() -> None:
    compiled = _compiled()
    omega = 3800.0 * 2.0 * pi / 60.0
    result = condition_path_domain_refined(
        compiled,
        (),
        max_tip_mass_per_flyweight_kg=0.300,
        mass_sample_count=257,
        representative_solution_count=4,
        reference_shaft_speed_rad_s=omega,
        force_samples_per_layer=9,
    )
    stations = result["force_capability"]["full"]["stations"]
    assert stations
    assert all("force_intervals_N" in row for row in stations)
    assert any(row["force_intervals_N"] for row in stations)
