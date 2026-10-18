"""Independent geometry/particle checks for user-defined contact sections."""

from dataclasses import replace
import json

import numpy as np
from numpy.polynomial import Polynomial
import pytest
from scipy.optimize import brentq, minimize_scalar

from cinder.model.cvt.actuation import (
    SlidingBlockFlyweightForce,
    SlidingBlockGeometry,
    SlidingBlockMass,
    SlidingBlockProfile as Profile,
    SlidingBlockSpec,
)
from cinder.model.cvt.actuation.sliding_block_geometry import (
    Mechanism,
    _gap_minima,
    calibrate_zero,
    evaluate,
)
from cinder.contracts.document import _decode_force_law, _encode_force_law
from cinder.contracts.schema import assembly_document_json_schema


def polynomial_profile(poly, left, right):
    variable = Polynomial([left, right - left])
    return Profile(
        "spline",
        0,
        left=left,
        right=right,
        knots=(left, right),
        coefficients=(tuple(poly(variable).coef),),
    )


def mass():
    return SlidingBlockMass(
        0.6, 3, (0, 0, 0), ((1e-4, 0, 8e-6), (0, 1e-4, 0), (8e-6, 0, 1e-4))
    )


def two_point_spec():
    u = Polynomial([0, 1])
    lower = polynomial_profile(0.8 * u + 1e6 * (u * u - 0.004**2) ** 2, -0.01, 0.01)
    upper = Profile("line", 0, offset=0.035, slope=-0.5, left=-0.01, right=0.01)
    cup = Profile("line", 0.05, slope=0.8, left=0.02, right=0.1)
    ramp = Profile("line", 0.05, offset=0.035, slope=-0.5, left=0.02, right=0.1)
    return SlidingBlockSpec(
        SlidingBlockGeometry(cup, ramp, lower, upper, 0.049, 0.065, 0, 0.015),
        mass(),
        "ideal_fixed_orientation",
    )


def curved_spec():
    r = Polynomial([0, 1])
    d = r - 0.05
    cup = polynomial_profile(0.8 * d - 1e5 * d**4, 0.02, 0.09)
    lower = Profile("quadratic", 0, slope=0.8, curvature=2000, left=-0.006, right=0.006)
    upper = Profile("line", 0, offset=0.08, slope=-0.5, left=-0.006, right=0.006)
    ramp = Profile("line", 0.05, offset=0.08, slope=-0.5, left=0.02, right=0.09)
    mechanism = calibrate_zero(
        Mechanism(cup, ramp, lower, upper, 0.6, 0.01, radius_ref=0.05, x_max=0.012)
    )
    return SlidingBlockSpec(
        SlidingBlockGeometry(
            mechanism.lower_track,
            mechanism.upper_track,
            lower,
            upper,
            0.049,
            0.061,
            0,
            0.012,
        ),
        mass(),
        "ideal_fixed_orientation",
    )


def test_nonconvex_two_point_contact_and_flat_face_have_analytic_clamping():
    spec = two_point_spec()
    mapping = SlidingBlockFlyweightForce(spec).inertia_map
    for x in np.linspace(0, 0.015, 17):
        p = mapping.pose(x)
        assert p.radial == pytest.approx(0.05 + x / 1.3, abs=2e-14)
        assert p.axial == pytest.approx(0.8 * x / 1.3, abs=2e-14)
        assert p.r_prime == pytest.approx(1 / 1.3, abs=2e-12)
        assert p.z_prime == pytest.approx(0.8 / 1.3, abs=2e-12)
        assert len(p.lower.u_intervals) == 2
        np.testing.assert_allclose(
            p.lower.u_intervals, ((-0.004, -0.004), (0.004, 0.004)), atol=2e-13
        )
        np.testing.assert_allclose(p.upper.u_intervals, ((-0.01, 0.01),), atol=2e-13)
        sample = mapping.evaluate(x)
        assert sample.effective_mass == pytest.approx(0.6 * (1 + 0.8**2) / 1.3**2)
        assert sample.effective_mass_gradient == pytest.approx(0, abs=1e-8)
        for omega in (-300, 0, 300):
            reactions = mapping.reactions(x, omega=omega, alpha=0, xdot=0, xddot=0)
            expected_force = 0.6 * p.radial * omega**2 / 1.3
            assert -reactions.upper_normal * p.upper.normal[1] == pytest.approx(
                expected_force, abs=1e-10
            )
            assert 0.5 * sample.shaft_inertia_gradient * omega**2 == pytest.approx(
                expected_force
            )
            assert reactions.compressive
            if omega:
                assert reactions.guide_moment is None
                assert reactions.per_block_guide_moment is None
            else:
                assert reactions.guide_moment == (0.0, 0.0, 0.0)


