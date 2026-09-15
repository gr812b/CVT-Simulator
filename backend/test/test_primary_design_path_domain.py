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
