"""Phase-3.1/3.2 path-domain and history-certification regression tests.

These tests intentionally import no CINDER mechanics.  They exercise the
standalone graph/history kernel that sits between architecture geometry and the
later exact concrete CINDER certification.
"""

from __future__ import annotations

from math import radians
from types import SimpleNamespace

import numpy as np

from app.engineering.fixed_pivot_primary.models import ArchitectureDesign, PackagingZone
import app.engineering.fixed_pivot_primary.path_domain as domain

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


def _simple_path() -> domain.PiecewiseRampPath:
    architecture = _architecture()
    travel = architecture.required_travel_m
    segment = domain.PathSegment(
        x0_m=0.0,
        x1_m=travel,
        q0_rad=radians(-10.0),
        q1_rad=radians(20.0),
        m0_rad_per_m=radians(30.0) / travel,
        m1_rad_per_m=radians(30.0) / travel,
    )
    return domain.PiecewiseRampPath(architecture, (segment,))


def test_viability_graph_returns_complete_active_paths() -> None:
    result = domain.analyze_path_domain(
        _architecture(),
        (),
        shift_station_count=7,
        q_sample_count=21,
        alpha_sample_count=5,
        representative_path_count=4,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )

    assert result["validity"]["valid"] is True
    assert result["graph"]["local_transition_template_count"] > 0
    assert all(count > 0 for count in result["graph"]["viable_node_counts"])
    assert len(result["representative_paths"]) == 4
    assert all(path["q_deg"][-1] > path["q_deg"][0] for path in result["representative_paths"])


def test_flat_q_boundaries_are_retained_but_active_projection_is_separate() -> None:
    result = domain.analyze_path_domain(
        _architecture(),
        (),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=2,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )
    first = result["graph"]["station_projection"][0]
    assert first["q_min_deg"] <= -29.9
    assert first["active_q_min_deg"] is not None
    assert first["active_q_max_deg"] is not None


def test_packaging_can_remove_the_complete_path_domain() -> None:
    architecture = _architecture()
    # A remote containment box excludes every physical ramp segment.
    wall = PackagingZone(
        id="wall",
        label="Impossible ramp envelope",
        subject="ramp",
        rule="contain",
        polygon_m=(
            (0.20, 0.20),
            (0.21, 0.20),
            (0.21, 0.21),
            (0.20, 0.21),
        ),
    )
    result = domain.analyze_path_domain(
        architecture,
        (wall,),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=2,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )
    assert result["graph"]["viable_node_counts"][0] == 0 or result["validity"]["valid"] is False


def test_history_allows_multiple_mathematical_roots_when_selected_branch_is_continuous(monkeypatch) -> None:
    path = _simple_path()

    def roots_at_shift(_path: domain.PiecewiseRampPath, shift: float):
        intended = path.evaluate(shift)
        roots = [
            domain.ContactRoot(
                parameter_m=shift,
                q_rad=intended["q_rad"],
                roller_center_x_m=intended["roller_center_x_m"],
                roller_center_r_m=intended["roller_center_r_m"],
            )
        ]
        if shift <= 0.75 * path.x_max_m:
            alt_s = min(path.x_max_m, shift + 0.004)
            alt = path.evaluate(alt_s)
            roots.append(
                domain.ContactRoot(
                    parameter_m=alt_s,
                    q_rad=intended["q_rad"] + radians(25.0),
                    roller_center_x_m=alt["roller_center_x_m"],
                    roller_center_r_m=alt["roller_center_r_m"],
                )
            )
        return roots

    monkeypatch.setattr(domain, "_contact_roots_at_shift", roots_at_shift)
    certification = domain._trace_history_selected_branch(path, 65)
    assert certification.valid is True
    assert certification.max_contact_root_count == 2
    assert certification.multiple_root_shift_count > 0


def test_history_selects_lowest_q_initial_contact_instead_of_arbitrary_root(monkeypatch) -> None:
    path = _simple_path()

    def roots_at_shift(_path: domain.PiecewiseRampPath, shift: float):
        intended = path.evaluate(shift)
        intended_root = domain.ContactRoot(
            parameter_m=shift,
            q_rad=intended["q_rad"],
            roller_center_x_m=intended["roller_center_x_m"],
            roller_center_r_m=intended["roller_center_r_m"],
        )
        if abs(shift) < 1.0e-12:
            other = path.evaluate(0.004)
            return [
                intended_root,
                domain.ContactRoot(
                    parameter_m=0.004,
                    q_rad=intended["q_rad"] - radians(5.0),
                    roller_center_x_m=other["roller_center_x_m"],
                    roller_center_r_m=other["roller_center_r_m"],
                ),
            ]
        return [intended_root]

    monkeypatch.setattr(domain, "_contact_roots_at_shift", roots_at_shift)
    certification = domain._trace_history_selected_branch(path, 65)
    assert certification.valid is False
    assert certification.failure is not None
    assert certification.failure.code == "INITIAL_BRANCH_NOT_SELECTED"


