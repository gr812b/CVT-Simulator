"""Run: python -m pytest -q tools/sliding_block_demo/test_sliding_block.py"""
from dataclasses import replace

import pytest

from .scenarios import make
from .sliding_block import evaluate, sweep


def test_straight_ramps_reduce_to_messick_and_v4():
    m = make("straight")
    omega = 350.0
    for x in (0.0, 0.004, 0.012, m.x_max):
        p = evaluate(m, x, omega=omega)
        assert p.admissible, p.status
        assert p.r_prime == pytest.approx(0.4, rel=1e-12)
        assert p.z_prime == pytest.approx(0.4, rel=1e-12)
        assert p.r_second == pytest.approx(0, abs=1e-12)
        assert p.M_f_prime == pytest.approx(0, abs=1e-12)
        assert p.F_interface == pytest.approx(m.total_mass * p.radial * 0.4 * omega**2)
        assert p.F_from_contact == pytest.approx(p.F_interface, rel=1e-11)


@pytest.mark.parametrize("name", ["straight", "curved-cup", "both-curved"])
def test_contact_force_matches_v4_even_during_acceleration(name):
    m = make(name)
    for x in (0.0, 0.003, 0.008, m.x_max):
        p = evaluate(m, x, omega=280, alpha=130, xdot=0.11, xddot=-8.0)
        assert p.admissible, (name, x, p.status)
        assert p.N_lower >= 0 and p.N_upper >= 0
        assert p.F_from_contact == pytest.approx(p.F_interface, rel=1e-10, abs=1e-8)
        assert p.J_f_prime**2 <= 4 * p.J_f * p.M_f + 1e-10
        # Power exchanged with mechanism matches -d kinetic energy/dt.
        omega, alpha, xd, xdd = 280, 130, 0.11, -8
        force = p.F_interface
        shaft_reaction = -p.J_f * alpha - p.J_f_prime * xd * omega
        stored_power = (p.M_f * xd * xdd + 0.5 * p.M_f_prime * xd**3
                        + p.J_f * omega * alpha + 0.5 * p.J_f_prime * xd * omega**2)
        assert force * xd + shaft_reaction * omega == pytest.approx(-stored_power, abs=1e-8)


@pytest.mark.parametrize("name", ["curved-cup", "both-curved"])
def test_curved_profile_derivatives_match_finite_difference(name):
    m = make(name)
    h = 2.0e-5
    x = m.x_max / 2
    low, mid, high = (evaluate(m, value) for value in (x - h, x, x + h))
    assert all(p.admissible for p in (low, mid, high))
    assert mid.r_prime == pytest.approx((high.radial - low.radial) / (2*h), rel=6e-4)
    assert mid.z_prime == pytest.approx((high.axial - low.axial) / (2*h), rel=6e-4)
    assert mid.r_second == pytest.approx((high.r_prime - low.r_prime) / (2*h), rel=3e-3)
    assert mid.z_second == pytest.approx((high.z_prime - low.z_prime) / (2*h), rel=3e-3)
    assert mid.M_f_prime == pytest.approx((high.M_f - low.M_f) / (2*h), rel=3e-3)
    assert mid.J_f_prime == pytest.approx((high.J_f - low.J_f) / (2*h), rel=6e-4)


def test_total_mass_count_only_changes_reporting_not_physics():
    original = make("both-curved")
    a = evaluate(replace(original, display_count=1), 0.005)
    b = evaluate(replace(original, display_count=7), 0.005)
    for attr in ("M_f", "M_f_prime", "J_f", "J_f_prime", "N_lower", "N_upper", "F_interface"):
        assert getattr(a, attr) == pytest.approx(getattr(b, attr))
    doubled = evaluate(replace(original, total_mass=2*original.total_mass), 0.005)
    for attr in ("M_f", "M_f_prime", "J_f", "J_f_prime", "N_lower", "N_upper", "F_interface"):
        assert getattr(doubled, attr) == pytest.approx(2 * getattr(a, attr))


def test_negative_contact_reaction_reports_liftoff():
    m = make("both-curved")
    p = evaluate(m, 0.008, omega=25, xddot=200)
    assert not p.admissible
    assert p.N_upper < 0
    assert "liftoff" in p.status
    assert p.F_from_contact == pytest.approx(p.F_interface)


def test_geometry_singularity_and_short_track_are_not_silently_clamped():
    parallel = evaluate(make("parallel"), 0.0)
    assert "ill-conditioned" in parallel.status
    short = sweep(make("short-track"), n=51)
    assert short[0].admissible
    assert not short[-1].admissible
    assert "contact" in short[-1].status or "domain" in short[-1].status


def test_end_contacts_can_be_rejected_if_rounded_nose_not_assumed():
    m = make("straight")
    p = evaluate(m, 0.004, allow_end_contacts=False)
    assert "sharp-end" in p.status
    p2 = evaluate(make("both-curved"), 0.004, allow_end_contacts=False)
    assert p2.admissible


def test_json_config_does_not_silently_calibrate_measured_profiles():
    from dataclasses import asdict
    from .sliding_block import from_mapping
    m = make("both-curved")
    spec = asdict(m)
    reloaded = from_mapping(spec)
    assert evaluate(reloaded, 0.007).admissible
    spec["upper_track"]["offset"] += 0.003
    uncalibrated = evaluate(from_mapping(spec), 0.0)
    assert uncalibrated.admissible  # an altered track may still be feasible
    assert abs(uncalibrated.radial - m.radius_ref) > 0.001
    spec["calibrate_at_zero"] = True
    rezeroed = evaluate(from_mapping(spec), 0.0)
    assert rezeroed.admissible
    assert rezeroed.radial == pytest.approx(m.radius_ref, abs=1e-8)