def test_unknown_pressure_location_returns_exact_guide_moment_range_and_impulses():
    mapping = SlidingBlockFlyweightForce(two_point_spec()).inertia_map
    p = mapping.pose(0.0075)
    cases = [
        mapping.reactions(0.0075, omega=300, alpha=40, xdot=0.1, xddot=3),
        mapping.impulses(0.0075, delta_xdot=0.1, delta_omega=20),
    ]
    for result in cases:
        tensor = 0.6 * np.array(mapping.spec.mass.centroidal_inertia_per_mass)
        if result is cases[0]:
            spin = np.array([0, 0, 300])
            spin_acc = np.array([0, 0, 40])
            inertial = tensor @ spin_acc + np.cross(spin, tensor @ spin)
        else:
            inertial = tensor @ np.array([0, 0, 20])
        values = []
        for a in (-0.004, 0.004):
            for b in (-0.01, 0.01):
                moment = inertial.copy()
                for contact, u, n in zip(
                    (p.lower, p.upper),
                    (a, b),
                    (result.lower_normal, result.upper_normal),
                ):
                    r = p.datum_radial + u
                    z = contact.axial + contact.slope * (u - contact.u)
                    moment -= np.cross(
                        (r - p.radial, 0, z - p.axial),
                        n * np.array((contact.normal[0], 0, contact.normal[1])),
                    )
                values.append(moment)
        expected = np.column_stack((np.min(values, axis=0), np.max(values, axis=0)))
        np.testing.assert_allclose(result.guide_moment_bounds, expected, atol=1e-11)
        np.testing.assert_allclose(
            result.per_block_guide_moment_bounds, expected / 3, atol=1e-11
        )
        assert result.guide_moment_bounds[1][1] - result.guide_moment_bounds[1][0] > 0


def test_variable_curvature_cup_matches_independent_contact_and_particle_work(
    monkeypatch,
):
    spec = curved_spec()
    mapping = SlidingBlockFlyweightForce(spec).inertia_map
    # These track-wide slope ranges overlap. Active-contact enclosures must
    # establish the regular branch without requiring a monotone-slope profile.
    assert spec.geometry.lower_track.bounds(0.043, 0.067, 1)[0] < -0.5

    # Separate geometry construction: unconstrained scalar minimization of the
    # strictly convex physical gap. It does not call CINDER's candidate search.
    def position(x):
        def geometry(r):
            result = minimize_scalar(
                lambda u: 0.8 * u
                + 1000 * u * u
                - (0.8 * (r + u - 0.05) - 1e5 * (r + u - 0.05) ** 4),
                bounds=(-0.006, 0.006),
                method="bounded",
                options={"xatol": 1e-15},
            )
            z = -result.fun
            return z + 0.5 * (r - 0.05), z

        r = brentq(lambda r: geometry(r)[0] - x, 0.049, 0.061, xtol=1e-15)
        return np.array((r, 0, geometry(r)[1]))

    offsets = np.array(
        [
            (a, b, c)
            for a in (-0.004, 0.004)
            for b in (-0.006, 0.006)
            for c in (-0.003, 0.003)
        ]
    )
    oracle_mass = replace(
        spec.mass,
        centroidal_inertia_per_mass=(
            (0.006**2 + 0.003**2, 0, 0),
            (0, 0.004**2 + 0.003**2, 0),
            (0, 0, 0.004**2 + 0.006**2),
        ),
    )
    mapping = SlidingBlockFlyweightForce(replace(spec, mass=oracle_mass)).inertia_map
    x, xd, xdd, omega, alpha = 0.006, 0.08, -2.0, 250.0, 50.0
    h = 2e-5

    def positions(dt):
        local = position(x + xd * dt + 0.5 * xdd * dt * dt) + offsets
        angle = omega * dt + 0.5 * alpha * dt * dt
        c, s = np.cos(angle), np.sin(angle)
        return local @ np.array(((c, -s, 0), (s, c, 0), (0, 0, 1))).T

    points = {i: positions(i * h) for i in (-2, -1, 0, 1, 2)}
    acceleration = (
        -points[2] + 16 * points[1] - 30 * points[0] + 16 * points[-1] - points[-2]
    ) / (12 * h * h)
    displacement = (position(x + 1e-6) - position(x - 1e-6)) / 2e-6
    particle_force = -0.6 / 8 * np.sum(acceleration * displacement)
    particle_torque = -0.6 / 8 * np.sum(np.cross(points[0], acceleration)[:, 2])
    sample = mapping.evaluate(x)
    expected = (
        0.5 * sample.shaft_inertia_gradient * omega**2
        - sample.effective_mass * xdd
        - 0.5 * sample.effective_mass_gradient * xd**2
    )
    assert expected == pytest.approx(particle_force, rel=2e-5, abs=0.02)
    assert (
        -sample.shaft_inertia * alpha - sample.shaft_inertia_gradient * xd * omega
        == pytest.approx(particle_torque, rel=2e-5, abs=2e-5)
    )
    np.testing.assert_allclose(
        (mapping.pose(x).radial, 0, mapping.pose(x).axial), position(x), atol=3e-11
    )
    from cinder.model.cvt.actuation import sliding_block

    monkeypatch.setattr(
        sliding_block,
        "brentq",
        lambda *a, **kw: pytest.fail("geometry solve in runtime"),
    )
    for x in np.linspace(0, 0.012, 21):
        mapping.evaluate(float(x))
        mapping.pose(float(x))
        assert mapping.reactions(
            float(x), omega=300, alpha=10, xdot=0.01, xddot=0
        ).compressive


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6, 7, 13])
def test_point_input_interpolates_every_point_and_has_consistent_derivatives(count):
    points = [
        (r, 0.3 * r + 10 * r * r + 1e5 * r**5) for r in np.linspace(-0.01, 0.01, count)
    ]
    p = Profile.from_points(points)
    assert hash(p)
    for r, z in points:
        assert p.value(r) == pytest.approx(z, abs=2e-14)
    for r in np.linspace(-0.009, 0.009, 11):
        h = 1e-7
        assert p.gradient(r) == pytest.approx(
            (p.value(r + h) - p.value(r - h)) / (2 * h), rel=1e-7, abs=1e-9
        )
        assert p.second(r) == pytest.approx(
            (p.gradient(r + h) - p.gradient(r - h)) / (2 * h), rel=1e-7, abs=1e-8
        )
        if not any(abs(r - k) < 2 * h for k in p.knots[1:-1]):
            assert p.derivative(r, 3) == pytest.approx(
                (p.second(r + h) - p.second(r - h)) / (2 * h), rel=1e-6, abs=2e-5
            )
    low, high = p.bounds(-0.01, 0.01, 1)
    slopes = [p.gradient(float(r)) for r in np.linspace(-0.01, 0.01, 1001)]
    assert min(slopes) >= low - 1e-12 and max(slopes) <= high + 1e-12