class _BowTiePath:
    """Continuous synthetic path with a nonlocal centre self-intersection."""

    def __init__(self) -> None:
        self.architecture = _architecture()
        self.x_min_m = 0.0
        self.x_max_m = 1.0
        self.segments = (
            SimpleNamespace(x0_m=0.0, x1_m=1.0 / 3.0),
            SimpleNamespace(x0_m=1.0 / 3.0, x1_m=2.0 / 3.0),
            SimpleNamespace(x0_m=2.0 / 3.0, x1_m=1.0),
        )
        self._knots = np.asarray([0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0])
        self._points = np.asarray([
            [0.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0],
            [1.0, 0.0],
        ])

    def evaluate(self, s: float):
        s = float(min(max(s, 0.0), 1.0))
        index = min(np.searchsorted(self._knots, s, side="right") - 1, 2)
        index = max(index, 0)
        a = self._knots[index]
        b = self._knots[index + 1]
        t = (s - a) / (b - a)
        point = (1.0 - t) * self._points[index] + t * self._points[index + 1]
        return {
            "q_rad": 0.0,
            "roller_center_x_m": float(point[0]),
            "roller_center_r_m": float(point[1]),
            "contact_x_m": float(point[0] + 2.0),
            "contact_r_m": float(point[1]),
        }


def test_one_roller_pose_with_two_distinct_contacts_is_rejected() -> None:
    path = _BowTiePath()
    certification = domain.certify_path_history(path, trace_sample_count=65, broad_phase_samples_per_segment=33)
    assert certification.valid is False
    assert certification.failure is not None
    assert certification.failure.code == "SECOND_SIMULTANEOUS_CONTACT"
    assert certification.failure.first_parameter_m is not None
    assert certification.failure.second_parameter_m is not None
    assert abs(certification.failure.second_parameter_m - certification.failure.first_parameter_m) > 0.1


def test_generated_path_has_exact_designed_contact_root_s_equal_x() -> None:
    path = _simple_path()
    for shift in np.linspace(0.0, path.x_max_m, 17):
        roots = domain._contact_roots_at_shift(path, float(shift))
        assert roots
        assert min(abs(root.parameter_m - shift) for root in roots) < 1.0e-10


def test_local_edge_acceptance_survives_independent_dense_audit() -> None:
    architecture = _architecture()
    states = domain._build_states(architecture, 17, 5)
    dx = architecture.required_travel_m / 4.0
    templates = domain._build_edge_templates(
        architecture,
        states,
        dx,
        edge_audit_sample_count=65,
    )
    assert templates

    # Independent grid is far denser than the acceptance bracket grid.  This
    # regression guards against the narrow fold/tangent overshoot that motivated
    # the Phase-3.1 continuous edge audit.
    xs = np.linspace(0.0, dx, 4097)
    for template in templates:
        segment = domain.PathSegment(
            0.0,
            dx,
            template.q0_rad,
            template.q1_rad,
            template.m0_rad_per_m,
            template.m1_rad_per_m,
        )
        rows = [domain._segment_constraint_row(architecture, segment, float(x)) for x in xs]
        values = np.asarray(rows)
        assert np.min(values[:, 0]) >= -1.0e-8
        assert np.min(values[:, 1]) > 0.0
        assert np.min(values[:, 2]) > 0.0
        assert np.min(values[:, 3]) >= -1.0e-5


