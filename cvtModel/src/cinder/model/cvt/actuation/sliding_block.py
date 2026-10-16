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

from ._numerics import contact_roundoff_tolerance
from .centrifugal_inertia import CentrifugalInertiaSample
from .forces.centrifugal_inertia import CentrifugalInertiaForce
from .sliding_block_geometry import (
    Contact,
    Mechanism,
    Profile,
    _contact,
    _min_gap,
    curvature_bounds,
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
    guide_moment: tuple[float, float, float]
    count: int
    capacity_status: str = "unknown (ideal guide)"
    normal_tolerances: tuple[float, float] = (0.0, 0.0)

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
    def per_block_guide_moment(self) -> tuple[float, float, float]:
        return tuple(value / self.count for value in self.guide_moment)


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


def _slope_bounds(p: Profile, a: float, b: float):
    return min(p.gradient(a), p.gradient(b)), max(p.gradient(a), p.gradient(b))


def _branch_mode(m: Mechanism, r0: float, r1: float, lower: bool) -> str:
    """Certify one gap-minimizer mode over the entire radial window.

    Supported profiles have a constant curvature sign and monotone slope.
    Curvature intervals certify convexity/concavity of the gap. For concave
    gaps the difference of endpoint values is monotone in radial position.
    This conservative test rejects ambiguous profiles and mode transitions.
    """
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    a, b = face.left, face.right
    flo, fhi = curvature_bounds(face, a, b)
    tlo, thi = curvature_bounds(track, r0 + a, r1 + b)
    sign = 1 if lower else -1
    clo, chi = (flo - thi, fhi - tlo) if lower else (tlo - fhi, thi - flo)
    if clo < -1e-12 and chi > 1e-12:
        raise ValueError(
            "Gap curvature cannot be certified throughout the selected branch"
        )

    def derivative_range(u):
        vals = [sign * (face.gradient(u) - track.gradient(r + u)) for r in (r0, r1)]
        return min(vals), max(vals)

    if clo >= -1e-12:
        da, db = derivative_range(a), derivative_range(b)
        if da[0] > 1e-10:
            return "left"
        if db[1] < -1e-10:
            return "right"
        if da[1] < -1e-10 and db[0] > 1e-10 and clo > 1e-10:
            return "interior"
    if chi <= 1e-12:
        delta = [
            sign
            * (face.value(a) - track.value(r + a) - face.value(b) + track.value(r + b))
            for r in (r0, r1)
        ]
        if min(delta) > 1e-12:
            return "right"
        if max(delta) < -1e-12:
            return "left"
    raise ValueError(
        "Contact mode changes, is conformal, or is ambiguous on this branch; split the interval"
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
        raise ValueError(
            f"No double contact at x={x:g} within the selected radial window: {exc}"
        ) from exc
    _, z = pose_at_radius(r)
    contacts = tuple(
        _contact(m, r, x, _min_gap(m, r, z, x, lower=lo)[1], lower=lo)
        for lo in (True, False)
    )
    lo, hi = contacts
    if np.linalg.cond([[-lo.slope, 1], [hi.slope, -1]]) >= 1e3:
        raise ValueError("Ill-conditioned contact kinematics")
    rp = 1 / (lo.slope - hi.slope)
    zp = lo.slope * rp
    rpp = -(lo.slope_derivative - hi.slope_derivative) * rp**3
    zpp = lo.slope * rpp + lo.slope_derivative * rp**2
    data = [[r, z], [rp, zp], [rpp, zpp]]
    for c, face, track in zip(
        contacts, (m.lower_face, m.upper_face), (m.lower_track, m.upper_track)
    ):
        up = upp = 0.0
        if c.mode == "interior tangent":

            def third(profile, coordinate):
                if profile.kind != "circle":
                    return 0.0
                d = coordinate - profile.origin
                return (
                    3
                    * profile.circle_sign
                    * profile.radius**2
                    * d
                    / (profile.radius**2 - d * d) ** 2.5
                )

            bc, tc = face.second(c.u), track.second(r + c.u)
            ur = tc / (bc - tc)
            urr = (
                third(track, r + c.u) * (1 + ur) ** 2 - third(face, c.u) * ur**2
            ) / (bc - tc)
            up, upp = ur * rp, ur * rpp + urr * rp**2
        for row, value in zip(data, (c.u, up, upp)):
            row.append(value)
    return np.array(data), contacts


@lru_cache(maxsize=32)
def _compile_motion(g: SlidingBlockGeometry):
    m = g.mechanism()
    # Disjoint slope bounds establish uniqueness of x(r) over the explicit
    # radial branch window. No claim is made about other disconnected windows.
    a, b = g.lower_face.left, g.lower_face.right
    low_slopes = _slope_bounds(g.lower_track, g.radial_min + a, g.radial_max + b)
    h = _slope_bounds(g.upper_track, g.radial_min + a, g.radial_max + b)
    separation = max(low_slopes[0] - h[1], h[0] - low_slopes[1])
    if separation <= 0:
        raise ValueError(
            "Track-slope bounds do not establish a unique nonsingular branch"
        )
    # ||A||_F^2 / |det A| bounds the 2-norm condition number.
    if (
        2 + max(abs(v) for v in low_slopes) ** 2 + max(abs(v) for v in h) ** 2
    ) / separation >= 1e3:
        raise ValueError("Ill-conditioned branch window")
    modes = tuple(
        _branch_mode(m, g.radial_min, g.radial_max, lo) for lo in (True, False)
    )
    if not g.allow_end_contacts and any(mode != "interior" for mode in modes):
        raise ValueError("End contacts require explicit allow_end_contacts=True")
    knots = list(np.linspace(g.axial_position_min, g.axial_position_max, 9))
    samples = {x: _exact_pose(g, x)[0] for x in knots}
    tolerances = np.array([2e-10, 2e-7, 2e-4])
    for _ in range(10):
        spline = BPoly.from_derivatives(
            knots, [samples[x] for x in knots], extrapolate=False
        )
        failed, worst = [], np.zeros(3)
        for left, right in zip(knots[:-1], knots[1:]):
            for fraction in (0.25, 0.5, 0.75):
                x = left + (right - left) * fraction
                exact = _exact_pose(g, x)[0]
                error = np.max(
                    np.abs(np.array([spline(x, nu=i) for i in range(3)]) - exact),
                    axis=1,
                )
                worst = np.maximum(worst, error)
                if np.any(error > tolerances):
                    failed.append(x)
                    samples[x] = exact
        if not failed:
            spline.c.setflags(write=False)
            spline.x.setflags(write=False)
            report = SlidingBlockCompilationReport(
                len(knots) - 1, modes, *map(float, worst)
            )
            return spline, report
        knots = sorted(set(knots + failed))
        if len(knots) > 4097:
            break
    raise ValueError(
        "Motion interpolation could not meet the declared derivative tolerances"
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
        for lower, u, mode in zip(
            (True, False), self._motion(x)[2:], self.compilation_report.contact_modes
        ):
            face = m.lower_face if lower else m.upper_face
            if mode == "left":
                u = face.left
            elif mode == "right":
                u = face.right
            contacts.append(_contact(m, rd, x, u, lower=lower))
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
        for c, n in zip((p.lower, p.upper), normals):
            arm = np.array([c.radial - p.radial, 0.0, c.axial - p.axial])
            moment -= np.cross(arm, n * np.array([c.normal[0], 0.0, c.normal[1]]))
        return SlidingBlockReactions(
            *map(float, normals),
            float(force),
            tuple(map(float, moment)),
            self.spec.mass.count,
            normal_tolerances=tolerances,
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
