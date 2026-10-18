"""Closed-form support changes, branch selection, and precision regressions."""

from dataclasses import replace
import json
import numpy as np
from numpy.polynomial import Polynomial
import pytest
from scipy.optimize import brentq
from cinder.model.cvt.actuation import (
    SlidingBlockGeometry,
    SlidingBlockGeometryError,
    SlidingBlockInertiaMap,
    SlidingBlockMass,
    SlidingBlockProfile as Profile,
    SlidingBlockSpec,
    SlidingBlockFlyweightForce,
)
from cinder.contracts.document import _decode_force_law, _encode_force_law
from cinder.contracts.schema import assembly_document_json_schema


def polynomial(poly, left, right):
    return Profile(
        "spline",
        0,
        left=left,
        right=right,
        knots=(left, right),
        coefficients=(tuple(poly(Polynomial([left, right - left])).coef),),
    )


def mass():
    return SlidingBlockMass(
        0.6, 3, (0, 0, 0), ((1e-4, 0, 0), (0, 1e-4, 0), (0, 0, 1e-4))
    )


def pads_spec():
    # Dyadic dimensions avoid perturbing the manufactured exact equal supports.
    knots = (1 / 32, 3 / 64, 13 / 256, 3 / 32)
    r = Polynomial([0, 1])
    base = 0.75 * (r - 1 / 16)
    bump = 2**28 * (r - knots[1]) ** 3 * (knots[2] - r) ** 3
    pieces = (base, base - bump, base)
    cup = Profile(
        "spline",
        0,
        left=knots[0],
        right=knots[-1],
        knots=knots,
        coefficients=tuple(
            tuple(p(Polynomial([a, b - a])).coef)
            for a, b, p in zip(knots, knots[1:], pieces)
        ),
    )
    lower = Profile("line", 0, slope=0.75, left=-1 / 128, right=1 / 128)
    upper = Profile(
        "line", 0, offset=1 / 32, slope=-0.5, left=lower.left, right=lower.right
    )
    ramp = Profile(
        "line", 1 / 16, offset=1 / 32, slope=-0.5, left=knots[0], right=knots[-1]
    )
    return SlidingBlockSpec(
        SlidingBlockGeometry(
            cup, ramp, lower, upper, 11 / 256, 19 / 256, -1 / 64, 1 / 128, True
        ),
        mass(),
        "ideal_fixed_orientation",
    )


def test_contact_spans_change_count_without_changing_body_mechanics(monkeypatch):
    spec = pads_spec()
    mapping = SlidingBlockInertiaMap(spec)
    from cinder.model.cvt.actuation import sliding_block

    monkeypatch.setattr(
        sliding_block, "brentq", lambda *a, **kw: pytest.fail("runtime closure solve")
    )
    counts = set()
    for R in np.linspace(0.05, 0.068, 39):
        x = 1.25 * (R - 1 / 16)
        p = mapping.pose(float(x))
        counts.add(len(p.lower.u_intervals))
        assert p.datum_radial == pytest.approx(R, abs=2e-13)
        assert p.datum_axial == pytest.approx(0.75 * (R - 1 / 16), abs=2e-13)
        assert (p.r_prime, p.z_prime) == pytest.approx((0.8, 0.6), abs=2e-10)
        sample = mapping.evaluate(x)
        assert sample.effective_mass == pytest.approx(0.6, abs=1e-10)
        assert sample.effective_mass_gradient == pytest.approx(0, abs=2e-7)
        loads = mapping.reactions(x, omega=250, alpha=40, xdot=0.03, xddot=2)
        assert loads.compressive
        assert -loads.upper_normal * p.upper.normal[1] == pytest.approx(
            0.6 * R * 250**2 * 0.8 - 0.6 * 2, abs=2e-7
        )
        moments = []
        for u in [v for span in p.lower.u_intervals for v in span]:
            for v in (-1 / 128, 1 / 128):
                value = 0
                for contact, coord, n in (
                    (p.lower, u, loads.lower_normal),
                    (p.upper, v, loads.upper_normal),
                ):
                    arm = (
                        R + coord - p.radial,
                        0,
                        contact.axial + contact.slope * (coord - contact.u) - p.axial,
                    )
                    value -= np.cross(
                        arm, n * np.array([contact.normal[0], 0, contact.normal[1]])
                    )[1]
                moments.append(value)
        assert loads.guide_moment_bounds[1] == pytest.approx(
            (min(moments), max(moments)), abs=2e-9
        )
    assert counts == {1, 2}


