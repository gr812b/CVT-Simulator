"""Compiled fixed-orientation sliding blocks on a selected two-contact branch.

SI units throughout. Profiles are meridional graphs, not arbitrary CAD solids.
Mass is the total identical set; tensors below are centroidal inertia per unit
mass in the local right-handed (radial, tangential, shaft-axial) frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from typing import Literal

import numpy as np
from scipy.interpolate import BPoly
from scipy.optimize import brentq
from scipy.integrate import quad

from ._numerics import contact_roundoff_tolerance
from .centrifugal_inertia import CentrifugalInertiaSample
from .forces.centrifugal_inertia import CentrifugalInertiaForce
from .sliding_block_geometry import (
    Contact,
    SlidingBlockGeometryError,
    Mechanism,
    Profile,
    _contact,
    _min_gap,
    _contact_minima,
)
from .types import PulleyActuationContext
from cinder.model.cvt.closure import ClosureUnknowns


@dataclass(frozen=True)
class SlidingBlockGeometry:
    """Contact edges relative to a body datum, and an explicit radial branch window.

    The fixed cup is ``lower_track``; ``upper_track`` translates by +x. Their
    supporting solids and the belt cone are outside this meridional contact model.
    """

    lower_track: Profile
    upper_track: Profile
    lower_face: Profile
    upper_face: Profile
    radial_min: float
    radial_max: float
    axial_position_min: float
    axial_position_max: float
    allow_end_contacts: bool = False

    def __post_init__(self):
        for key in (
            "radial_min",
            "radial_max",
            "axial_position_min",
            "axial_position_max",
        ):
            if not isfinite(getattr(self, key)):
                raise ValueError(f"{key} must be finite")
        if not 0 < self.radial_min < self.radial_max:
            raise ValueError("radial branch window must be positive and ordered")
        if not self.axial_position_min < self.axial_position_max:
            raise ValueError("axial branch interval must be ordered")
        if not isinstance(self.allow_end_contacts, bool):
            raise ValueError("allow_end_contacts must be boolean")
        self.mechanism()  # Includes a global positive-thickness check.
        for track in (self.lower_track, self.upper_track):
            if (
                self.radial_min + self.lower_face.left < track.left
                or self.radial_max + self.lower_face.right > track.right
            ):
                raise ValueError(
                    "branch window extends the block footprint outside a track"
                )

    def mechanism(self) -> Mechanism:
        return Mechanism(
            self.lower_track,
            self.upper_track,
            self.lower_face,
            self.upper_face,
            1.0,
            0.0,
            radius_ref=self.radial_min,
            x_min=self.axial_position_min,
            x_max=self.axial_position_max,
        )


@dataclass(frozen=True)
class SlidingBlockMass:
    total_mass: float
    count: int
    com_offset: tuple[float, float, float]
    centroidal_inertia_per_mass: tuple[tuple[float, float, float], ...]

    def __post_init__(self):
        if not isfinite(self.total_mass) or self.total_mass <= 0:
            raise ValueError("total_mass must be finite and positive")
        if (
            isinstance(self.count, bool)
            or not isinstance(self.count, int)
            or self.count < 1
        ):
            raise ValueError("count must be a positive integer")
        c = np.asarray(self.com_offset, dtype=float)
        j = np.asarray(self.centroidal_inertia_per_mass, dtype=float)
        if c.shape != (3,) or not np.all(np.isfinite(c)):
            raise ValueError("com_offset needs three finite components")
        if c[1] != 0:
            raise ValueError(
                "Tangential COM offset gives a mixed kinetic term B; four maps require B=0"
            )
        if j.shape != (3, 3) or not np.all(np.isfinite(j)):
            raise ValueError("centroidal_inertia_per_mass needs a finite 3x3 tensor")
        scale = max(float(np.max(np.abs(j))), 1e-30)
        if not np.allclose(j, j.T, rtol=0, atol=scale * 1e-12):
            raise ValueError("centroidal inertia tensor must be symmetric")
        eigen = np.linalg.eigvalsh(j)
        if eigen[0] < -scale * 1e-12 or eigen[2] > eigen[0] + eigen[1] + scale * 1e-12:
            raise ValueError(
                "centroidal inertia must be positive semidefinite and satisfy triangle inequalities"
            )
        object.__setattr__(self, "com_offset", tuple(map(float, c)))
        object.__setattr__(
            self,
            "centroidal_inertia_per_mass",
            tuple(tuple(map(float, row)) for row in j),
        )

    @classmethod
    def from_profiles(cls, lower, upper, *, width, total_mass, count=1):
        """Uniform prism bounded by two smooth profiles; display mesh is unused.

        Width and profiles are metres; total_mass is the complete set in kg.
        This is a mass-body construction, independent of the selected contacts.
        """
        if not isfinite(width) or width <= 0:
            raise ValueError("tangential width must be finite and positive")
        if (lower.left, lower.right) != (upper.left, upper.right):
            raise ValueError("mass profiles must share one finite radial domain")
        from .sliding_block_geometry import _profile_gap_minimum

        if _profile_gap_minimum(upper, lower, 0, lower.left, lower.right)[0] <= 0:
            raise ValueError("mass profiles intersect or have nonpositive thickness")
        a, b = lower.left, lower.right
        rscale = b - a
        r0 = (a + b) / 2
        low = lower.bounds(a, b)[0]
        high = upper.bounds(a, b)[1]
        zscale = high - low
        z0 = (high + low) / 2
        cuts = sorted(
            {
                0.0,
                1.0,
                *((r - a) / rscale for r in (*lower.knots, *upper.knots) if a < r < b),
            }
        )

        area_scale = None

        def integrate(fun):
            def sample(t):
                r = a + rscale * t
                return fun(
                    t - 0.5,
                    (lower.value(r) - z0) / zscale,
                    (upper.value(r) - z0) / zscale,
                )

            results = [
                quad(
                    sample,
                    left,
                    right,
                    epsabs=0.0 if area_scale is None else 1e-13 * area_scale,
                    epsrel=1e-11,
                    limit=200,
                )
                for left, right in zip(cuts, cuts[1:])
            ]
            value = sum(v for v, _ in results)
            if not isfinite(value) or sum(e for _, e in results) > 1e-10 * (
                abs(value) if area_scale is None else area_scale
            ):
                raise SlidingBlockGeometryError(
                    "Mass quadrature did not resolve the profile moments",
                    code="mass_quadrature",
                    category="numerical",
                )
            return value

        area = integrate(lambda r, lo, hi: hi - lo)
        area_scale = area
        cr = integrate(lambda r, lo, hi: r * (hi - lo)) / area
        cz = integrate(lambda r, lo, hi: (hi - lo) * (hi + lo) / 2) / area
        vr = (
            integrate(lambda r, lo, hi: r * r * (hi - lo)) / area - cr * cr
        ) * rscale**2
        vz = (
            integrate(lambda r, lo, hi: (hi - lo) * (hi * hi + hi * lo + lo * lo) / 3)
            / area
            - cz * cz
        ) * zscale**2
        cov = (
            (
                integrate(lambda r, lo, hi: r * (hi - lo) * (hi + lo) / 2) / area
                - cr * cz
            )
            * rscale
            * zscale
        )
        vt = width**2 / 12
        return cls(
            total_mass,
            count,
            (r0 + cr * rscale, 0.0, z0 + cz * zscale),
            ((vt + vz, 0.0, -cov), (0.0, vr + vz, 0.0), (-cov, 0.0, vr + vt)),
        )

    @classmethod
    def from_section(cls, outline, *, width, total_mass, count=1):
        """Uniform prism from a simple closed (radial, axial) polygon in metres.

        Mass is the complete set, independent of count. The polygon describes
        weight material only. Use measured COM/tensor data for inserts or a
        nonuniform body; contact profiles need not trace the mass outline.
        """
        points = np.asarray(outline, dtype=float)
        if (
            points.ndim != 2
            or points.shape[1] != 2
            or len(points) < 3
            or not np.all(np.isfinite(points))
            or not isfinite(width)
            or width <= 0
        ):
            raise ValueError(
                "section needs finite 2D vertices and a positive tangential width"
            )
        if np.array_equal(points[0], points[-1]):
            points = points[:-1]
        origin = points.mean(axis=0)
        scale = float(np.max(np.ptp(points, axis=0)))
        if scale == 0 or len(points) < 3:
            raise ValueError("section has zero area")
        p = (points - origin) / scale
        q = np.roll(p, -1, axis=0)
        if np.any(np.linalg.norm(q - p, axis=1) <= 64 * np.finfo(float).eps):
            raise ValueError("section has a zero-length edge")

        def orient(a, b, c):
            return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))

        def intersects(a, b, c, d):
            if np.any(
                np.maximum(np.minimum(a, b), np.minimum(c, d))
                > np.minimum(np.maximum(a, b), np.maximum(c, d))
            ):
                return False
            return (
                orient(a, b, c) * orient(a, b, d) <= 0
                and orient(c, d, a) * orient(c, d, b) <= 0
            )

        for i in range(len(p)):
            for j in range(i + 1, len(p)):
                if j == i + 1 or (i == 0 and j == len(p) - 1):
                    continue
                if intersects(p[i], q[i], p[j], q[j]):
                    raise ValueError("section outline intersects itself")
        cross = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
        area = float(np.sum(cross) / 2)
        if abs(area) <= 64 * np.finfo(float).eps:
            raise ValueError("section has zero or numerically unresolved area")
        centre = np.sum((p + q) * cross[:, None], axis=0) / (6 * area)
        er2 = np.sum((p[:, 0] ** 2 + p[:, 0] * q[:, 0] + q[:, 0] ** 2) * cross) / (
            12 * area
        )
        ez2 = np.sum((p[:, 1] ** 2 + p[:, 1] * q[:, 1] + q[:, 1] ** 2) * cross) / (
            12 * area
        )
        erz = np.sum(
            (
                2 * p[:, 0] * p[:, 1]
                + p[:, 0] * q[:, 1]
                + q[:, 0] * p[:, 1]
                + 2 * q[:, 0] * q[:, 1]
            )
            * cross
        ) / (24 * area)
        vr, vz = (np.array([er2, ez2]) - centre**2) * scale**2
        cov = (erz - centre[0] * centre[1]) * scale**2
        centre = origin + scale * centre
        vt = width**2 / 12
        return cls(
            total_mass,
            count,
            (float(centre[0]), 0.0, float(centre[1])),
            ((vt + vz, 0.0, -cov), (0.0, vr + vz, 0.0), (-cov, 0.0, vr + vt)),
        )


@dataclass(frozen=True)
class SlidingBlockSpec:
    geometry: SlidingBlockGeometry
    mass: SlidingBlockMass
    guide: Literal["ideal_fixed_orientation"]

    def __post_init__(self):
        if not isinstance(self.geometry, SlidingBlockGeometry) or not isinstance(
            self.mass, SlidingBlockMass
        ):
            raise TypeError("SlidingBlockSpec requires typed geometry and mass")
        if self.guide != "ideal_fixed_orientation":
            raise ValueError(
                "Only explicit ideal_fixed_orientation guides are supported"
            )


@dataclass(frozen=True)
class SlidingBlockPose:
    datum_radial: float
    datum_axial: float
    radial: float
    axial: float
    r_prime: float
    z_prime: float
    r_second: float
    z_second: float
    lower: Contact
    upper: Contact


@dataclass(frozen=True)
class SlidingBlockReactions:
    """Total-set normals and like local guide components; divide by count per block.

    Guide force is applied through the COM; its moment is a free couple.
    These local components are not a circumferential global vector sum.
    A computed demand is not a verified hardware capacity.
    """

    lower_normal: float
    upper_normal: float
    guide_tangential: float
    guide_moment: tuple[float, float, float] | None
    count: int
    capacity_status: str = "unknown (ideal guide)"
    normal_tolerances: tuple[float, float] = (0.0, 0.0)
    guide_moment_bounds: tuple[tuple[float, float], ...] = ()

    @property
    def contact_margins(self) -> tuple[float, float]:
        """Signed reactions with only numerically unresolved values snapped.

        Raw forces/impulses remain in ``lower_normal`` and ``upper_normal``.
        The resolution follows arithmetic and local tangency residuals, rather
        than a fixed physical deadband.
        """
        return tuple(
            0.0 if abs(value) <= tolerance else value
            for value, tolerance in zip(
                (self.lower_normal, self.upper_normal), self.normal_tolerances
            )
        )

    @property
    def compressive(self) -> bool:
        return min(self.contact_margins) >= 0.0

    @property
    def per_block_guide_moment(self) -> tuple[float, float, float] | None:
        if self.guide_moment is None:
            return None
        return tuple(value / self.count for value in self.guide_moment)

    @property
    def per_block_guide_moment_bounds(self):
        return tuple(
            (a / self.count, b / self.count) for a, b in self.guide_moment_bounds
        )


@dataclass(frozen=True)
class SlidingBlockCompilationReport:
    interval_count: int
    contact_modes: tuple[str, str]
    max_position_error: float
    max_gradient_error: float
    max_curvature_error: float
    # These are measured at three interior validation points per final cell,
    # not a rigorous continuum interpolation-error bound.
    position_tolerance: float = 2e-10
    gradient_tolerance: float = 2e-7
    curvature_tolerance: float = 2e-4
    contact_interval_counts: tuple[int, int] = (1, 1)


def _slope_bounds(p: Profile, a: float, b: float):
    return p.bounds(a, b, 1)


def _active_slope_bounds(m, r0, r1, lower):
    """Bound every possible global gap minimizer over a radial interval.

    A test point supplies a uniform upper bound on the minimum gap. Face
    subintervals whose lower gap bound exceeds it cannot contain contact.
    This works with nonconvex, changing-curvature profiles and multiple minima.
    """
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    middle = (r0 + r1) / 2
    spans = _contact_minima(m, middle, lower=lower)
    u = sum(spans[0]) / 2
    low, high = track.bounds(r0 + u, r1 + u)
    ceiling = face.value(u) - low if lower else high - face.value(u)
    regions = []
    for a, b in zip(
        np.linspace(face.left, face.right, 33)[:-1],
        np.linspace(face.left, face.right, 33)[1:],
    ):
        fl, fh = face.bounds(float(a), float(b))
        tl, th = track.bounds(r0 + float(a), r1 + float(b))
        floor = fl - th if lower else tl - fh
        if floor <= ceiling + 1e-13:
            regions.append((float(a), float(b)))
    if not regions:
        raise SlidingBlockGeometryError(
            "Numerical contact enclosure retained no minimum",
            code="contact_enclosure",
            category="numerical",
            radial_interval=(r0, r1),
        )
    slopes = [v for a, b in regions for v in track.bounds(r0 + a, r1 + b, 1)]
    return (min(slopes), max(slopes)), regions


def _regular_contact_cell(m, r0, r1, lower):
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    a, b = face.left, face.right
    # A single affine track separates the gap into a function of u and an
    # affine function of R. Any isolated minima or flat spans stay fixed;
    # multiple equal minima do not make translation ambiguous.
    if track.kind == "line" or (track.kind == "quadratic" and track.curvature == 0):
        return True
    if track.kind == "spline" and all(
        all(v == 0 for v in row[2:]) for row in track.coefficients
    ):
        return True
    sign = 1 if lower else -1

    def convex_or_endpoint(a, b, allow_left, allow_right):
        fl, fh = face.bounds(a, b, 2)
        tl, th = track.bounds(r0 + a, r1 + b, 2)
        curvature = (fl - th, fh - tl) if lower else (tl - fh, th - fl)

        def derivative(u):
            low, high = track.bounds(r0 + u, r1 + u, 1)
            vals = [sign * (face.gradient(u) - v) for v in (low, high)]
            return min(vals), max(vals)

        da, db = derivative(a), derivative(b)
        fsl, fsh = face.bounds(a, b, 1)
        tsl, tsh = track.bounds(r0 + a, r1 + b, 1)
        gsl, gsh = (fsl - tsh, fsh - tsl) if lower else (tsl - fsh, tsh - fsl)
        if (allow_left and gsl > 0) or (allow_right and gsh < 0):
            return True
        if allow_left and da[0] > 0 and curvature[0] >= 0:
            return True
        if allow_right and db[1] < 0 and curvature[0] >= 0:
            return True
        if curvature[0] > 0 and da[1] < 0 and db[0] > 0:
            return True
        if curvature[1] < 0 and allow_left and allow_right:
            middle = (r0 + r1) / 2
            delta = sign * (
                face.value(a)
                - track.value(middle + a)
                - face.value(b)
                + track.value(middle + b)
            )
            sa = track.bounds(r0 + a, r1 + a, 1)
            sb = track.bounds(r0 + b, r1 + b, 1)
            lipschitz = max(abs(v - w) for v in sa for w in sb)
            return abs(delta) > lipschitz * (r1 - r0) / 2 + 1e-13
        return False

    if convex_or_endpoint(a, b, True, True):
        return True
    _, regions = _active_slope_bounds(m, r0, r1, lower)
    if any(c > old_b + 1e-14 for (_, old_b), (c, _) in zip(regions, regions[1:])):
        return False
    a, b = regions[0][0], regions[-1][1]
    return convex_or_endpoint(a, b, a == face.left, b == face.right)


def _check_contact_regularity(m, r0, r1):
    pending = [(min(r0, r1), max(r0, r1), 0)]
    while pending:
        a, b, depth = pending.pop()
        valid = [_regular_contact_cell(m, a, b, lower) for lower in (True, False)]
        if all(valid):
            continue
        if depth >= 12:
            contact = "lower" if not valid[0] else "upper"
            raise SlidingBlockGeometryError(
                f"Cannot establish a C2 contact envelope on {contact} face in radial interval [{a:g}, {b:g}]; inspect competing minima or a contact-mode transition",
                code="contact_regularity",
                category="numerical",
                radial_interval=(a, b),
                contact=contact,
            )
        middle = (a + b) / 2
        pending.extend(((a, middle, depth + 1), (middle, b, depth + 1)))


def _check_branch(m, r0, r1):
    """Establish monotone closure, with local active-contact bounds if needed."""
    pending, signs = [(r0, r1, 0)], set()
    while pending:
        a, b, depth = pending.pop()
        low = _slope_bounds(
            m.lower_track, a + m.lower_face.left, b + m.lower_face.right
        )
        high = _slope_bounds(
            m.upper_track, a + m.upper_face.left, b + m.upper_face.right
        )
        if max(low[0] - high[1], high[0] - low[1]) <= 0:
            low, _ = _active_slope_bounds(m, a, b, True)
            high, _ = _active_slope_bounds(m, a, b, False)
        separation = max(low[0] - high[1], high[0] - low[1])
        if separation > 0:
            condition = (
                2 + max(abs(v) for v in low) ** 2 + max(abs(v) for v in high) ** 2
            ) / separation
            if condition < 1e3:
                signs.add(1 if low[0] > high[1] else -1)
                continue
        if depth >= 12:
            raise SlidingBlockGeometryError(
                "Numerical branch enclosure cannot establish unique regular motion in radial interval "
                f"[{a:g}, {b:g}]; narrow the branch or inspect its contact singularities",
                code="branch_enclosure",
                category="numerical",
                radial_interval=(a, b),
            )
        middle = (a + b) / 2
        pending.extend(((a, middle, depth + 1), (middle, b, depth + 1)))
    if len(signs) != 1:
        raise ValueError(
            "Selected radial window crosses a reversal or singularity of closure"
        )


def _exact_pose(
    g: SlidingBlockGeometry, x: float
) -> tuple[np.ndarray, tuple[Contact, Contact]]:
    m = g.mechanism()

    def pose_at_radius(r):
        l, _ = _min_gap(m, r, 0.0, 0.0, lower=True)
        h, _ = _min_gap(m, r, 0.0, 0.0, lower=False)
        return -l - h, -l

    def residual(r):
        return pose_at_radius(r)[0] - x

    try:
        r = brentq(residual, g.radial_min, g.radial_max, xtol=5e-16)
    except ValueError as exc:
        raise SlidingBlockGeometryError(
            f"No double contact at x={x:g} within the selected radial window: {exc}",
            code="branch_domain",
            category="configuration",
            axial_position=x,
            radial_interval=(g.radial_min, g.radial_max),
        ) from exc
    _, z = pose_at_radius(r)
    sets = tuple(_contact_minima(m, r, lower=lo) for lo in (True, False))
    contacts = []
    for lower, spans in zip((True, False), sets):
        try:
            contacts.append(
                _contact(m, r, x, sum(spans[0]) / 2, lower=lower, intervals=spans)
            )
        except ValueError as exc:
            raise SlidingBlockGeometryError(
                str(exc),
                code="contact_kinematics",
                category="regularity",
                axial_position=x,
                contact="lower" if lower else "upper",
            ) from exc
    contacts = tuple(contacts)
    lo, hi = contacts
    if np.linalg.cond([[-lo.slope, 1], [hi.slope, -1]]) >= 1e3:
        raise ValueError("Ill-conditioned contact kinematics")
    rp = 1 / (lo.slope - hi.slope)
    zp = lo.slope * rp
    rpp = -(lo.slope_derivative - hi.slope_derivative) * rp**3
    zpp = lo.slope * rpp + lo.slope_derivative * rp**2
    data = [[r, z], [rp, zp], [rpp, zpp]]
    for c, spans, face, track in zip(
        contacts, sets, (m.lower_face, m.upper_face), (m.lower_track, m.upper_track)
    ):
        for span in spans:
            for u in span:
                up = upp = 0.0
                is_span = span[1] - span[0] > 2e-13
                if is_span:
                    if not any(
                        abs(u - v) < 2e-12 for v in (face.left, face.right, *face.knots)
                    ):
                        up, upp = (
                            -rp,
                            -rpp,
                        )  # moving across a fixed track-piece boundary
                elif u != face.left and u != face.right:
                    bc, tc = face.second(u), track.second(r + u)
                    if tc != 0:
                        if abs(bc - tc) <= 128 * np.finfo(float).eps * max(
                            abs(bc), abs(tc)
                        ):
                            raise ValueError(
                                "Contact migration is singular at the selected pose"
                            )
                        ur = tc / (bc - tc)
                        urr = (
                            track.derivative(r + u, 3) * (1 + ur) ** 2
                            - face.derivative(u, 3) * ur**2
                        ) / (bc - tc)
                        up, upp = ur * rp, ur * rpp + urr * rp**2
                for row, value in zip(data, (u, up, upp)):
                    row.append(value)
    return np.array(data), contacts


@lru_cache(maxsize=32)
def _compile_motion(g: SlidingBlockGeometry):
    m = g.mechanism()
    _check_branch(m, g.radial_min, g.radial_max)
    initial, contacts = _exact_pose(g, g.axial_position_min)
    final, _ = _exact_pose(g, g.axial_position_max)
    _check_contact_regularity(m, float(initial[0, 0]), float(final[0, 0]))
    counts = tuple(len(c.u_intervals) for c in contacts)
    modes_seen = [set(), set()]

    def exact(x):
        data, contacts = _exact_pose(g, x)
        if tuple(len(c.u_intervals) for c in contacts) != counts:
            raise SlidingBlockGeometryError(
                f"Contact-set topology changes at x={x:g}; split at the transition and check motion regularity",
                code="contact_topology_transition",
                category="implementation",
                axial_position=x,
            )
        for i, c in enumerate(contacts):
            if "end contact" in c.mode and not g.allow_end_contacts:
                raise ValueError(
                    f"End contacts require explicit allow_end_contacts=True (x={x:g})"
                )
            modes_seen[i].add(c.mode)
        return data

    knots = list(np.linspace(g.axial_position_min, g.axial_position_max, 9))
    samples = {x: exact(x) for x in knots}
    tolerances = np.array([2e-10, 2e-7, 2e-4])
    for _ in range(10):
        spline = BPoly.from_derivatives(
            knots, [samples[x] for x in knots], extrapolate=False
        )
        failed, worst = [], np.zeros(3)
        for left, right in zip(knots[:-1], knots[1:]):
            for fraction in (0.25, 0.5, 0.75):
                x = left + (right - left) * fraction
                target = exact(x)
                difference = np.abs(
                    np.array([spline(x, nu=i) for i in range(3)]) - target
                )
                # Contact coordinates need accurate values, not globally C2
                # derivatives. Only body motion derivatives enter the boundary.
                error = np.array(
                    [
                        np.max(difference[0]),
                        np.max(difference[1, :2]),
                        np.max(difference[2, :2]),
                    ]
                )
                worst = np.maximum(worst, error)
                if np.any(error > tolerances):
                    failed.append(x)
                    samples[x] = target
        if not failed:
            spline.c.setflags(write=False)
            spline.x.setflags(write=False)
            report = SlidingBlockCompilationReport(
                len(knots) - 1,
                tuple(" / ".join(sorted(v)) for v in modes_seen),
                *map(float, worst),
                contact_interval_counts=counts,
            )
            return spline, report
        knots = sorted(set(knots + failed))
        if len(knots) > 4097:
            break
    raise SlidingBlockGeometryError(
        "Motion/contact interpolation could not meet the declared tolerances; inspect contact transitions and smoothness",
        code="interpolation_tolerance",
        category="numerical",
    )


class SlidingBlockInertiaMap:
    """Compile once; evaluate one common C2 motion representation in the RHS."""

    def __init__(self, spec: SlidingBlockSpec):
        if not isinstance(spec, SlidingBlockSpec):
            raise TypeError("Expected SlidingBlockSpec")
        self._spec = spec
        self._motion, self.compilation_report = _compile_motion(spec.geometry)
        # Positive COM radius throughout the selected radial window.
        if spec.geometry.radial_min + spec.mass.com_offset[0] <= 0:
            raise ValueError("COM crosses or reaches the shaft axis")

    @property
    def spec(self) -> SlidingBlockSpec:
        return self._spec

    @property
    def axial_position_min(self):
        return self.spec.geometry.axial_position_min

    @property
    def axial_position_max(self):
        return self.spec.geometry.axial_position_max

    def _kinematics(self, x):
        if (
            not isfinite(x)
            or not self.axial_position_min <= x <= self.axial_position_max
        ):
            raise ValueError("Sliding-block position is outside its compiled interval")
        rz = self._motion(x)[:2].copy()
        rz += np.asarray(self.spec.mass.com_offset)[[0, 2]]
        return rz, self._motion(x, nu=1)[:2], self._motion(x, nu=2)[:2]

    def evaluate(self, axial_position: float) -> CentrifugalInertiaSample:
        (r, _), (rp, zp), (rpp, zpp) = self._kinematics(axial_position)
        m = self.spec.mass
        return CentrifugalInertiaSample(
            float(m.total_mass * (rp * rp + zp * zp)),
            float(2 * m.total_mass * (rp * rpp + zp * zpp)),
            float(m.total_mass * (r * r + m.centroidal_inertia_per_mass[2][2])),
            float(2 * m.total_mass * r * rp),
        )

    def pose(self, x: float) -> SlidingBlockPose:
        (r, z), (rp, zp), (rpp, zpp) = self._kinematics(x)
        m = self.spec.geometry
        rd, zd = r - self.spec.mass.com_offset[0], z - self.spec.mass.com_offset[2]
        contacts = []
        cursor = 2
        paths = self._motion(x)
        for lower, count in zip(
            (True, False), self.compilation_report.contact_interval_counts
        ):
            face = m.lower_face if lower else m.upper_face
            spans = []
            for _ in range(count):
                a, b = map(float, paths[cursor : cursor + 2])
                a, b = (min(face.right, max(face.left, v)) for v in (a, b))
                spans.append((a, b))
                cursor += 2
            u = sum(spans[0]) / 2
            contacts.append(_contact(m, rd, x, u, lower=lower, intervals=tuple(spans)))
        return SlidingBlockPose(
            *map(float, (rd, zd, r, z, rp, zp, rpp, zpp)), *contacts
        )

    def reactions(
        self, x: float, *, omega: float, alpha: float, xdot: float, xddot: float
    ) -> SlidingBlockReactions:
        if not all(isfinite(v) for v in (omega, alpha, xdot, xddot)):
            raise ValueError("Operating state must be finite")
        p = self.pose(x)
        mass = self.spec.mass.total_mass
        terms = mass * np.array(
            [
                [p.r_prime * xddot, p.r_second * xdot**2, -p.radial * omega**2],
                [p.z_prime * xddot, p.z_second * xdot**2, 0.0],
            ]
        )
        normals, tolerances = self._resolve_normals(p, terms)
        force = mass * (p.radial * alpha + 2 * omega * p.r_prime * xdot)
        tensor = mass * np.array(self.spec.mass.centroidal_inertia_per_mass)
        spin = np.array([0.0, 0.0, omega])
        moment = tensor @ np.array([0.0, 0.0, alpha]) + np.cross(spin, tensor @ spin)
        return self._wrench(p, normals, force, moment, tolerances)

    def impulses(
        self, x: float, *, delta_xdot: float, delta_omega: float
    ) -> SlidingBlockReactions:
        """Return retained-contact demands for a jump at fixed configuration.

        Here the normal and guide-force fields are impulses in N s, and the
        guide-moment field is an angular impulse in N m s.
        """
        if not all(isfinite(v) for v in (delta_xdot, delta_omega)):
            raise ValueError("Velocity jumps must be finite")
        p = self.pose(x)
        mass = self.spec.mass.total_mass
        normals, tolerances = self._resolve_normals(
            p, mass * np.array([[p.r_prime], [p.z_prime]]) * delta_xdot
        )
        moment = (
            mass
            * np.array(self.spec.mass.centroidal_inertia_per_mass)
            @ np.array([0.0, 0.0, delta_omega])
        )
        return self._wrench(
            p, normals, mass * p.radial * delta_omega, moment, tolerances
        )

    @staticmethod
    def _resolve_normals(p, terms):
        directions = np.column_stack([p.lower.normal, p.upper.normal])
        normals = np.linalg.solve(directions, np.sum(terms, axis=1))
        # Exact constraint motion obeys q' . n_lower = 0 and
        # q' . n_upper = n_upper,z. The interpolated motion leaves a small,
        # directly measurable residual in these two virtual-work identities.
        # Its absolute work error bounds the discrepancy of either recovered
        # normal, after division by that contact's axial normal component.
        residual = np.array([p.r_prime, p.z_prime]) @ directions
        residual[1] -= p.upper.normal[1]
        work_error = float(np.abs(residual) @ np.abs(normals))
        scales = np.abs(np.linalg.inv(directions)) @ np.sum(np.abs(terms), axis=1)
        tolerances = tuple(
            work_error / abs(directions[1, i]) + contact_roundoff_tolerance(scale)
            for i, scale in enumerate(scales)
        )
        return normals, tolerances

    def _wrench(self, p, normals, force, moment, tolerances):
        # Pressure may be anywhere on each contact set. Constant normal direction
        # determines total force; its moment is affine in the pressure centroid.
        lower_bound, upper_bound = moment.copy(), moment.copy()
        unique = True
        for c, n in zip((p.lower, p.upper), normals):
            spans = c.u_intervals or ((c.u, c.u),)
            coordinates = [v for pair in spans for v in pair]
            unique = unique and max(coordinates) - min(coordinates) <= 2e-13
            values = []
            track = (
                self.spec.geometry.lower_track
                if c is p.lower
                else self.spec.geometry.upper_track
            )
            axial_shift = c.axial - track.value(c.radial)
            for u in coordinates:
                r = p.datum_radial + u
                z = track.value(r) + axial_shift
                arm = np.array([r - p.radial, 0, z - p.axial])
                values.append(
                    -np.cross(arm, n * np.array([c.normal[0], 0, c.normal[1]]))
                )
            lower_bound += np.min(values, axis=0)
            upper_bound += np.max(values, axis=0)
        bounds = tuple((float(a), float(b)) for a, b in zip(lower_bound, upper_bound))
        return SlidingBlockReactions(
            *map(float, normals),
            float(force),
            (
                tuple(map(float, lower_bound))
                if unique or np.array_equal(lower_bound, upper_bound)
                else None
            ),
            self.spec.mass.count,
            normal_tolerances=tolerances,
            guide_moment_bounds=bounds,
        )


class SlidingBlockFlyweightForce(CentrifugalInertiaForce):
    """Common inertia mechanics plus sliding-block contact and impulse policy."""

    def __init__(self, spec: SlidingBlockSpec):
        self._spec = spec
        super().__init__(SlidingBlockInertiaMap(spec))

    @property
    def spec(self) -> SlidingBlockSpec:
        return self._spec

    def _sample(self, context: PulleyActuationContext):
        if context.helical_coupling is not None:
            raise ValueError(
                "Sliding-block tracks must co-rotate with the shaft; relative sheave helix rotation is unsupported"
            )
        return super()._sample(context)

    def contact_reactions(
        self, context: PulleyActuationContext, unknowns: ClosureUnknowns
    ):
        if context.axial_acceleration is None or context.closure_channels is None:
            raise ValueError(
                "Sliding-block reactions need the solved host acceleration channels"
            )
        self._sample(context)
        return self.inertia_map.reactions(
            context.axial_position,
            omega=context.shaft_speed,
            alpha=unknowns[context.closure_channels.shaft_angular_acceleration],
            xdot=context.axial_speed,
            xddot=context.axial_acceleration.evaluate(unknowns),
        )

    def compressive_contact_margins(self, context, unknowns):
        reactions = self.contact_reactions(context, unknowns)
        return (
            ("fixed_track", reactions.contact_margins[0]),
            ("moving_track", reactions.contact_margins[1]),
        )

    def impulse_contact_margins(
        self, before: PulleyActuationContext, after: PulleyActuationContext
    ):
        self._sample(after)
        if abs(before.axial_position - after.axial_position) > 1e-8:
            raise ValueError(
                "Impulse validation requires a common contact configuration"
            )
        reactions = self.inertia_map.impulses(
            after.axial_position,
            delta_xdot=after.axial_speed - before.axial_speed,
            delta_omega=after.shaft_speed - before.shaft_speed,
        )
        return (
            ("fixed_track", reactions.contact_margins[0]),
            ("moving_track", reactions.contact_margins[1]),
        )
