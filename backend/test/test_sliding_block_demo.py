"""Matched-face geometry, independent mass integration, and held-state balance."""

from math import pi, asin, sqrt

import numpy as np
import pytest
from shapely.geometry import Polygon
from cinder.model.cvt.actuation import SlidingBlockFlyweightForce, SlidingBlockProfile as Profile
from cinder.model.cvt.actuation.sliding_block_geometry import evaluate

from app.application.sliding_block_demo import (
    _block_mass,
    preview,
    sample_definition,
    DEFAULT_INPUTS,
    _translation_sweep,
)


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
    assert data["inputs"]["block_thickness_m"] == 0.04
    assert data["findings"] == []
    assert data["minimum_hardware_clearance_m"] > 0.001
    spec, _, _ = sample_definition()
    with pytest.raises(ValueError, match="conformal"):
        SlidingBlockFlyweightForce(spec)


def test_smooth_weight_mass_centroid_and_full_tensor_do_not_use_the_display_mesh():
    data = preview()
    spec, _, _ = sample_definition()
    lo, hi, mass = spec.geometry.lower_face, spec.geometry.upper_face, spec.mass
    assert lo.kind == "circle"
    assert hi.slope == spec.geometry.upper_track.slope

    # Independent Gaussian integration, including the nonzero product of inertia.
    def integral(fun):
        nodes, weights = np.polynomial.legendre.leggauss(128)
        half = (lo.right - lo.left) / 2
        return half * sum(
            weight * fun((lo.left + lo.right) / 2 + half * node)
            for node, weight in zip(nodes, weights)
        )

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
        for a, b in ((cup, moving), (cup, fixed), (moving, fixed)):
            assert a.intersection(b).area < 1e-12
        assert frame.interference_pairs == []
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


def test_edits_rebuild_mass_and_motion_but_backing_does_not_change_weight():
    base = preview()
    wider = preview(DEFAULT_INPUTS.model_copy(update={"block_width_m": 0.030}))
    assert wider.total_mass_kg == pytest.approx(base.total_mass_kg * 0.030 / 0.024)
    assert wider.frames[-1].datum_m == base.frames[-1].datum_m
    backing = preview(DEFAULT_INPUTS.model_copy(update={"cup_backing_m": 0.005}))
    assert backing.total_mass_kg == base.total_mass_kg
    assert backing.block_outline_m == base.block_outline_m
    assert backing.cup_section_m != base.cup_section_m
    for key, value in (
        ("block_span_m", 0.018),
        ("block_cup_radius_m", 0.019),
        ("cup_radius_m", 0.13),
        ("ramp_angle_rad", 0.4),
        ("travel_m", 0.010),
    ):
        candidate = preview(DEFAULT_INPUTS.model_copy(update={key: value}))
        assert not candidate.findings
        assert len(candidate.frames) == 241
        assert candidate.frames[-1].closure_m == candidate.travel_m


def test_preview_reports_interference_and_contact_failure_without_losing_revision(api):
    headers = {"X-Cinder-Client": "web"}
    thin = api.post(
        "/api/v1/demo/sliding-block/preview",
        headers=headers,
        json={"revision": 7, "inputs": {"block_thickness_m": 0.025}},
    )
    assert thin.status_code == 200
    data = thin.json()
    assert data["revision"] == 7
    assert data["preview"] is not None
    assert data["preview"]["minimum_hardware_clearance_m"] == 0
    assert any(
        f["code"] == "cup_moving_interference" and f["field"] == "block_thickness_m"
        for f in data["findings"]
    )
    assert "cup_moving" in data["preview"]["frames"][0]["interference_pairs"]
    assert data["preview"]["cup_touching_thickness_m"] < 0.04
    bad = api.post(
        "/api/v1/demo/sliding-block/preview",
        headers=headers,
        json={"revision": 8, "inputs": {"block_cup_radius_m": 0.005}},
    ).json()
    assert bad["revision"] == 8 and bad["preview"] is None
    assert bad["findings"][0]["field"] == "block_cup_radius_m"
    fixed = api.post(
        "/api/v1/demo/sliding-block/preview", headers=headers, json={"revision": 9, "inputs": {}}
    ).json()
    assert fixed["revision"] == 9 and not fixed["findings"]
    assert fixed["preview"]["minimum_hardware_clearance_m"] > 0.001
    assert (
        api.post(
            "/api/v1/demo/sliding-block/preview",
            headers=headers,
            json={"revision": 1, "inputs": {"travel_m": 10}},
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/demo/sliding-block/preview",
            headers=headers,
            json={"revision": 1, "inputs": {"unknown": 1}},
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/demo/sliding-block/preview",
            headers={**headers, "Origin": "https://unrelated.example"},
            json={"revision": 1, "inputs": {}},
        ).status_code
        == 403
    )


def test_preview_admission_limits_expensive_work(api, monkeypatch):
    from app.api.v1 import demo

    assert demo._preview_slots.acquire(False)
    assert demo._preview_slots.acquire(False)
    try:
        assert (
            api.post(
                "/api/v1/demo/sliding-block/preview",
                headers={"X-Cinder-Client": "web"},
                json={"revision": 1, "inputs": {}},
            ).status_code
            == 429
        )
    finally:
        demo._preview_slots.release()
        demo._preview_slots.release()
    from app.core.errors import ApiProblem

    def limited(*args, **kwargs):
        raise ApiProblem(429, "preview_rate_limited", "Too many requests")

    monkeypatch.setattr(demo, "throttle", limited)
    assert (
        api.post(
            "/api/v1/demo/sliding-block/preview",
            headers={"X-Cinder-Client": "web"},
            json={"revision": 2, "inputs": {}},
        ).status_code
        == 429
    )


def test_sweep_detects_a_collision_between_clear_endpoints():
    moving = [(0, 0), (1, 0), (1, 1), (0, 1)]
    obstacle = Polygon([(0.25, 1.4), (0.75, 1.4), (0.75, 1.5), (0.25, 1.5)])
    assert not obstacle.intersects(Polygon(moving))
    assert not obstacle.intersects(Polygon([(r, z + 2) for r, z in moving]))
    assert obstacle.intersection(_translation_sweep(moving, 2)).area == pytest.approx(obstacle.area)


def test_near_semicircle_mass_matches_closed_form_and_intersecting_faces_fail(api):
    spec, _, _ = sample_definition(
        DEFAULT_INPUTS.model_copy(update={"block_cup_radius_m": 0.01800000001})
    )
    lo, hi = spec.geometry.lower_face, spec.geometry.upper_face

    def circular_area(u):
        d = u - lo.origin
        return 0.5 * (d * sqrt(lo.radius**2 - d * d) + lo.radius**2 * asin(d / lo.radius))

    area = (
        (hi.offset - lo.offset - lo.radius) * (lo.right - lo.left)
        + circular_area(lo.right)
        - circular_area(lo.left)
    )
    assert spec.mass.total_mass == pytest.approx(area * 0.024 * 7800 * 3, rel=1e-11)
    result = api.post(
        "/api/v1/demo/sliding-block/preview",
        headers={"X-Cinder-Client": "web"},
        json={"revision": 10, "inputs": {"block_thickness_m": 0.002}},
    )
    assert result.status_code == 200
    assert result.json()["preview"] is None
    assert result.json()["findings"][0]["field"] == "block_thickness_m"