def endpoint_spec():
    # A(R)=s*d+4*k*a²*d²+k*d⁴+4*k*a*|d|³ is C2, with a jump in A'''.
    r = Polynomial([0, 1])
    a = 1 / 256
    s = 0.75
    k = 2**20
    K = 512
    d = r - 1 / 16
    cup = polynomial(
        s * d + k * (d**4 - 2 * a * a * d * d) - K * a * a + k * a**4, 1 / 32, 3 / 32
    )
    lower = Profile("quadratic", 0, slope=s, curvature=-2 * K, left=-a, right=a)
    upper = Profile("line", 0, offset=1 / 32, slope=-0.5, left=-a, right=a)
    ramp = Profile("line", 1 / 16, offset=1 / 32, slope=-0.5, left=1 / 32, right=3 / 32)
    return SlidingBlockSpec(
        SlidingBlockGeometry(
            cup,
            ramp,
            lower,
            upper,
            1 / 16 - 1 / 512,
            1 / 16 + 1 / 256,
            -1 / 1024,
            1 / 256,
            True,
        ),
        mass(),
        "ideal_fixed_orientation",
    )


def endpoint_oracle(x):
    a = 1 / 256
    k = 2**20
    s = 0.75

    def A(d):
        return s * d + 4 * k * a * a * d * d + k * d**4 + 4 * k * a * abs(d) ** 3

    d = brentq(lambda d: A(d) + 0.5 * d - x, -1 / 512, 1 / 256, xtol=1e-16)
    first = s + 8 * k * a * a * d + 4 * k * d**3 + 12 * k * a * d * abs(d)
    second = 8 * k * a * a + 12 * k * d * d + 24 * k * a * abs(d)
    rp = 1 / (first + 0.5)
    rpp = -second * rp**3
    return np.array(
        [[1 / 16 + d, A(d)], [rp, first * rp], [rpp, first * rpp + second * rp**2]]
    )


def test_smooth_endpoint_switch_uses_one_body_branch_and_correct_derivatives():
    mapping = SlidingBlockInertiaMap(endpoint_spec())
    for x in [*np.linspace(-1 / 1024, 1 / 256, 29), -1e-8, 0, 1e-8]:
        expected = endpoint_oracle(x)
        p = mapping.pose(float(x))
        np.testing.assert_allclose([p.radial, p.axial], expected[0], atol=3e-10, rtol=0)
        np.testing.assert_allclose(
            [p.r_prime, p.z_prime], expected[1], atol=4e-7, rtol=0
        )
        np.testing.assert_allclose(
            [p.r_second, p.z_second], expected[2], atol=4e-4, rtol=0
        )
    assert mapping.pose(-1e-5).lower.u == pytest.approx(-1 / 256)
    assert mapping.pose(1e-5).lower.u == pytest.approx(1 / 256)


def test_true_endpoint_corner_requires_an_event_model():
    spec = endpoint_spec()
    g = spec.geometry
    cup = Profile(
        "quadratic",
        1 / 16,
        offset=-0.01,
        slope=0.75,
        curvature=8,
        left=1 / 32,
        right=3 / 32,
    )
    from cinder.model.cvt.actuation.sliding_block_geometry import calibrate_zero

    m = calibrate_zero(replace(g.mechanism(), lower_track=cup, radius_ref=1 / 16))
    with pytest.raises(SlidingBlockGeometryError) as failure:
        SlidingBlockInertiaMap(
            replace(
                spec,
                geometry=replace(
                    g, lower_track=m.lower_track, upper_track=m.upper_track
                ),
            )
        )
    assert failure.value.category == "model"
    assert failure.value.code == "nonsmooth_contact_transition"
    assert failure.value.radial_interval[0] == pytest.approx(1 / 16, abs=1e-12)


def folded_spec(reference=None):
    cup = Profile(
        "quadratic", 0.06, offset=-0.001, slope=0, curvature=64, left=0.015, right=0.105
    )
    lower = Profile("quadratic", 0, curvature=-1000, left=0, right=0.004)
    upper = Profile("line", 0, offset=0.04, left=0, right=0.004)
    ramp = Profile("line", 0, offset=0.04, left=0.015, right=0.105)
    constant = 500 * 0.004**2 - 0.001
    g = SlidingBlockGeometry(
        cup,
        ramp,
        lower,
        upper,
        0.025,
        0.09,
        constant + 0.001,
        constant + 0.003,
        True,
        reference,
    )
    return SlidingBlockSpec(g, mass(), "ideal_fixed_orientation")


def test_multiple_branches_require_selection_and_both_are_usable():
    with pytest.raises(SlidingBlockGeometryError) as failure:
        SlidingBlockInertiaMap(folded_spec())
    assert failure.value.code == "ambiguous_branch"
    for reference, sign in ((0.035, -1), (0.08, 1)):
        spec = folded_spec(reference)
        mapping = SlidingBlockInertiaMap(spec)
        for x in np.linspace(
            spec.geometry.axial_position_min, spec.geometry.axial_position_max, 7
        ):
            p = mapping.pose(x)
            candidates = [
                (
                    u,
                    spec.geometry.lower_track.value(p.datum_radial + u)
                    - spec.geometry.lower_face.value(u),
                )
                for u in (0, 0.004)
            ]
            assert p.datum_axial == pytest.approx(
                max(v for _, v in candidates), abs=2e-10
            )
            assert np.sign(p.r_prime) == sign
        assert (
            mapping.compilation_report.selected_radial_interval[0]
            <= reference
            <= mapping.compilation_report.selected_radial_interval[1]
        )
        record = _encode_force_law(SlidingBlockFlyweightForce(spec))
        import jsonschema

        schema = assembly_document_json_schema()
        jsonschema.validate(
            record, {"$defs": schema["$defs"], "$ref": "#/$defs/assemblySlidingBlock"}
        )
        assert (
            _encode_force_law(_decode_force_law(json.loads(json.dumps(record))))
            == record
        )


