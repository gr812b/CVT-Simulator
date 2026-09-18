from __future__ import annotations

from math import pi

import numpy as np

from app.engineering.fixed_pivot_primary.architecture_compare import (
    _directional_witnesses,
    _legendre_coefficient,
)
from app.engineering.fixed_pivot_primary.inverse_design import (
    ForceTargetPoint,
    _build_target,
    _evaluate_candidate,
    _force_denominator,
    _inverse_q_profile,
    _mass_moments,
    _potential,
)
from app.engineering.fixed_pivot_primary.models import ArchitectureDesign


def _architecture() -> ArchitectureDesign:
    return ArchitectureDesign(
        pivot_axial_position_m=0.0,
        pivot_radius_m=42.545e-3,
        arm_length_m=31.5214e-3,
        roller_radius_m=6.5e-3,
        required_travel_m=19.05e-3,
        number_of_flyweights=3,
        arm_mass_per_flyweight_kg=13.646e-3,
        ramp_axial_direction=-1,
        roller_side_sign=1,
        max_tip_mass_per_flyweight_kg=0.650,
    )


def test_appendix_d_analytic_inverse_recovers_q_profile() -> None:
    architecture = _architecture()
    mass = 0.240
    moments = _mass_moments(architecture, mass)
    q0 = np.deg2rad(8.0)
    q = np.deg2rad(np.linspace(8.0, 52.0, 121))
    cumulative = _potential(architecture, moments, q) - _potential(architecture, moments, q0)

    recovered, failure = _inverse_q_profile(architecture, moments, q0, cumulative)

    assert failure is None
    assert recovered is not None
    assert np.max(np.abs(recovered - q)) < 1.0e-10


def test_force_denominator_is_half_Jq_derivative_factor() -> None:
    architecture = _architecture()
    moments = _mass_moments(architecture, 0.180)
    q = np.deg2rad(np.linspace(-10.0, 70.0, 31))
    H = _force_denominator(architecture, moments, q)
    eps = 1.0e-7
    numerical = (
        _potential(architecture, moments, q + eps) - _potential(architecture, moments, q - eps)
    ) / (2.0 * eps)
    assert np.max(np.abs(H - numerical)) < 1.0e-8


def test_legendre_shape_projection_separates_progression_from_curvature() -> None:
    x = np.linspace(-1.0, 1.0, 401)
    p1 = x
    p2 = 0.5 * (3.0 * x * x - 1.0)
    assert abs(_legendre_coefficient(x, p1, 1) - 1.0) < 1.0e-4
    assert abs(_legendre_coefficient(x, p1, 2)) < 1.0e-4
    assert abs(_legendre_coefficient(x, p2, 2) - 1.0) < 1.0e-4
    assert abs(_legendre_coefficient(x, p2, 1)) < 1.0e-4


def test_continuous_inverse_round_trip_reproduces_known_static_force_curve() -> None:
    architecture = _architecture()
    mass = 0.200
    omega = 3800.0 * 2.0 * pi / 60.0
    x = np.linspace(0.0, architecture.required_travel_m, 41)
    q0 = np.deg2rad(9.0)
    q = q0 + np.deg2rad(36.0) * x / architecture.required_travel_m
    qp = np.full_like(q, np.deg2rad(36.0) / architecture.required_travel_m)
    moments = _mass_moments(architecture, mass)
    force = omega * omega * _force_denominator(architecture, moments, q) * qp
    points = tuple(
        ForceTargetPoint(shift_m=float(shift), force_N=float(value))
        for shift, value in zip(x, force, strict=True)
    )
    target = _build_target(points, architecture.required_travel_m)

    candidate, failure = _evaluate_candidate(
        architecture,
        (),
        target,
        omega,
        q0,
        mass,
        181,
    )

    assert failure is None
    assert candidate is not None
    assert candidate.rms_error_N < 0.25
    assert candidate.max_error_N < 1.0


def test_architecture_witness_distance_uses_whole_curve_not_only_low_modes() -> None:
    x = np.linspace(0.0, 1.0, 101)
    z = 2.0 * x - 1.0
    p4 = (35.0 * z**4 - 30.0 * z**2 + 3.0) / 8.0
    flat = np.ones_like(x)
    high_order = 1.0 + 0.25 * p4

    def row(shape: np.ndarray, path_index: int) -> dict[str, object]:
        return {
            "path_index": path_index,
            "shift_fraction": x.tolist(),
            "normalized_shape": shape.tolist(),
            "c1": 0.0,
            "c2": 0.0,
            "c3": 0.0,
        }

    witnesses, stats = _directional_witnesses([row(high_order, 0)], [row(flat, 0)], "A", "B")

    assert witnesses
    assert witnesses[0]["shape_distance"] > 0.05
    assert witnesses[0]["max_pointwise_shape_gap"] > 0.20
    assert stats["max"] == witnesses[0]["shape_distance"]
