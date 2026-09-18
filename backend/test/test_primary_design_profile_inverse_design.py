from __future__ import annotations

from math import pi

import numpy as np

from app.engineering.fixed_pivot_primary.models import ArchitectureDesign, PackagingZone
from app.engineering.fixed_pivot_primary.path_domain import (
    ForceRequirement,
    _path_from_state_indices,
)
from app.engineering.fixed_pivot_primary.path_domain_refinement import condition_path_domain_refined
from app.engineering.fixed_pivot_primary.path_domain_packaging import (
    compile_path_domain_cached_packaging,
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
    return compile_path_domain_cached_packaging(
        _architecture(),
        (),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=4,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )


def _force(path, shift_m: float, mass_kg: float, omega: float) -> float:
    from app.engineering.fixed_pivot_primary.path_domain import _normalized_force_gain

    row = path.evaluate(shift_m)
    arm, tip, _ = _normalized_force_gain(path.architecture, row["q_rad"], row["dq_dx_rad_per_m"])
    return omega * omega * (arm + mass_kg * tip)


def test_soft_profile_guides_do_not_collapse_graph_and_rank_full_curve() -> None:
    compiled = _compiled()
    assert compiled.representative_state_paths
    path = _path_from_state_indices(
        compiled.architecture,
        compiled.states,
        list(compiled.representative_state_paths[0]),
        compiled.shift_station_count,
    )
    omega = 3800.0 * 2.0 * pi / 60.0
    mass = 0.20
    guides = tuple(
        ForceRequirement(
            id=f"guide-{index}",
            shift_m=float(x),
            force_N=_force(path, float(x), mass, omega),
            shaft_speed_rad_s=omega,
            tolerance_N=50.0,
        )
        for index, x in enumerate(np.linspace(0.0, compiled.architecture.required_travel_m, 6))
    )

    result = condition_path_domain_refined(
        compiled,
        guides,
        max_tip_mass_per_flyweight_kg=0.30,
        mass_sample_count=257,
        representative_solution_count=0,
        reference_shaft_speed_rad_s=omega,
    )

    assert result["validity"]["valid"] is True
    assert result["summary"]["profile_guide_count"] == 6
    assert result["summary"]["hard_lock_count"] == 0
    assert result["graph"]["viable_node_counts"] == [len(row) for row in compiled.viable_nodes]
    assert result["representative_solutions"]
    fit = result["representative_solutions"][0]["solution"]["profile_fit"]
    assert fit["rms_error_N"] >= 0.0
    assert fit["max_abs_error_N"] >= fit["rms_error_N"]


def test_packaging_reuses_base_graph_and_caches_zone_mask() -> None:
    architecture = _architecture()
    remote_zone = PackagingZone(
        id="remote",
        label="Remote keep-out",
        subject="ramp",
        rule="forbid",
        polygon_m=((0.20, 0.20), (0.21, 0.20), (0.21, 0.21), (0.20, 0.21)),
        clearance_m=0.0,
    )
    first = compile_path_domain_cached_packaging(
        architecture,
        (remote_zone,),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=4,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )
    second = compile_path_domain_cached_packaging(
        architecture,
        (remote_zone,),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=4,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )
    assert first is second
    assert first.document["graph"]["packaging_reused_base_graph"] is True
    assert first.document["numerics"]["packaging_edge_mask_cached"] is True
