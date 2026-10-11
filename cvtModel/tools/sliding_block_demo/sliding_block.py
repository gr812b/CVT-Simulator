"""Research prototype: fixed-orientation, two-contact sliding centrifugal weights.

All distances are metres, forces newtons.  x moves the upper track +axially;
(r, z) denotes the centre of mass of one representative block.  The entire
symmetric set has TOTAL mass M; the block count is never a force multiplier.

Each face is a graph z=f(radial_coordinate), with a specified finite interval.
Gap is the minimum *signed axial separation* along an overlapping radial
footprint.  Both active gaps are zero.  This is intentionally a 2-D meridional
ideal-contact model, NOT a 3-D saddle-contact or elastic-pressure model.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import hypot, isfinite, sqrt
from typing import Literal

import numpy as np
from scipy.optimize import least_squares, minimize_scalar


@dataclass(frozen=True)
class Profile:
    """Line, quadratic curve, or (unrotated) circular-arc graph z=f(r).

    For circle: z = offset + sign*(radius - sqrt(radius**2-(r-origin)**2)).
    All profiles have an explicit valid radial interval [left, right].
    """

    kind: Literal["line", "quadratic", "circle"]
    origin: float
    offset: float = 0.0
    slope: float = 0.0
    curvature: float = 0.0
    radius: float = 0.0
    circle_sign: int = 1
    left: float = -1.0
    right: float = 1.0

    def __post_init__(self) -> None:
        if not self.left < self.right:
            raise ValueError("profile needs left < right")
        if self.kind == "circle":
            if self.radius <= 0 or self.circle_sign not in (-1, 1):
                raise ValueError("circle needs positive radius and sign +/-1")
            if max(abs(self.left - self.origin), abs(self.right - self.origin)) >= self.radius:
                raise ValueError("circular profile domain exceeds open semicircle")
        elif self.kind not in ("line", "quadratic"):
            raise ValueError(f"unknown profile: {self.kind}")

    def value(self, r: float) -> float:
        d = r - self.origin
        if self.kind == "circle":
            return self.offset + self.circle_sign * (self.radius - sqrt(self.radius**2 - d**2))
        return self.offset + self.slope * d + (0.5 * self.curvature * d**2 if self.kind == "quadratic" else 0)

    def gradient(self, r: float) -> float:
        d = r - self.origin
        if self.kind == "circle":
            return self.circle_sign * d / sqrt(self.radius**2 - d**2)
        return self.slope + (self.curvature * d if self.kind == "quadratic" else 0)

    def second(self, r: float) -> float:
        d = r - self.origin
        if self.kind == "circle":
            return self.circle_sign * self.radius**2 / (self.radius**2 - d**2) ** 1.5
        return self.curvature if self.kind == "quadratic" else 0.0


@dataclass(frozen=True)
class Mechanism:
    lower_track: Profile   # stationary track: lower contact
    upper_track: Profile   # moves by +x in axial z
    lower_face: Profile    # block face in COM-relative radial coordinate u
    upper_face: Profile
    total_mass: float
    gyration_radius: float    # centroidal shaft-axis inertia per total mass: J_C=M*k^2
    display_count: int = 1  # display/part measurement only; NEVER multiplies inertia
    radius_ref: float = 0.054
    x_max: float = 0.014
    name: str = "sliding weight"

    def __post_init__(self) -> None:
        if self.total_mass <= 0 or self.gyration_radius < 0:
            raise ValueError("mass must be >0 and gyration radius nonnegative")
        if self.display_count < 1 or self.radius_ref <= 0 or self.x_max <= 0:
            raise ValueError("count, reference radius, and travel must be positive")
        if (self.lower_face.left, self.lower_face.right) != (self.upper_face.left, self.upper_face.right):
            raise ValueError("demo expects same radial interval for both block faces")
        for u in np.linspace(self.lower_face.left, self.lower_face.right, 21):
            if self.upper_face.value(float(u)) <= self.lower_face.value(float(u)):
                raise ValueError("block faces intersect: upper must stay above lower")


@dataclass(frozen=True)
class Contact:
    u: float                  # local radial coordinate on weight
    radial: float             # contact radial coordinate relative to shaft
    axial: float              # world contact axial coordinate
    slope: float              # slope of the contacted TRACK
    slope_derivative: float   # d(track slope)/d(block COM radial shift)
    normal: tuple[float, float]  # normal on weight (radial, axial)
    mode: str                 # interior tangent / end contact / conformal


@dataclass(frozen=True)
class Point:
    x: float
    radial: float
    axial: float
    r_prime: float
    z_prime: float
    r_second: float
    z_second: float
    M_f: float
    M_f_prime: float
    J_f: float
    J_f_prime: float
    N_lower: float          # total normal reaction, across all weights
    N_upper: float
    guide_tangential: float # magnitude/sign of needed tangential guide reaction
    guide_rocking_moment: float # moment needed to hold block orientation, across all weights
    F_interface: float
    F_from_contact: float
    lower: Contact | None
    upper: Contact | None
    issues: tuple[str, ...]

    @property
    def admissible(self) -> bool:
        return not self.issues

    @property
    def status(self) -> str:
        return "PASS" if self.admissible else ", ".join(self.issues)


def _min_gap(m: Mechanism, radial: float, axial: float, x: float, *, lower: bool) -> tuple[float, float]:
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    a, b = face.left, face.right
    if radial + a < track.left - 1e-11 or radial + b > track.right + 1e-11:
        raise ValueError("block footprint extends outside modelled track domain")

    def gap(u: float) -> float:
        if lower:
            return axial + face.value(u) - track.value(radial + u)
        return track.value(radial + u) + x - axial - face.value(u)

    # Find GLOBAL minimum over bounded profile. A single bounded minimization
    # silently misses separated local minima on a wavy/non-convex surface.
    grid = np.linspace(a, b, 25)
    samples = [gap(float(u)) for u in grid]
    candidates = [(samples[0], a), (samples[-1], b)]
    for i in range(1, len(grid) - 1):
        if samples[i] <= samples[i - 1] and samples[i] <= samples[i + 1]:
            opt = minimize_scalar(gap, bounds=(float(grid[i - 1]), float(grid[i + 1])), method="bounded", options={"xatol": 1e-13})
            candidates.append((float(opt.fun), float(opt.x)))
    # Minima on every grid segment also catches poorly resolved nonconvex faces.
    # For the named examples, at most one smooth local minimum exists.
    return min(candidates, key=lambda item: item[0])


def calibrate_zero(m: Mechanism) -> Mechanism:
    """Choose the two track axial offsets so both contacts close at (r_ref, z=0, x=0)."""
    lo_gap, _ = _min_gap(m, m.radius_ref, 0.0, 0.0, lower=True)
    lo = replace(m.lower_track, offset=m.lower_track.offset + lo_gap)
    intermediate = replace(m, lower_track=lo)
    hi_gap, _ = _min_gap(intermediate, m.radius_ref, 0.0, 0.0, lower=False)
    hi = replace(m.upper_track, offset=m.upper_track.offset - hi_gap)
    return replace(intermediate, upper_track=hi)


def _contact(m: Mechanism, radial: float, x: float, u: float, *, lower: bool) -> Contact:
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    R = radial + u
    slope = track.gradient(R)
    fc = track.second(R)
    bc = face.second(u)
    endpoint = min(abs(u - face.left), abs(u - face.right)) <= 5e-8
    # The envelope theorem gives the gap gradient, even if u moves.
    # For an interior tangent: face'' * du/dr = track''*(1+du/dr).
    if not endpoint and abs(bc - fc) > 1e-8:
        du_dr = fc / (bc - fc)
        mode = "interior tangent"
    elif not endpoint and abs(bc - fc) <= 1e-8:
        # Stationary flat-on-flat conformal line contacts are okay for force
        # resultants, but their load pressure distribution is undetermined.
        du_dr = 0.0
        mode = "conformal (undetermined contact distribution)"
    else:
        du_dr = 0.0
        mode = "end contact (rounded nose assumed)"
    slope_derivative = fc * (1 + du_dr)
    if lower:
        nr, nz = -slope, 1.0
        world_axial = track.value(R)
    else:
        nr, nz = slope, -1.0
        world_axial = track.value(R) + x
    length = hypot(nr, nz)
    return Contact(u, R, world_axial, slope, slope_derivative, (nr / length, nz / length), mode)


def _invalid(x: float, reason: str, radial: float = float("nan"), axial: float = float("nan")) -> Point:
    n = float("nan")
    return Point(x, radial, axial, *(n,) * 14, None, None, (reason,))


def evaluate(
    m: Mechanism, x: float, *, omega: float = 350.0, alpha: float = 0.0,
    xdot: float = 0.0, xddot: float = 0.0, guess: tuple[float, float] | None = None,
    max_condition: float = 1e3, allow_end_contacts: bool = True,
) -> Point:
    """Solve both active gaps then check geometry, compressive normals and v4 maps.

    Reacted loads depend on the *assumed operating accelerations*. This does NOT
    solve CINDER's coupled shift acceleration. It probes whether its assumed
    two-contact branch could remain closed at this instantaneous state.
    """
    if not (0 <= x <= m.x_max):
        return _invalid(x, "travel outside configured range")
    face = m.lower_face
    radius_min = max(m.lower_track.left, m.upper_track.left) - face.left
    radius_max = min(m.lower_track.right, m.upper_track.right) - face.right
    radius_min = max(radius_min, 1.0e-5)
    if radius_min >= radius_max:
        return _invalid(x, "no shared track footprint")
    rguess, zguess = guess if guess is not None else (m.radius_ref + x * 0.4, 0.4 * x)
    rguess = float(np.clip(rguess, radius_min + 1e-10, radius_max - 1e-10))
    def residual(y: np.ndarray) -> tuple[float, float]:
        r, z = float(y[0]), float(y[1])
        l, _ = _min_gap(m, r, z, x, lower=True)
        h, _ = _min_gap(m, r, z, x, lower=False)
        return l, h
    try:
        opt = least_squares(residual, (rguess, zguess), bounds=((radius_min, -0.1), (radius_max, 0.1)),
                            xtol=1e-13, ftol=1e-13, gtol=1e-13, max_nfev=120)
        r, z = map(float, opt.x)
        if max(abs(a) for a in opt.fun) > 2.0e-8:
            return _invalid(x, "track limit / no compatible double contact" if (abs(r-radius_min)<1e-7 or abs(r-radius_max)<1e-7) else "no simultaneous nonpenetrating double contact", r, z)
        _, ulo = _min_gap(m, r, z, x, lower=True)
        _, uhi = _min_gap(m, r, z, x, lower=False)
        lo = _contact(m, r, x, ulo, lower=True)
        hi = _contact(m, r, x, uhi, lower=False)
    except (ValueError, FloatingPointError, OverflowError) as exc:
        return _invalid(x, f"geometry domain: {exc}", rguess, zguess)

    # Differentiated gap rows: [-lower_slope, +1], [+upper_slope, -1].
    # Absolute determinant = |lower_slope-upper_slope|. The scaling is
    # dimensionless because both radial and axial coordinates are metres.
    gap_jacobian = np.array([[-lo.slope, 1.0], [hi.slope, -1.0]])
    condition = float(np.linalg.cond(gap_jacobian))
    if not isfinite(condition) or condition >= max_condition:
        return _invalid(x, "singular / ill-conditioned contact kinematics", r, z)
    D = lo.slope - hi.slope
    rp = 1.0 / D
    zp = lo.slope * rp
    D_r = lo.slope_derivative - hi.slope_derivative
    rpp = -D_r * rp**3
    zpp = lo.slope * rpp + lo.slope_derivative * rp**2

    M = m.total_mass
    Mf = M * (rp**2 + zp**2)
    Mfp = 2 * M * (rp * rpp + zp * zpp)
    Jf = M * (r**2 + m.gyration_radius**2)
    Jfp = 2 * M * r * rp
    # F_mech and shaft reaction are evaluated from EXACTLY the same maps.
    Fi = 0.5 * Jfp * omega**2 - Mf * xddot - 0.5 * Mfp * xdot**2

    # Block FBD, including rotating-frame centrifugal term and relative inertia.
    # Tangential (Coriolis and shaft-alpha) reaction is carried by the guide.
    ar = rp * xddot + rpp * xdot**2 - r * omega**2
    az = zp * xddot + zpp * xdot**2
    nmat = np.column_stack([lo.normal, hi.normal])
    try:
        normals = np.linalg.solve(nmat, M * np.array([ar, az]))
    except np.linalg.LinAlgError:
        return _invalid(x, "singular normal-force resolution", r, z)
    Nlo, Nhi = map(float, normals)
    guide_tan = M * (2 * omega * rp * xdot + r * alpha)
    # Contact force moments about representative COM; total over all blocks.
    def arm_moment(c: Contact, force: float) -> float:
        return (c.u * c.normal[1] - (c.axial - z) * c.normal[0]) * force
    guide_moment = -(arm_moment(lo, Nlo) + arm_moment(hi, Nhi))
    F_contact = Nhi / sqrt(1.0 + hi.slope**2)
    issues: list[str] = []
    if r <= 0:
        issues.append("nonpositive shaft radius")
    if Nlo < -1e-7 or Nhi < -1e-7:
        issues.append("contact liftoff (negative normal reaction)")
    if not allow_end_contacts and ("end contact" in lo.mode or "end contact" in hi.mode):
        issues.append("sharp-end contact excluded by configuration")
    if abs(F_contact - Fi) > 2e-7 * (1 + abs(Fi)):
        issues.append("contact force / v4 interface mismatch")
    if Jfp**2 > 4 * Jf * Mf + 1e-10:
        issues.append("inertia inequality violated")
    return Point(x, r, z, rp, zp, rpp, zpp, Mf, Mfp, Jf, Jfp, Nlo, Nhi,
                 guide_tan, guide_moment, Fi, F_contact, lo, hi, tuple(issues))


def sweep(m: Mechanism, *, n: int = 81, **operating_point: float) -> list[Point]:
    points: list[Point] = []
    guess = (m.radius_ref, 0.0)
    for x in np.linspace(0, m.x_max, n):
        p = evaluate(m, float(x), guess=guess, **operating_point)
        points.append(p)
        if isfinite(p.radial) and isfinite(p.axial):
            guess = (p.radial, p.axial)
    return points


def from_mapping(spec: dict) -> Mechanism:
    """Load measured/synthetic profiles from a JSON-compatible object.

    If ``calibrate_at_zero`` is true, re-zero the rail offsets only for
    illustrative setups. Do NOT silently calibrate measured hardware.
    """
    keys = ("lower_track", "upper_track", "lower_face", "upper_face")
    data = {k: v for k, v in spec.items() if k != "calibrate_at_zero"}
    for key in keys:
        data[key] = Profile(**data[key])
    mechanism = Mechanism(**data)
    return calibrate_zero(mechanism) if spec.get("calibrate_at_zero", False) else mechanism
