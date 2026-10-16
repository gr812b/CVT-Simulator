"""Regressions for the actual drawings, independent of the inertia checks."""
from copy import deepcopy
from dataclasses import asdict, replace

import numpy as np
import pytest
from shapely.geometry import Point as ShapePoint, Polygon

from .demo import _html_data
from .scenarios import EXAMPLES, make
from .section import (build_section, section_frame, placed_bodies, belt_polygon,
                      validate_solids)
from .sliding_block import sweep, evaluate


@pytest.fixture(scope="module")
def scenes():
    result = {}
    for name in EXAMPLES:
        m = make(name)
        points = sweep(m, n=76)
        section = build_section(m, points)
        result[name] = m, points, section
    return result


@pytest.mark.parametrize("name", EXAMPLES)
def test_entire_sampled_travel_has_finite_nonintersecting_solids(scenes, name):
    m, points, section = scenes[name]
    for p in points:
        frame = section_frame(section, m, p)
        assert not frame["issues"], (name, p.x, frame["issues"])
        bodies = placed_bodies(section, frame)
        for b in bodies:
            shape = Polygon(b["points"])
            assert shape.is_valid and shape.area > 0, b["name"]
        # Coil sections stay outside the shaft and inside the hub bore, and
        # approach their two seats without penetrating any sectioned material.
        coils = [ShapePoint(c).buffer(.8, quad_segs=8) for c in frame["spring_centers"]]
        for coil in coils:
            assert all(coil.intersection(Polygon(b["points"])).area < 1e-8 for b in bodies)
        assert np.mean(np.array(frame["spring_centers"])[:, 1]) == pytest.approx(0)


@pytest.mark.parametrize("name", EXAMPLES)
def test_belt_has_constant_shape_seats_on_both_flanks_and_moves_out(scenes, name):
    m, _, s = scenes[name]
    original, initial_r = belt_polygon(s, 0)
    original = np.array(original)
    area = Polygon(original).area
    for x in np.linspace(0, m.x_max*1000, 137):
        vertices, radius = belt_polygon(s, x)
        belt = np.array(vertices)
        assert Polygon(belt).area == pytest.approx(area, abs=1e-9)
        assert radius == pytest.approx(initial_r+x/(2*s.slope))
        assert belt[2,0]-belt[3,0] > belt[1,0]-belt[0,0] > 0
        # A fixed trapezoid translates by x/2 axially and x/(2*tan(beta)) radially.
        assert belt-original == pytest.approx(np.tile([x/2,x/(2*s.slope)],(4,1)), abs=1e-10)
        for j in (0,3):
            z,r=belt[j]
            assert z == pytest.approx(s.moving_root_z-s.slope*(r-s.root)+x)
        for j in (1,2):
            z,r=belt[j]
            assert z == pytest.approx(s.fixed_root_z+s.slope*(r-s.root))
        assert belt[:,1].min()>=s.root and belt[:,1].max()<=s.rim


@pytest.mark.parametrize("name", ["straight","curved-cup","both-curved"])
def test_solved_contacts_are_boundaries_of_block_and_connected_solid(scenes, name):
    m, points, s = scenes[name]
    for p in points:
        f=section_frame(s,m,p)
        solids={b["name"]:Polygon(b["points"]) for b in placed_bodies(s,f)}
        block=solids["Sliding weight"]
        for contact,body,band in [(p.lower,"Reaction cup",s.contact_bands[0]),
                                  (p.upper,"Moving sheave",s.contact_bands[1])]:
            q=ShapePoint(1000*contact.axial,1000*contact.radial)
            assert band[0] <= q.y <= band[1]
            assert q.distance(solids[body].boundary) < 1e-8
            assert q.distance(block.boundary) < 3e-5
            # Drawn contact normals point into free space toward the block.
            trial=ShapePoint(q.x + .02*contact.normal[1],q.y + .02*contact.normal[0])
            assert not solids[body].contains(trial)
        # Each displayed assembly is fixed in its own coordinates.
        for b in placed_bodies(s,f)[:len(s.bodies)]:
            source=next(a for a in s.bodies if a["name"]==b["name"])
            delta=np.array(b["points"])-np.array(source["points"])
            expected=np.tile([1000*p.x if b["moving"] else 0,0],(len(delta),1))
            assert delta == pytest.approx(expected,abs=1e-11)
        assert f["spring_length"] == pytest.approx(s.spring_end-s.spring_start-p.x*1000)


def test_invalid_solver_iterates_are_never_drawn_as_physical_weights(scenes):
    for name in ("short-track","parallel"):
        m,points,s=scenes[name]
        for p in points:
            f=section_frame(s,m,p)
            if not p.lower or not p.upper:
                assert f["block"]==[] and f["com"] is None and not f["pose_valid"]
        assert not section_frame(s,m,points[-1])["pose_valid"]
    m,_,s=scenes["both-curved"]
    # A tensile reaction invalidates dynamics but not the geometric pose.
    p=evaluate(m,.008,omega=25,xddot=200)
    assert not p.admissible and section_frame(s,m,p)["pose_valid"]


def test_detector_rejects_crossing_belt_and_material_overlap(scenes):
    m,points,s=scenes["straight"]
    bodies=placed_bodies(s,section_frame(s,m,points[0]))
    broken=deepcopy(bodies)
    belt=next(b for b in broken if b["name"]=="Belt")
    belt["points"][1],belt["points"][2]=belt["points"][2],belt["points"][1]
    assert "invalid solid outline: Belt" in validate_solids(broken)
    overlapped=deepcopy(bodies)
    block=next(b for b in overlapped if b["name"]=="Sliding weight")
    block["points"]=next(b["points"] for b in overlapped if b["name"]=="Reaction cup")
    assert any("material overlap" in issue for issue in validate_solids(overlapped))


def test_section_envelope_is_checked_between_compiled_points(scenes):
    for name in ("straight","curved-cup","both-curved"):
        m,_,s=scenes[name]
        for x in np.linspace(.0001,m.x_max-.0001,39):
            assert not section_frame(s,m,evaluate(m,float(x)))["issues"]


def test_html_serializes_the_same_solid_scene_as_static_renderer(scenes):
    data=_html_data()
    for name,(_,points,s) in scenes.items():
        assert data[name]["section"]==asdict(s)
        for i in (0,38,75):
            m=make(name)
            f=section_frame(s,m,points[i])
            assert data[name]["points"][i]["section"]==f
    # Any n changes neither the solid layout nor the total-mass mechanics.
    m=make("both-curved")
    changed=replace(m,display_count=7)
    assert asdict(build_section(changed,sweep(changed,n=76)))==data["both-curved"]["section"]