def test_small_resolvable_slope_separation_is_not_a_fixed_condition_limit():
    spec = pads_spec()
    g = spec.geometry
    cup = Profile("line", 0.0625, slope=0.75, left=0.02, right=0.1)
    ramp = Profile("line", 0.0625, offset=0.03125, slope=0.749, left=0.02, right=0.1)
    lower = Profile("line", 0, slope=0.75, left=-0.004, right=0.004)
    upper = Profile("line", 0, offset=0.03125, slope=0.749, left=-0.004, right=0.004)
    g = replace(
        g,
        lower_track=cup,
        upper_track=ramp,
        lower_face=lower,
        upper_face=upper,
        radial_min=0.06,
        radial_max=0.07,
        axial_position_min=0,
        axial_position_max=5e-6,
    )
    mapping = SlidingBlockInertiaMap(replace(spec, geometry=g))
    p = mapping.pose(2.5e-6)
    assert p.radial == pytest.approx(0.065, abs=1e-12)
    assert p.r_prime == pytest.approx(1000, rel=1e-10)


@pytest.mark.parametrize(
    "factory,transition", [(pads_spec, -0.009765625), (endpoint_spec, 0.0)]
)
def test_free_motion_crosses_support_change_and_conserves_energy_and_momentum(
    factory, transition
):
    from scipy.integrate import solve_ivp

    mapping = SlidingBlockInertiaMap(factory())
    host_mass, fixed_inertia = 1.0, 0.03

    def rhs(t, y):
        x, xd, omega = y
        s = mapping.evaluate(x)
        acceleration = (
            0.5 * s.shaft_inertia_gradient * omega**2
            - 0.5 * s.effective_mass_gradient * xd**2
        ) / (host_mass + s.effective_mass)
        alpha = (
            -s.shaft_inertia_gradient * xd * omega / (fixed_inertia + s.shaft_inertia)
        )
        loads = mapping.reactions(
            x, omega=omega, alpha=alpha, xdot=xd, xddot=acceleration
        )
        assert loads.compressive
        return xd, acceleration, alpha

    solution = solve_ivp(
        rhs,
        (0, 0.0005),
        (transition - 1e-5, 0.02, 200),
        rtol=1e-9,
        atol=1e-12,
        max_step=2e-5,
    )
    assert solution.success and solution.y[0, -1] > transition + 1e-5
    energy = []
    momentum = []
    for x, xd, omega in solution.y.T:
        s = mapping.evaluate(x)
        energy.append(
            0.5 * (host_mass + s.effective_mass) * xd**2
            + 0.5 * (fixed_inertia + s.shaft_inertia) * omega**2
        )
        momentum.append((fixed_inertia + s.shaft_inertia) * omega)
    np.testing.assert_allclose(energy, energy[0], rtol=3e-9, atol=1e-10)
    np.testing.assert_allclose(momentum, momentum[0], rtol=3e-9, atol=1e-11)


def test_reference_validation_and_reachable_com_radius():
    spec = folded_spec(0.035)
    with pytest.raises(ValueError, match="reference_radius"):
        replace(spec.geometry, reference_radius=0.2)
    # The broad search window includes a fictitious COM-axis crossing; the
    # actual selected trajectory stays near R=.05 and has a positive radius.
    mapping = SlidingBlockInertiaMap(
        replace(spec, mass=replace(spec.mass, com_offset=(-0.03, 0, 0)))
    )
    assert mapping.pose(spec.geometry.axial_position_min).radial > 0


def test_isolated_extra_contact_preserves_active_envelope_curvature():
    spec = endpoint_spec()
    g = spec.geometry
    r = Polynomial([0, 1])
    a = 1 / 256
    d = r - 1 / 16
    k = 2**20
    cup = polynomial(
        0.75 * d + k * (d - a) ** 2 * (d + a) ** 3 - 512 * a * a, 1 / 32, 3 / 32
    )
    mapping = SlidingBlockInertiaMap(
        replace(spec, geometry=replace(g, lower_track=cup))
    )
    p = mapping.pose(0)
    assert len(p.lower.u_intervals) == 2
    # The right candidate wins on both sides; the left touches only at zero.
    expected_second = 16 * k * a**3
    assert p.lower.slope_derivative == pytest.approx(expected_second, abs=2e-10)
    assert p.r_second == pytest.approx(-expected_second / 1.25**3, abs=2e-6)
    for x in (-1e-5, 1e-5):
        assert len(mapping.pose(x).lower.u_intervals) == 1
        assert mapping.pose(x).lower.u == pytest.approx(a, abs=1e-10)
