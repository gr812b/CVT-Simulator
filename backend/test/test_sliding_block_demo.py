"""Sample poses, physical block properties and full hardware envelopes."""

from math import pi

import numpy as np
import pytest
from shapely.geometry import Polygon

from app.application.sliding_block_demo import _block_mass, preview, sample_force


def test_public_sample_is_bounded_cached_and_uses_published_cinder(api):
    response = api.get("/api/v1/demo/sliding-block")
    assert response.status_code == 200
    data = response.json()
    assert data["cinder_version"] == "1.2.0"
    assert len(data["frames"]) == 241
    assert data["frames"][0]["closure_m"] == 0
    assert data["frames"][-1]["closure_m"] == data["travel_m"] == 0.015
    assert data["block_count"] == 3
    assert preview() is preview()


def test_drawn_weight_has_the_prisms_mass_centroid_and_inertia():
    data = preview()
    force, _ = sample_force()
    polygon = Polygon(data.block_outline_m)
    mass = force.spec.mass
    assert mass.total_mass == pytest.approx(polygon.area * data.block_width_m * 7800 * 3)
    assert mass.com_offset[0] == pytest.approx(polygon.centroid.x)
    assert mass.com_offset[2] == pytest.approx(polygon.centroid.y)
    # Independent closed-form cuboid fixture checks all tensor axes and
    # total-set/count accounting in the prism utility.
    rect = _block_mass([(-0.01, -0.02), (0.01, -0.02), (0.01, 0.02), (-0.01, 0.02)])
    expected = np.diag(
        [(0.024**2 + 0.04**2) / 12, (0.02**2 + 0.04**2) / 12, (0.02**2 + 0.024**2) / 12]
    )
    np.testing.assert_allclose(rect.centroidal_inertia_per_mass, expected, atol=1e-16)
    assert rect.com_offset == (0, 0, 0)


def test_all_exported_poses_match_cinder_and_full_solids_clear_the_weight():
    data = preview()
    force, _ = sample_force()
    cup = Polygon(data.cup_section_m)
    fixed = Polygon(data.fixed_section_m)
    assert cup.is_valid and fixed.is_valid
    for frame in data.frames:
        pose = force.inertia_map.pose(frame.closure_m)
        assert frame.datum_m == (pose.datum_radial, pose.datum_axial)
        assert frame.fixed_contact_m == (pose.lower.radial, pose.lower.axial)
        assert frame.moving_contact_m == (pose.upper.radial, pose.upper.axial)
        weight = Polygon(
            [(r + pose.datum_radial, z + pose.datum_axial) for r, z in data.block_outline_m]
        )
        moving = Polygon([(r, z + frame.closure_m) for r, z in data.moving_section_m])
        assert moving.is_valid
        for hardware in (cup, moving, fixed):
            assert weight.intersection(hardware).area < 1e-12
        belt = Polygon(frame.belt_section_m)
        assert belt.is_valid
        for sheave in (moving, fixed):
            assert belt.intersection(sheave).area < 1e-12
        # At held closure, the moving contact's axial reaction must equal
        # the canonical force; the guide supplies the independent couple.
        assert frame.closing_force_N == pytest.approx(
            -frame.moving_reaction_N * frame.moving_normal[1], rel=1e-7
        )
        assert frame.fixed_reaction_N > 0 and frame.moving_reaction_N > 0
        reaction = force.inertia_map.reactions(
            frame.closure_m, omega=data.rpm * 2 * pi / 60, alpha=0, xdot=0, xddot=0
        )
        assert frame.guide_moment_Nm == reaction.guide_moment
    assert data.frames[-1].com_m[0] > data.frames[0].com_m[0]
    # Both endpoints retain contacts in this arrest-direction fixture.
    for x in (0, data.travel_m):
        assert force.inertia_map.impulses(x, delta_xdot=-0.1, delta_omega=0).compressive