@pytest.mark.parametrize("arc_first", [True, False])
def test_global_search_of_arc_polynomial_gap_matches_independent_minima(arc_first):
    u = Polynomial([0, 1])
    wave = polynomial_profile(1e6 * (u * u - 0.004**2) ** 2 + 0.1 * u, -0.01, 0.01)
    arc = Profile("circle", -0.002, radius=0.02, left=-0.01, right=0.01)
    top, bottom = (arc, wave) if arc_first else (wave, arc)
    minimum, spans = _gap_minima(top, bottom, 0, -0.01, 0.01)

    def f(r):
        return top.value(float(r)) - bottom.value(float(r))

    grid = np.linspace(-0.01, 0.01, 1001)
    candidates = [f(grid[0]), f(grid[-1])]
    for i in range(1, len(grid) - 1):
        if f(grid[i]) <= min(f(grid[i - 1]), f(grid[i + 1])):
            candidates.append(
                minimize_scalar(
                    f,
                    bounds=(grid[i - 1], grid[i + 1]),
                    method="bounded",
                    options={"xatol": 1e-15},
                ).fun
            )
    assert minimum == pytest.approx(min(candidates), abs=2e-13)
    for a, b in spans:
        assert f((a + b) / 2) == pytest.approx(minimum, abs=2e-13)


def test_opposite_circle_branches_do_not_lose_the_central_stationary_point():
    a = Profile("circle", 0, radius=0.02, left=-0.01, right=0.01)
    b = replace(a, circle_sign=-1)
    value, spans = _gap_minima(a, b, 0, -0.01, 0.01)
    assert value == pytest.approx(0, abs=1e-14)
    np.testing.assert_allclose(spans, ((0, 0),), atol=1e-13)