def test_domain_projection_and_normalized_force_capability_are_returned() -> None:
    result = domain.analyze_path_domain(
        _architecture(),
        (),
        shift_station_count=7,
        q_sample_count=21,
        alpha_sample_count=5,
        representative_path_count=3,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )

    projection = result["domain_projection"]
    assert projection["point_count"] > 0
    points = projection["ramp_surface_points"]
    assert len(points["x_m"]) == projection["point_count"]
    assert len(points["r_m"]) == projection["point_count"]
    assert projection["visual_radius_m"] > 0.0

    capability = result["capability"]
    assert len(capability["stations"]) == 7
    active_stations = [row for row in capability["stations"] if row["active_state_count"] > 0]
    assert active_stations
    for row in active_stations:
        assert row["tip_force_per_omega2_per_kg_max"] is not None
        assert row["tip_force_per_omega2_per_kg_max"] >= 0.0
        assert row["max_tip_total_force_per_omega2_max"] is not None
        assert row["max_tip_total_force_per_omega2_max"] >= 0.0

    for path in result["representative_paths"]:
        assert len(path["capability"]["tip_force_per_omega2_per_kg"]) == len(path["shift_m"])
        assert len(path["capability"]["arm_force_per_omega2"]) == len(path["shift_m"])


def test_normalized_force_gain_matches_finite_difference_of_mass_model() -> None:
    architecture = _architecture()
    q = radians(22.0)
    dq_dx = 31.0
    arm_gain, tip_gain_per_kg, total_gain = domain._normalized_force_gain(
        architecture, q, dq_dx
    )

    count = architecture.number_of_flyweights
    pivot = architecture.pivot_radius_m
    length = architecture.arm_length_m
    arm_mass = architecture.arm_mass_per_flyweight_kg

    def shaft_inertia(angle: float, tip_mass: float) -> float:
        # Uniform arm integrated along its length plus a point end mass.
        s = np.sin(angle)
        arm = arm_mass * (
            pivot * pivot
            + pivot * length * s
            + (length * length / 3.0) * s * s
        )
        tip = tip_mass * (pivot + length * s) ** 2
        return count * (arm + tip)

    eps = 1.0e-7
    d_j_d_q_arm = (shaft_inertia(q + eps, 0.0) - shaft_inertia(q - eps, 0.0)) / (2.0 * eps)
    d_j_d_q_with_unit_tip = (
        shaft_inertia(q + eps, 1.0) - shaft_inertia(q - eps, 1.0)
    ) / (2.0 * eps)
    expected_arm = 0.5 * d_j_d_q_arm * dq_dx
    expected_tip_per_kg = 0.5 * (d_j_d_q_with_unit_tip - d_j_d_q_arm) * dq_dx

    assert np.isclose(arm_gain, expected_arm, rtol=2.0e-7, atol=1.0e-12)
    assert np.isclose(tip_gain_per_kg, expected_tip_per_kg, rtol=2.0e-7, atol=1.0e-12)
    assert np.isclose(
        total_gain,
        arm_gain + architecture.max_tip_mass_per_flyweight_kg * tip_gain_per_kg,
        rtol=1.0e-12,
        atol=1.0e-12,
    )


def _small_compiled_domain() -> domain.CompiledPathDomain:
    return domain.compile_path_domain(
        _architecture(),
        (),
        shift_station_count=5,
        q_sample_count=17,
        alpha_sample_count=5,
        representative_path_count=4,
        edge_audit_sample_count=65,
        history_trace_sample_count=65,
    )


def _force_on_path(
    path: domain.PiecewiseRampPath,
    shift_m: float,
    tip_mass_kg: float,
    shaft_speed_rad_s: float,
) -> float:
    row = path.evaluate(shift_m)
    arm, tip, _ = domain._normalized_force_gain(
        path.architecture,
        row["q_rad"],
        row["dq_dx_rad_per_m"],
    )
    return shaft_speed_rad_s ** 2 * (arm + tip_mass_kg * tip)


def test_force_conditioning_without_requirements_retains_complete_domain() -> None:
    compiled = _small_compiled_domain()
    result = domain.condition_path_domain(
        compiled,
        (),
        max_tip_mass_per_flyweight_kg=0.300,
        mass_sample_count=257,
    )
    assert result["validity"]["valid"] is True
    assert result["summary"]["requirement_count"] == 0
    assert result["graph"]["viable_node_counts"] == [len(row) for row in compiled.viable_nodes]
    assert result["mass"]["surviving_mass_min_kg"] == 0.0
    assert np.isclose(result["mass"]["surviving_mass_max_kg"], 0.300)


