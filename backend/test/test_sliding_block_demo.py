"""Matched-face geometry, independent mass integration, and held-state balance."""

from math import pi

import numpy as np
import pytest
from scipy.integrate import quad
from shapely.geometry import Polygon
from cinder.model.cvt.actuation import SlidingBlockFlyweightForce, SlidingBlockProfile as Profile
from cinder.model.cvt.actuation.sliding_block_geometry import evaluate

from app.application.sliding_block_demo import _block_mass, preview, sample_definition


def test_public_sample_is_bounded_cached_and_honest_about_provider_support(api):
    response = api.get("/api/v1/demo/sliding-block")
    assert response.status_code == 200
    data = response.json()
    assert data["cinder_version"] == "1.2.0"
    assert len(data["frames"]) == 241
    assert data["frames"][0]["closure_m"] == 0
    assert data["frames"][-1]["closure_m"] == data["travel_m"] == 0.015
    assert data["block_count"] == 3
    assert data["simulation_ready"] is False
    assert "guide_moment_Nm" not in data["frames"][0]
    assert preview() is preview()
    spec, _, _ = sample_definition()
    with pytest.raises(ValueError, match="conformal"):
        SlidingBlockFlyweightForce(spec)


def test_smooth_weight_mass_centroid_and_full_tensor_do_not_use_the_display_mesh():
    data = preview()
    spec, _, _ = sample_definition()
    lo, hi, mass = spec.geometry.lower_face, spec.geometry.upper_face, spec.mass
    assert lo.kind == "circle"
    assert hi.slope == spec.geometry.upper_track.slope

    # Independent adaptive integrals, including the nonzero product of inertia.
    def integral(fun):
        return quad(fun, lo.left, lo.right, epsabs=1e-18, epsrel=1e-12)[0]

    area = integral(lambda r: hi.value(r) - lo.value(r))
    cr = integral(lambda r: r * (hi.value(r) - lo.value(r))) / area
    cz = integral(lambda r: (hi.value(r) ** 2 - lo.value(r) ** 2) / 2) / area
    rr = integral(lambda r: r**2 * (hi.value(r) - lo.value(r))) / area - cr**2
    zz = integral(lambda r: (hi.value(r) ** 3 - lo.value(r) ** 3) / 3) / area - cz**2
    rz = integral(lambda r: r * (hi.value(r) ** 2 - lo.value(r) ** 2) / 2) / area - cr * cz
    tt = data.block_width_m**2 / 12
    assert mass.total_mass == pytest.approx(area * data.block_width_m * 7800 * 3, rel=1e-12)
    np.testing.assert_allclose(mass.com_offset, (cr, 0, cz), atol=1e-15)
    np.testing.assert_allclose(
        mass.centroidal_inertia_per_mass,
        ((tt + zz, 0, -rz), (0, rr + zz, 0), (-rz, 0, rr + tt)),
        atol=1e-15,
    )
    polygon = Polygon(data.block_outline_m)
    assert polygon.area == pytest.approx(area, rel=3e-6)
    assert polygon.centroid.x == pytest.approx(cr, abs=1e-8)
    assert polygon.centroid.y == pytest.approx(cz, abs=1e-8)
    for a, b in zip(data.block_outline_m[:512], data.block_outline_m[1:513]):
        # Each rendered arc chord is within 0.2 micrometre of its smooth face.
        assert abs((a[1] + b[1]) / 2 - lo.value((a[0] + b[0]) / 2)) < 2e-7

    rect = _block_mass(
        Profile("line", 0, offset=-0.02, left=-0.01, right=0.01),
        Profile("line", 0, offset=0.02, left=-0.01, right=0.01),
    )
    expected = np.diag(
        [(0.024**2 + 0.04**2) / 12, (0.02**2 + 0.04**2) / 12, (0.02**2 + 0.024**2) / 12]
    )
    np.testing.assert_allclose(rect.centroidal_inertia_per_mass, expected, atol=1e-16)
    np.testing.assert_allclose(rect.com_offset, (0, 0, 0), atol=1e-18)


def test_all_poses_have_tangent_cup_contact_flush_ramp_and_clear_hardware():
    data = preview()
    spec, _, mechanism = sample_definition()
    g = spec.geometry
    cup, fixed = Polygon(data.cup_section_m), Polygon(data.fixed_section_m)
    assert cup.is_valid and fixed.is_valid
    for frame in data.frames:
        rd, zd = frame.datum_m
        p = evaluate(mechanism, frame.closure_m, omega=data.rpm * 2 * pi / 60, guess=(rd, zd))
        assert p.admissible
        np.testing.assert_allclose(frame.com_m, (p.radial, p.axial), atol=1e-10)
        assert g.radial_min <= rd <= g.radial_max
        assert g.lower_face.left < p.lower.u < g.lower_face.right
        assert g.lower_face.gradient(p.lower.u) == pytest.approx(p.lower.slope, abs=1e-10)
        assert zd + g.lower_face.value(p.lower.u) == pytest.approx(p.lower.axial, abs=1e-10)
        # The whole flat face closes, not just one arbitrarily chosen endpoint.
        for u in np.linspace(g.upper_face.left, g.upper_face.right, 17):
            assert zd + g.upper_face.value(u) == pytest.approx(
                g.upper_track.value(rd + u) + frame.closure_m, abs=1e-10
            )
        assert frame.moving_contact_span_m == tuple(
            (rd + u, zd + g.upper_face.value(u)) for u in (g.upper_face.left, g.upper_face.right)
        )
        weight = Polygon([(r + rd, z + zd) for r, z in data.block_outline_m])
        moving = Polygon([(r, z + frame.closure_m) for r, z in data.moving_section_m])
        assert weight.is_valid and moving.is_valid
        for hardware in (cup, moving, fixed):
            assert weight.intersection(hardware).area < 1e-12
        belt = Polygon(frame.belt_section_m)
        assert belt.is_valid
        for sheave in (moving, fixed):
            assert belt.intersection(sheave).area < 1e-12
    assert data.frames[-1].com_m[0] > data.frames[0].com_m[0]


def test_held_resultants_balance_and_canonical_force_agrees_with_rotational_energy():
    data = preview()
    spec, _, mechanism = sample_definition()
    omega = data.rpm * 2 * pi / 60
    for frame in data.frames:
        normals = np.column_stack((frame.fixed_normal, frame.moving_normal))
        load = normals @ (frame.fixed_reaction_N, frame.moving_reaction_N)
        np.testing.assert_allclose(
            load, (-spec.mass.total_mass * frame.com_m[0] * omega**2, 0), atol=1e-10
        )
        assert frame.fixed_reaction_N > 0 and frame.moving_reaction_N > 0
        assert frame.closing_force_N == pytest.approx(
            -frame.moving_reaction_N * frame.moving_normal[1], rel=1e-12
        )
    # Independent energy difference checks at interior held positions.
    for x in (0.002, 0.0075, 0.013):
        h = 1e-6
        points = [evaluate(mechanism, x + d, omega=omega) for d in (-h, 0, h)]
        energy_gradient = 0.5 * omega**2 * (points[2].J_f - points[0].J_f) / (2 * h)
        assert points[1].F_interface == pytest.approx(energy_gradient, rel=1e-7)