def test_uniform_arbitrary_polygon_mass_matches_sum_of_two_cuboids():
    outline = [(0, 0), (0.03, 0), (0.03, 0.01), (0.01, 0.01), (0.01, 0.04), (0, 0.04)]
    # Two non-overlapping rectangles form this concave L section.
    rectangles = [(0.03, 0.01, (0.015, 0.005)), (0.01, 0.03, (0.005, 0.025))]
    area = sum(w * h for w, h, _ in rectangles)
    centre = sum(w * h * np.array(c) for w, h, c in rectangles) / area
    covariance = np.zeros((2, 2))
    for w, h, c in rectangles:
        delta = np.array(c) - centre
        covariance += (
            w * h * (np.diag((w * w / 12, h * h / 12)) + np.outer(delta, delta)) / area
        )
    expected = np.array(
        (
            (0.02**2 / 12 + covariance[1, 1], 0, -covariance[0, 1]),
            (0, np.trace(covariance), 0),
            (-covariance[0, 1], 0, covariance[0, 0] + 0.02**2 / 12),
        )
    )
    for points in (outline, list(reversed(outline)), outline + [outline[0]]):
        result = SlidingBlockMass.from_section(
            points, width=0.02, total_mass=0.6, count=3
        )
        np.testing.assert_allclose(
            result.com_offset, (centre[0], 0, centre[1]), atol=1e-16
        )
        np.testing.assert_allclose(
            result.centroidal_inertia_per_mass, expected, atol=1e-16
        )
        assert result.total_mass == 0.6
    with pytest.raises(ValueError, match="intersects"):
        SlidingBlockMass.from_section(
            [(0, 0), (1, 1), (0, 1), (1, 0)], width=0.02, total_mass=0.6
        )


def test_new_profiles_round_trip_in_json_and_legacy_documents_keep_their_shape():
    import jsonschema

    for spec in (two_point_spec(), curved_spec()):
        record = _encode_force_law(SlidingBlockFlyweightForce(spec))
        schema = assembly_document_json_schema()
        jsonschema.validate(
            record, {"$defs": schema["$defs"], "$ref": "#/$defs/assemblySlidingBlock"}
        )
        restored = _decode_force_law(json.loads(json.dumps(record)))
        assert _encode_force_law(restored) == record
        for x in (0, 0.006, 0.012):
            assert restored.inertia_map.evaluate(x) == SlidingBlockFlyweightForce(
                spec
            ).inertia_map.evaluate(x)
        # A legacy line remains the same record; no unused spline fields leak.
        assert "knots" not in record["geometry"]["upper_track"]
    p = Profile.from_points([(0, 0), (0.01, 0.02)])
    with pytest.raises(ValueError, match="ordered"):
        replace(p, knots=(0.01, 0))
    with pytest.raises(ValueError, match="C2"):
        Profile(
            "spline", 0, left=0, right=2, knots=(0, 1, 2), coefficients=((0, 1), (5, 1))
        )


def test_inspection_does_not_invent_a_pressure_centroid_or_guide_couple():
    spec = two_point_spec()
    m = replace(spec.geometry.mechanism(), total_mass=0.6, gyration_radius=0.01)
    p = evaluate(m, 0.0075, omega=300)
    assert p.admissible
    assert p.guide_rocking_moment is None
    assert p.lower.u_intervals and p.upper.u_intervals


def test_hidden_competing_minima_transition_is_not_admitted_by_sampling():
    from cinder.model.cvt.actuation import SlidingBlockGeometryError

    spec = two_point_spec()
    g = spec.geometry
    curved = replace(g.lower_track, kind="quadratic", curvature=10)
    m = calibrate_zero(
        Mechanism(
            curved,
            g.upper_track,
            g.lower_face,
            g.upper_face,
            0.6,
            0.01,
            radius_ref=0.04573,
            x_max=0.015,
        )
    )
    g = replace(
        g,
        lower_track=m.lower_track,
        upper_track=m.upper_track,
        radial_min=0.044,
        radial_max=0.064,
    )
    with pytest.raises(SlidingBlockGeometryError) as failure:
        SlidingBlockFlyweightForce(replace(spec, geometry=g))
    assert failure.value.category == "numerical"
    assert failure.value.code == "contact_regularity"
    assert failure.value.contact == "lower"
    assert failure.value.radial_interval is not None


