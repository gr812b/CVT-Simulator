"""Finite reference solids around the unchanged sliding-block contact solution.

Coordinates in the scene are (axial z, signed radius r), in millimetres.
A scene is built ONCE for a whole sweep. Only the orange assembly translates.
The finite contact inserts retain the original profiles over the swept contact
bands. Unused mathematical extensions are relieved, not drawn as intersecting
material. These reference solids are not measured hardware or new solver inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import isfinite, tan, radians

import numpy as np
from shapely.geometry import Polygon

from .sliding_block import Mechanism, Point

COLORS = {"fixed": "#167586", "moving": "#bb6827", "block": "#345f91",
          "belt": "#303b49", "shaft": "#a8b4c1", "spring": "#536173"}
FILLS = {"fixed": "#e5f0f1", "moving": "#fff0df", "block": "#b2c8e2",
         "belt": "#455366", "shaft": "#e5e9ee", "spring": "#66798e"}


def _rect(z0, r0, z1, r1):
    return [[z0, r0], [z1, r0], [z1, r1], [z0, r1]]


def _curve(profile, a, b, extra=()):
    radii = sorted(set(np.linspace(a, b, 161).tolist() + [r for r in extra if a <= r <= b]))
    return [[1000 * profile.value(r), 1000 * r] for r in radii]


def _body(name, points, kind, moving=False):
    return dict(name=name, points=points, kind=kind, moving=moving)


def _shift(points, dz):
    return [[z + dz, r] for z, r in points]


@dataclass
class Section:
    """One rigid set of reference parts and its seating relation."""
    bodies: list[dict]
    tracks: list[dict]
    bounds: list[float]
    slope: float
    root: float
    rim: float
    moving_root_z: float
    fixed_root_z: float
    belt_height: float
    belt_width: float
    belt_radius_open: float
    spring_start: float
    spring_end: float
    labels: list[dict]
    path: list[list[float]]
    contact_bands: list[list[float]]


def build_section(m: Mechanism, points: list[Point]) -> Section:
    """Build fixed material once; never trim or rescale a body as x changes.

    A 1 mm radial margin surrounds all solved contacts (bounded by the input
    domain). Away from that band the insert ends in free space, with its backing
    connected to its sheave/cup. The scene therefore makes no claim that the
    entire mathematical profile domain is a physical contact face.
    """
    curves, bands = [], []
    for key, profile in (("lower", m.lower_track), ("upper", m.upper_track)):
        contacts = [getattr(p, key).radial for p in points if getattr(p, key) is not None]
        if contacts:
            a, b = max(profile.left, min(contacts) - .001), min(profile.right, max(contacts) + .001)
        else:
            # No solved branch (e.g. parallel). Draw reference material only;
            # no failed least-squares iterate is ever drawn as a weight pose.
            a = max(profile.left, m.radius_ref + m.lower_face.left - .001)
            b = min(profile.right, m.radius_ref + m.lower_face.right + .001)
        curves.append(_curve(profile, a, b, contacts))
        bands.append([1000 * a, 1000 * b])
    lower, upper = curves
    lo_a, lo_b = bands[0]
    hi_a, hi_b = bands[1]
    shaft_r, bore_r = 3.0, 9.0
    # A thick cup on the -z side, with a continuous web back to its hub.
    back = min(z for z, _ in lower) - 9
    cup = [[back, bore_r], [back, lo_b]] + lower[::-1] + [[back + 5, lo_a], [back + 5, bore_r]]
    # Both groove faces widen OUTWARD. +x translates the left face rightward.
    t = tan(radians(20))
    height, width, radius_open = 10.0, 30.0, 48.0
    travel = m.x_max * 1000
    # Leave at least 3 mm between the sheave roots at maximum closure.
    root = max(30.0, radius_open + (travel + 3 - width) / (2 * t))
    radius_open = max(radius_open, root + height / 2 + 2)
    rim = max(86.0, radius_open + travel / (2 * t) + height / 2 + 7, lo_b + 7, hi_b + 7)
    # The relieved rear face clears the entire swept block, including corners.
    block_front = [1000 * (p.axial - p.x + m.upper_face.value(float(u)))
                   for p in points if p.lower and p.upper
                   for u in np.linspace(m.upper_face.left, m.upper_face.right, 41)]
    rear = max([z for z, _ in upper] + block_front) + 5
    front = rear + 5 + t * (rim - root)
    moving = ([[rear, bore_r], [rear, hi_a]] + upper +
              [[rear, hi_b], [rear, rim], [front - t * (rim - root), rim],
               [front, root], [front, bore_r]])
    gap_root = width + 2 * t * (root - radius_open)
    fixed_front = front + gap_root
    fixed = [[fixed_front, bore_r], [fixed_front, root],
             [fixed_front + t * (rim - root), rim],
             [fixed_front + t * (rim - root) + 5, rim],
             [fixed_front + 5, root], [fixed_front + 5, bore_r]]
    spring_start, spring_end = front - 3, max(front + 40, fixed_front + 12, front + travel + 20)
    shaft_end = max(spring_end + 7, fixed_front + t * (rim - root) + 9)
    bodies = [
        _body("Shaft", _rect(back - 8, -shaft_r, shaft_end, shaft_r), "shaft"),
        _body("Reaction cup", cup, "fixed"),
        _body("Cup hub", _rect(back, shaft_r + .5, back + 5, bore_r), "fixed"),
        _body("Moving sheave", moving, "moving", True),
        _body("Moving spring seat", _rect(spring_start - 4, shaft_r + .5, spring_start, bore_r), "moving", True),
        _body("Moving spring seat, lower", _rect(spring_start - 4, -bore_r, spring_start, -shaft_r - .5), "moving", True),
        _body("Fixed sheave", fixed, "fixed"),
        _body("Fixed sleeve", _rect(fixed_front + 5, bore_r, spring_end + 2, bore_r + 2), "fixed"),
        _body("Fixed spring seat", _rect(spring_end, shaft_r + .5, spring_end + 2, bore_r), "fixed"),
        _body("Fixed spring seat, lower", _rect(spring_end, -bore_r, spring_end + 2, -shaft_r - .5), "fixed"),
    ]
    tracks = [dict(name="Cup contact face", points=lower, kind="fixed", moving=False),
              dict(name="Moving contact face", points=upper, kind="moving", moving=True)]
    labels = [dict(text="REACTION CUP", at=[back, lo_b + 7], kind="fixed"),
              dict(text="MOVING SHEAVE", at=[rear + 5, rim + 6], kind="moving"),
              dict(text="FIXED SHEAVE", at=[fixed_front + t * (rim - root) + 2, rim + 6], kind="fixed")]
    return Section(bodies, tracks, [back - 14, shaft_end + 4, -20, rim + 14], t, root, rim,
                   front, fixed_front, height, width, radius_open, spring_start, spring_end,
                   labels, [[1000*p.axial, 1000*p.radial] for p in points if p.lower and p.upper], bands)


def belt_polygon(s: Section, x_mm: float):
    """Fixed belt size; translate radially until BOTH flank constraints close."""
    radius = s.belt_radius_open + x_mm / (2 * s.slope)
    r0, r1 = radius - s.belt_height / 2, radius + s.belt_height / 2
    moving = lambda r: s.moving_root_z - s.slope * (r - s.root) + x_mm
    fixed = lambda r: s.fixed_root_z + s.slope * (r - s.root)
    return [[moving(r0), r0], [fixed(r0), r0], [fixed(r1), r1], [moving(r1), r1]], radius


def block_polygon(m: Mechanism, p: Point):
    u = sorted(set(np.linspace(m.lower_face.left, m.lower_face.right, 101).tolist() +
                   [c.u for c in (p.lower, p.upper) if c is not None]))
    return ([[1000*(p.axial + m.lower_face.value(v)), 1000*(p.radial + v)] for v in u] +
            [[1000*(p.axial + m.upper_face.value(v)), 1000*(p.radial + v)] for v in u[::-1]])


def placed_bodies(s: Section, frame: dict) -> list[dict]:
    bodies = [{**b, "points": _shift(b["points"], frame["x_mm"] if b["moving"] else 0)} for b in s.bodies]
    bodies.append(_body("Belt", frame["belt"], "belt"))
    if frame["block"]:
        bodies.append(_body("Sliding weight", frame["block"], "block"))
    return bodies


def validate_solids(bodies: list[dict], tolerance_mm2=2e-4):
    """Check simple positive-area polygons and forbidden material overlap.

    Parts of the same rigid assembly may join. Belt/block/shaft must not overlap
    any other assembly. Tiny polygon-chord errors at curved tangencies are
    bounded by the area tolerance; contacts are also included as curve vertices.
    """
    issues, shapes = [], []
    for b in bodies:
        polygon = Polygon(b["points"])
        if not polygon.is_valid or polygon.area <= 0:
            issues.append(f"invalid solid outline: {b['name']}")
            continue
        group = b["kind"] if b["kind"] in ("fixed", "moving") else b["name"]
        shapes.append((b["name"], group, polygon))
    for (an, ag, a), (bn, bg, b) in combinations(shapes, 2):
        if ag != bg and a.intersection(b).area > tolerance_mm2:
            issues.append(f"material overlap: {an} / {bn}")
    return issues


def section_frame(s: Section, m: Mechanism, p: Point) -> dict:
    # Invalid optimizers can return finite r,z. They are NOT solved poses.
    solved = p.lower is not None and p.upper is not None
    belt, radius = belt_polygon(s, p.x * 1000)
    start = s.spring_start + p.x * 1000
    spring_centers = [[float(z), r] for r in (-6.25, 6.25)
                      for z in np.linspace(start + .8, s.spring_end - .8, 9)]
    frame = dict(x_mm=1000*p.x, belt=belt, belt_radius=radius,
                 block=block_polygon(m, p) if solved else [],
                 com=[1000*p.axial, 1000*p.radial] if solved else None,
                 spring_centers=spring_centers, spring_length=s.spring_end-start,
                 pose_valid=solved)
    frame["issues"] = validate_solids(placed_bodies(s, frame))
    if radius - s.belt_height/2 < s.root or radius + s.belt_height/2 > s.rim:
        frame["issues"].append("belt outside conical faces")
    if frame["spring_length"] < 9 * 1.6:
        frame["issues"].append("reference spring coil bind")
    return frame


def render_section(axis, s: Section, frame: dict, p: Point, *, labels=True):
    """Static rendering consumes the same scene and frames as the browser."""
    from matplotlib.patches import Polygon as Patch, Circle
    for b in placed_bodies(s, frame):
        k = b["kind"]
        axis.add_patch(Patch(b["points"], closed=True, facecolor=FILLS[k],
                             edgecolor=COLORS[k], lw=1.1,
                             hatch="///" if k in ("fixed", "moving") else None))
    for t in s.tracks:
        xy = np.array(_shift(t["points"], frame["x_mm"] if t["moving"] else 0))
        axis.plot(xy[:,0], xy[:,1], color=COLORS[t["kind"]], lw=2.5)
    for z,r in frame["spring_centers"]:
        axis.add_patch(Circle((z,r), .8, fc=FILLS["spring"], ec=COLORS["spring"], lw=.6))
    if s.path:
        path = np.array(s.path)
        axis.plot(path[:,0], path[:,1], ":", color=COLORS["block"], lw=1)
    if frame["com"]:
        axis.plot(*frame["com"], "o", ms=4, color="#203247")
        for c,N,kind in ((p.lower,p.N_lower,"fixed"),(p.upper,p.N_upper,"moving")):
            z,r = 1000*c.axial,1000*c.radial
            axis.plot(z,r,"o",ms=5,color=COLORS[kind],mec="white")
            if isfinite(N):
                sign=1 if N>=0 else -1
                axis.annotate("",xy=(z+5*sign*c.normal[1],r+5*sign*c.normal[0]),xytext=(z,r),
                              arrowprops=dict(arrowstyle="->",color=COLORS[kind],lw=1.2))
    if labels:
        for lab in s.labels:
            axis.text(lab["at"][0] + (frame["x_mm"] if lab["kind"] == "moving" else 0), lab["at"][1], lab["text"], color=COLORS[lab["kind"]], ha="center", fontsize=7, weight="bold")
        axis.text((s.spring_start+s.spring_end)/2,-14,"Coaxial spring",ha="center",fontsize=8)
        if not frame["pose_valid"]:
            axis.text(.03,.86,"No compatible weight pose",transform=axis.transAxes,color="#a32839",fontsize=9)
    if frame["issues"]:
        axis.text(.02,.94,"Section invalid: " + "; ".join(frame["issues"]),
                  transform=axis.transAxes,color="#a32839",fontsize=7,wrap=True)
    axis.axhline(0,color="#6d7b8c",ls=(0,(6,3,1,3)),lw=.8)
    axis.set(xlim=s.bounds[:2],ylim=s.bounds[2:],xlabel="Axial position z [mm]",ylabel="Radius r [mm]")
    axis.set_aspect("equal")
    axis.grid(alpha=.12)
    axis.set_title(f"Primary section · x = {frame['x_mm']:.1f} mm",fontsize=11)