def test_one_force_point_returns_ramp_plus_mass_solutions() -> None:
    compiled = _small_compiled_domain()
    state_path = compiled.representative_state_paths[0]
    path = domain._path_from_state_indices(
        compiled.architecture,
        compiled.states,
        list(state_path),
        compiled.shift_station_count,
    )
    omega = 3600.0 * 2.0 * np.pi / 60.0
    mass = 0.180
    shift = 0.45 * compiled.architecture.required_travel_m
    force = _force_on_path(path, shift, mass, omega)
    requirement = domain.ForceRequirement("p1", shift, force, omega, 2.0)
    result = domain.condition_path_domain(
        compiled,
        (requirement,),
        max_tip_mass_per_flyweight_kg=0.300,
        mass_sample_count=513,
    )
    assert result["validity"]["valid"] is True
    assert result["requirements"][0]["individually_attainable"] is True
    assert result["representative_solutions"]
    solution = result["representative_solutions"][0]["solution"]
    assert solution["tip_mass_min_kg"] <= mass <= solution["tip_mass_max_kg"]


def test_two_points_from_one_ramp_and_one_mass_remain_jointly_feasible() -> None:
    compiled = _small_compiled_domain()
    state_path = compiled.representative_state_paths[0]
    path = domain._path_from_state_indices(
        compiled.architecture,
        compiled.states,
        list(state_path),
        compiled.shift_station_count,
    )
    omega = 3800.0 * 2.0 * np.pi / 60.0
    mass = 0.220
    shifts = [0.25, 0.72]
    requirements = tuple(
        domain.ForceRequirement(
            f"p{index}",
            fraction * compiled.architecture.required_travel_m,
            _force_on_path(path, fraction * compiled.architecture.required_travel_m, mass, omega),
            omega,
            3.0,
        )
        for index, fraction in enumerate(shifts)
    )
    result = domain.condition_path_domain(
        compiled,
        requirements,
        max_tip_mass_per_flyweight_kg=0.300,
        mass_sample_count=513,
    )
    assert result["validity"]["valid"] is True
    assert result["summary"]["jointly_feasible"] is True
    assert result["representative_solutions"]
    intervals = [entry["solution"] for entry in result["representative_solutions"]]
    assert any(item["tip_mass_min_kg"] <= mass <= item["tip_mass_max_kg"] for item in intervals)


def test_individually_attainable_points_can_be_jointly_incompatible() -> None:
    compiled = _small_compiled_domain()
    omega = 3800.0 * 2.0 * np.pi / 60.0
    # Search deterministic station-envelope extrema until a pair is found whose
    # individual constraints are possible but whose shared-mass path set is empty.
    full = domain.condition_path_domain(
        compiled,
        (),
        max_tip_mass_per_flyweight_kg=0.300,
        mass_sample_count=257,
    )
    stations = full["force_capability"]["full"]["stations"]
    found = None
    active = [row for row in stations[1:-1] if row["force_min_N"] is not None]
    for left in active:
        for right in active:
            if right["station"] <= left["station"]:
                continue
            candidates = [
                (left["force_min_N"], right["force_max_N"]),
                (left["force_max_N"], right["force_min_N"]),
            ]
            for f1, f2 in candidates:
                reqs = (
                    domain.ForceRequirement("a", left["shift_m"], float(f1), omega, 1.0),
                    domain.ForceRequirement("b", right["shift_m"], float(f2), omega, 1.0),
                )
                result = domain.condition_path_domain(
                    compiled,
                    reqs,
                    max_tip_mass_per_flyweight_kg=0.300,
                    mass_sample_count=257,
                )
                if all(row["individually_attainable"] for row in result["requirements"]) and not result["summary"]["jointly_feasible"]:
                    found = result
                    break
            if found is not None:
                break
        if found is not None:
            break
    assert found is not None
    assert found["validity"]["valid"] is False
    assert found["validity"]["findings"][0]["code"] == "REQUIREMENTS_JOINTLY_INCOMPATIBLE"


def test_force_point_outside_full_capability_is_rejected() -> None:
    compiled = _small_compiled_domain()
    omega = 3800.0 * 2.0 * np.pi / 60.0
    shift = 0.5 * compiled.architecture.required_travel_m
    full = domain.condition_path_domain(
        compiled,
        (),
        max_tip_mass_per_flyweight_kg=0.250,
        mass_sample_count=257,
    )
    middle = full["force_capability"]["full"]["stations"][2]
    impossible = float(middle["force_max_N"]) + 1000.0
    result = domain.condition_path_domain(
        compiled,
        (domain.ForceRequirement("outside", shift, impossible, omega, 1.0),),
        max_tip_mass_per_flyweight_kg=0.250,
        mass_sample_count=257,
    )
    assert result["validity"]["valid"] is False
    assert result["requirements"][0]["individually_attainable"] is False
    assert result["validity"]["findings"][0]["code"] == "INDIVIDUAL_REQUIREMENT_OUTSIDE_CAPABILITY"