def test_smooth_arc_mass_moments_match_truncated_half_disc_in_closed_form():
    radius = 0.02
    a = 0.9999 * radius
    lower = Profile("circle", 0, offset=-radius, radius=radius, left=-a, right=a)
    upper = Profile("line", 0, left=-a, right=a)
    result = SlidingBlockMass.from_profiles(
        lower, upper, width=0.018, total_mass=0.6, count=3
    )
    angle = np.arcsin(a / radius)
    area = a * np.sqrt(radius**2 - a * a) + radius**2 * angle
    centre_z = -(radius**2 * a - a**3 / 3) / area
    raw_r2 = radius**4 * (angle / 4 - np.sin(4 * angle) / 16) / area
    raw_z2 = (
        radius**4 * (angle / 4 + np.sin(2 * angle) / 6 + np.sin(4 * angle) / 48) / area
    )
    vt = 0.018**2 / 12
    expected = np.diag(
        (vt + raw_z2 - centre_z**2, raw_r2 + raw_z2 - centre_z**2, vt + raw_r2)
    )
    np.testing.assert_allclose(result.com_offset, (0, 0, centre_z), atol=2e-14)
    np.testing.assert_allclose(result.centroidal_inertia_per_mass, expected, atol=2e-16)
    assert result.total_mass == 0.6
    assert result.count == 3


@pytest.mark.parametrize("degree", [3, 5])
def test_compiled_multi_piece_point_profile_and_all_runtime_paths_avoid_geometry_roots(
    degree, monkeypatch
):
    from cinder.model.cvt.actuation import sliding_block, sliding_block_geometry

    spec = curved_spec()
    source = spec.geometry.lower_track
    points = [
        (r, source.value(float(r))) for r in np.linspace(source.left, source.right, 13)
    ]
    curve = Profile.from_points(points, degree=degree)
    g = replace(spec.geometry, lower_track=curve)
    # Rebuild only the synthetic open reference; measured hardware must not be
    # silently moved by a production caller.
    m = calibrate_zero(
        Mechanism(
            g.lower_track,
            g.upper_track,
            g.lower_face,
            g.upper_face,
            0.6,
            0.01,
            radius_ref=0.05,
            x_max=0.012,
        )
    )
    g = replace(g, lower_track=m.lower_track, upper_track=m.upper_track)
    force = SlidingBlockFlyweightForce(replace(spec, geometry=g))

    def no_solve(*a, **kw):
        pytest.fail("contact root solve in runtime")

    for module, key in (
        (sliding_block, "brentq"),
        (sliding_block_geometry, "brentq"),
        (sliding_block_geometry, "_gap_minima"),
        (sliding_block_geometry, "_contact_minima"),
    ):
        monkeypatch.setattr(module, key, no_solve)
    for x in np.linspace(0, 0.012, 17):
        sample = force.inertia_map.evaluate(float(x))
        p = force.inertia_map.pose(float(x))
        assert (
            abs(
                p.datum_axial
                + g.lower_face.value(p.lower.u)
                - g.lower_track.value(p.lower.radial)
            )
            < 4e-10
        )
        reactions = force.inertia_map.reactions(
            float(x), omega=300, alpha=20, xdot=0.05, xddot=-2
        )
        assert reactions.compressive
        assert reactions.guide_moment is None
        force.inertia_map.impulses(float(x), delta_xdot=-0.1, delta_omega=10)
        if 0.000001 < x < 0.011999:
            a, b = (force.inertia_map.evaluate(float(x + d)) for d in (-1e-7, 1e-7))
            assert sample.effective_mass_gradient == pytest.approx(
                (b.effective_mass - a.effective_mass) / 2e-7, rel=1e-5, abs=1e-6
            )


@pytest.mark.parametrize("axial_origin", [-0.25, 0.25])
def test_axial_datum_translation_has_no_hidden_sample_size_bounds(axial_origin):
    spec = two_point_spec()
    g = spec.geometry
    moved = replace(
        g,
        lower_track=replace(g.lower_track, offset=g.lower_track.offset + axial_origin),
        upper_track=replace(g.upper_track, offset=g.upper_track.offset + axial_origin),
    )
    mapping = SlidingBlockFlyweightForce(replace(spec, geometry=moved)).inertia_map
    reference = SlidingBlockFlyweightForce(spec).inertia_map
    mechanism = replace(moved.mechanism(), total_mass=0.6, gyration_radius=0.01)
    exact = evaluate(mechanism, 0.0075, omega=300)
    assert exact.admissible
    assert exact.radial == pytest.approx(reference.pose(0.0075).radial, abs=1e-10)
    assert exact.axial == pytest.approx(
        reference.pose(0.0075).axial + axial_origin, abs=1e-10
    )
    assert mapping.pose(0.0075).axial == pytest.approx(exact.axial, abs=1e-10)
    assert mapping.evaluate(0.0075).shaft_inertia_gradient == pytest.approx(
        reference.evaluate(0.0075).shaft_inertia_gradient
    )
