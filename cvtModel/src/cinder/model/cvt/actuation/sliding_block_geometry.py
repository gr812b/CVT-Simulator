"""Canonical finite-profile geometry for fixed-orientation sliding weights.

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
from bisect import bisect_right
from decimal import Decimal, localcontext
from functools import lru_cache
from math import hypot, isfinite, sqrt
from typing import Literal

import numpy as np
from scipy.optimize import brentq, least_squares
from scipy.interpolate import make_interp_spline, PPoly
from numpy.polynomial import Polynomial

from cinder.model.cvt.closure import AffineClosureScalar
from .centrifugal_inertia import CentrifugalInertiaSample
from .forces.centrifugal_inertia import _closing_force
from .types import PulleyActuationContext


class SlidingBlockGeometryError(ValueError):
    """Machine-readable distinction between domain, model and numerical failures."""

    def __init__(
        self,
        message,
        *,
        code,
        category,
        axial_position=None,
        radial_interval=None,
        contact=None,
    ):
        super().__init__(message)
        self.code = code
        self.category = category
        self.axial_position = axial_position
        self.radial_interval = radial_interval
        self.contact = contact


@dataclass(frozen=True)
class Profile:
    """Finite C2 polynomial/spline or exact primitive graph z=f(r).

    For circle: z = offset + sign*(radius - sqrt(radius**2-(r-origin)**2)).
    All profiles have an explicit valid radial interval [left, right].
    """

    kind: Literal["line", "quadratic", "circle", "spline"]
    origin: float
    offset: float = 0.0
    slope: float = 0.0
    curvature: float = 0.0
    radius: float = 0.0
    circle_sign: int = 1
    left: float = -1.0
    right: float = 1.0
    knots: tuple[float, ...] = ()
    coefficients: tuple[tuple[float, ...], ...] = ()

    def __post_init__(self) -> None:
        if self.kind != "spline" and (self.knots or self.coefficients):
            raise ValueError("knots and coefficients belong only to spline profiles")
        for name in (
            "origin",
            "offset",
            "slope",
            "curvature",
            "radius",
            "left",
            "right",
        ):
            if not isfinite(getattr(self, name)):
                raise ValueError(f"profile {name} must be finite")
        if not self.left < self.right:
            raise ValueError("profile needs left < right")
        if (
            isinstance(self.circle_sign, bool)
            or not isinstance(self.circle_sign, int)
            or self.circle_sign not in (-1, 1)
        ):
            raise ValueError("profile circle_sign must be an integer +/-1")
        if self.kind == "circle":
            if self.radius <= 0:
                raise ValueError("circle needs positive radius")
            if (
                max(abs(self.left - self.origin), abs(self.right - self.origin))
                >= self.radius
            ):
                raise ValueError("circular profile domain exceeds open semicircle")
        elif self.kind == "spline":
            knots = tuple(float(v) for v in self.knots)
            coefficients = tuple(
                tuple(float(v) for v in row) for row in self.coefficients
            )
            if (
                len(knots) < 2
                or len(coefficients) != len(knots) - 1
                or any(not isfinite(v) for v in knots)
                or any(a >= b for a, b in zip(knots, knots[1:]))
                or any(
                    not row or not all(isfinite(v) for v in row) for row in coefficients
                )
            ):
                raise ValueError(
                    "spline needs ordered finite knots and one finite coefficient row per interval"
                )
            if (self.left, self.right) != (knots[0], knots[-1]):
                raise ValueError("spline domain must equal its first and last knots")
            object.__setattr__(self, "knots", knots)
            object.__setattr__(self, "coefficients", coefficients)
            # Motion acceleration needs C2 contact profiles. The third derivative
            # used only for contact-path interpolation may have a one-sided jump.
            for i in range(1, len(knots) - 1):
                for order in range(3):
                    a = (
                        Polynomial(coefficients[i - 1]).deriv(order)(1)
                        / (knots[i] - knots[i - 1]) ** order
                    )
                    b = (
                        Polynomial(coefficients[i]).deriv(order)(0)
                        / (knots[i + 1] - knots[i]) ** order
                    )
                    scale = max(abs(a), abs(b), 1e-3 if order == 0 else 1.0)
                    if abs(a - b) > 2e-9 * scale:
                        raise ValueError(
                            f"spline seam {i} is not C2 (derivative {order})"
                        )
        elif self.kind not in ("line", "quadratic"):
            raise ValueError(f"unknown profile: {self.kind}")

    @classmethod
    def from_points(cls, points, *, degree=3):
        """Interpolate ordered (radial, axial) SI points, without smoothing.

        Cubic (C2) interpolation is the default; degree=5 selects C4 quintics.
        Too few points define one lower-degree global polynomial.
        Measured noise is retained; callers must
        fit noisy measurements explicitly before using them as ideal contacts.
        """
        points = np.asarray(points, dtype=float)
        if (
            points.ndim != 2
            or points.shape[1] != 2
            or len(points) < 2
            or not np.all(np.isfinite(points))
            or np.any(np.diff(points[:, 0]) <= 0)
        ):
            raise ValueError(
                "profile points need finite, strictly increasing radial coordinates"
            )
        if degree not in (3, 5):
            raise ValueError(
                "point interpolation degree must be 3 or 5; explicit polynomial segments admit other degrees"
            )
        r, z = points.T
        if len(r) <= degree + 1:
            t = (r - r[0]) / (r[-1] - r[0])
            coefficients = (
                tuple(Polynomial.fit(t, z, len(r) - 1, domain=[0, 1]).convert().coef),
            )
            knots = (r[0], r[-1])
        else:
            pp = PPoly.from_spline(make_interp_spline(r, z, k=degree))
            knots, coefficients = [r[0]], []
            for i, (a, b) in enumerate(zip(pp.x, pp.x[1:])):
                if a < b and a >= r[0] and b <= r[-1]:
                    coefficients.append(
                        tuple(pp.c[::-1, i] * (b - a) ** np.arange(len(pp.c)))
                    )
                    knots.append(b)
        return cls(
            "spline",
            0.0,
            left=float(r[0]),
            right=float(r[-1]),
            knots=tuple(knots),
            coefficients=tuple(coefficients),
        )

    def polynomial(self, coordinate, a, b):
        """Polynomial in t=(r-a)/(b-a) on one seam-free interval, or None for arcs."""
        if self.kind == "circle":
            return None
        variable = Polynomial([a, b - a])
        if self.kind == "spline":
            i = min(
                max(bisect_right(self.knots, coordinate) - 1, 0),
                len(self.coefficients) - 1,
            )
            return (
                Polynomial(self.coefficients[i])(
                    (variable - self.knots[i]) / (self.knots[i + 1] - self.knots[i])
                )
                + self.offset
            )
        d = variable - self.origin
        return (
            Polynomial([self.offset])
            + self.slope * d
            + (0.5 * self.curvature * d * d if self.kind == "quadratic" else 0)
        )

    def derivative(self, r, order):
        if self.kind == "spline":
            i = min(max(bisect_right(self.knots, r) - 1, 0), len(self.coefficients) - 1)
            width = self.knots[i + 1] - self.knots[i]
            return float(
                Polynomial(self.coefficients[i]).deriv(order)(
                    (r - self.knots[i]) / width
                )
                / width**order
                + (self.offset if order == 0 else 0)
            )
        if order == 3:
            if self.kind != "circle":
                return 0.0
            d = r - self.origin
            return (
                3
                * self.circle_sign
                * self.radius**2
                * d
                / (self.radius**2 - d * d) ** 2.5
            )
        return (self.value, self.gradient, self.second)[order](r)

    def bounds(self, a, b, order=0):
        """Extrema from polynomial stationary roots, or analytic circular extrema."""
        if a == b:
            value = self.derivative(a, order)
            padding = 64 * np.finfo(float).eps * max(abs(value), np.finfo(float).tiny)
            return value - padding, value + padding
        cuts = sorted({a, b, *(v for v in self.knots if a < v < b)})
        values = []
        for left, right in zip(cuts, cuts[1:]):
            poly = self.polynomial((left + right) / 2, left, right)
            if poly is not None:
                poly = poly.deriv(order) / (right - left) ** order
                candidates = [0.0, 1.0, *_real_roots(poly.deriv(), 0, 1)]
                values.extend(float(poly(t)) for t in candidates)
            else:
                candidates = [left, right]
                if left < self.origin < right:
                    candidates.append(self.origin)
                values.extend(self.derivative(v, order) for v in candidates)
        padding = (
            64
            * np.finfo(float).eps
            * max(max(abs(v) for v in values), np.finfo(float).tiny)
        )
        return min(values) - padding, max(values) + padding

    def value(self, r: float) -> float:
        if self.kind == "spline":
            return self.derivative(r, 0)
        d = r - self.origin
        if self.kind == "circle":
            return self.offset + self.circle_sign * (
                self.radius - sqrt(self.radius**2 - d**2)
            )
        return (
            self.offset
            + self.slope * d
            + (0.5 * self.curvature * d**2 if self.kind == "quadratic" else 0)
        )

    def gradient(self, r: float) -> float:
        if self.kind == "spline":
            return self.derivative(r, 1)
        d = r - self.origin
        if self.kind == "circle":
            return self.circle_sign * d / sqrt(self.radius**2 - d**2)
        return self.slope + (self.curvature * d if self.kind == "quadratic" else 0)

    def second(self, r: float) -> float:
        if self.kind == "spline":
            return self.derivative(r, 2)
        d = r - self.origin
        if self.kind == "circle":
            return self.circle_sign * self.radius**2 / (self.radius**2 - d**2) ** 1.5
        return self.curvature if self.kind == "quadratic" else 0.0


@dataclass(frozen=True)
class Mechanism:
    lower_track: Profile  # stationary track: lower contact
    upper_track: Profile  # moves by +x in axial z
    lower_face: Profile  # block face in body-datum radial coordinate u
    upper_face: Profile
    total_mass: float
    gyration_radius: float  # centroidal shaft-axis inertia per total mass: J_C=M*k^2
    display_count: int = 1  # display/part measurement only; NEVER multiplies inertia
    radius_ref: float = 0.054
    x_max: float = 0.014
    name: str = "sliding weight"
    com_offset: tuple[float, float] = (0.0, 0.0)  # radial, axial from body datum
    x_min: float = 0.0

    def __post_init__(self) -> None:
        for name in ("total_mass", "gyration_radius", "radius_ref", "x_min", "x_max"):
            if not isfinite(getattr(self, name)):
                raise ValueError(f"mechanism {name} must be finite")
        if isinstance(self.display_count, bool) or not isinstance(
            self.display_count, int
        ):
            raise ValueError("display_count must be a positive integer")
        if self.total_mass <= 0 or self.gyration_radius < 0:
            raise ValueError("mass must be >0 and gyration radius nonnegative")
        if self.display_count < 1 or self.radius_ref <= 0:
            raise ValueError("count and reference radius must be positive")
        if self.x_min >= self.x_max:
            raise ValueError("axial travel interval must be ordered")
        if (self.lower_face.left, self.lower_face.right) != (
            self.upper_face.left,
            self.upper_face.right,
        ):
            raise ValueError("demo expects same radial interval for both block faces")
        if len(self.com_offset) != 2 or not all(isfinite(v) for v in self.com_offset):
            raise ValueError("COM offset needs finite radial and axial components")
        a, b = self.lower_face.left, self.lower_face.right
        value, _ = _profile_gap_minimum(self.upper_face, self.lower_face, 0.0, a, b)
        if value <= 0:
            raise ValueError("block faces intersect: upper must stay above lower")


@dataclass(frozen=True)
class Contact:
    u: float  # local radial coordinate on weight
    radial: float  # contact radial coordinate relative to shaft
    axial: float  # world contact axial coordinate
    slope: float  # slope of the contacted TRACK
    slope_derivative: float  # d(track slope)/d(block COM radial shift)
    normal: tuple[float, float]  # normal on weight (radial, axial)
    mode: str  # interior tangent / end contact / conformal
    u_intervals: tuple[tuple[float, float], ...] = ()


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
    N_lower: float  # total normal reaction, across all weights
    N_upper: float
    guide_tangential: float  # magnitude/sign of needed tangential guide reaction
    guide_rocking_moment: (
        float | None  # contact-only moment; None when pressure location is unknown
    )
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


def _real_roots(poly, a, b):
    """Isolate polynomial roots recursively between derivative roots.

    Coordinates are normalized per piece to avoid SI high-power conditioning.
    Repeated roots are retained by testing all derivative stationary points.
    """
    scale = float(np.max(np.abs(poly.coef)))
    if scale == 0:
        return []
    poly = Polynomial(poly.coef / scale).trim(1e-14)
    if poly.degree() == 0:
        return []
    if poly.degree() == 1:
        root = -poly.coef[0] / poly.coef[1]
        return [float(root)] if a < root < b else []
    critical = _real_roots(poly.deriv(), a, b)
    cuts = [a, *critical, b]
    roots = [v for v in critical if abs(poly(v)) <= 2e-12]
    for left, right in zip(cuts, cuts[1:]):
        if poly(left) * poly(right) < 0:
            roots.append(brentq(poly, left, right, xtol=1e-14))
    return sorted(set(roots))


def curvature_bounds(profile: Profile, a: float, b: float) -> tuple[float, float]:
    return profile.bounds(a, b, 2)


@lru_cache(maxsize=8192)
def _gap_minima(top, bottom, shift, a, b):
    """Global finite-face minimum, including all stationary points and flat spans.

    Polynomial pieces are solved in normalized coordinates. Arc/polynomial
    stationarity is squared to a polynomial; candidates are checked against
    the unsquared equation so extraneous roots never become contacts.
    """
    cuts = sorted(
        {
            a,
            b,
            *(v for v in top.knots if a < v < b),
            *(v - shift for v in bottom.knots if a < v - shift < b),
        }
    )
    candidates = [(top.value(u) - bottom.value(u + shift), (u, u)) for u in cuts]
    for left, right in zip(cuts, cuts[1:]):
        width = right - left
        p = top.polynomial((left + right) / 2, left, right)
        q = bottom.polynomial((left + right) / 2 + shift, left + shift, right + shift)
        if p is not None and q is not None:
            gap = p - q
            derivative = gap.deriv()
            cancellation_scale = max(
                np.max(np.abs(p.coef)), np.max(np.abs(q.coef)), np.finfo(float).tiny
            )
            if (
                max(abs(v) for v in derivative.coef)
                <= 64 * np.finfo(float).eps * cancellation_scale
            ):
                candidates.append((float(gap(0.5)), (left, right)))
                continue
            roots = _real_roots(derivative, 0, 1)
        elif p is None and q is None:
            # d1/sqrt(R1^2-d1^2) = sign_ratio*d2/sqrt(R2^2-d2^2)
            d1 = Polynomial([left - top.origin, width])
            d2 = Polynomial([left + shift - bottom.origin, width])
            equation = d1 * d1 * bottom.radius**2 - d2 * d2 * top.radius**2
            if np.max(np.abs(equation.coef)) < 1e-28:
                if (
                    top.radius == bottom.radius
                    and top.circle_sign == bottom.circle_sign
                    and top.origin == bottom.origin - shift
                ):
                    candidates.append(
                        (
                            top.value((left + right) / 2)
                            - bottom.value((left + right) / 2 + shift),
                            (left, right),
                        )
                    )
                roots = [v for d in (d1, d2) for v in _real_roots(d, 0, 1)]
            else:
                roots = _real_roots(equation, 0, 1)
        else:
            arc = top if p is None else bottom
            start = left if p is None else left + shift
            d = Polynomial([start - arc.origin, width])
            slope = (q if p is None else p).deriv() / width
            equation = slope * slope * (arc.radius**2 - d * d) - d * d
            roots = _real_roots(equation, 0, 1)
        for t in roots:
            u = left + width * t
            if abs(top.gradient(u) - bottom.gradient(u + shift)) <= 2e-8 * max(
                1.0, abs(top.gradient(u)), abs(bottom.gradient(u + shift))
            ):
                candidates.append((top.value(u) - bottom.value(u + shift), (u, u)))
    minimum = min(value for value, _ in candidates)
    scale = max(
        abs(top.value(a)),
        abs(top.value(b)),
        abs(bottom.value(a + shift)),
        abs(bottom.value(b + shift)),
        abs(minimum),
        1e-3,
    )
    tolerance = 128 * np.finfo(float).eps * scale
    spans = sorted(span for value, span in candidates if value <= minimum + tolerance)
    merged = []
    for left, right in spans:
        if merged and left <= merged[-1][1] + 2e-13:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    return minimum, tuple(merged)


def _profile_gap_minimum(top, bottom, shift, a, b):
    value, spans = _gap_minima(top, bottom, shift, a, b)
    return value, (spans[0][0] + spans[0][1]) / 2


def _min_gap(
    m: Mechanism, radial: float, axial: float, x: float, *, lower: bool
) -> tuple[float, float]:
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    a, b = face.left, face.right
    if radial + a < track.left - 1e-11 or radial + b > track.right + 1e-11:
        raise ValueError("block footprint extends outside modelled track domain")

    if lower:
        gap, u = _profile_gap_minimum(face, track, radial, a, b)
        return gap + axial, u
    gap, R = _profile_gap_minimum(track, face, -radial, a + radial, b + radial)
    # Preserve exact material endpoints after a translated-coordinate query.
    # Subtraction roundoff otherwise creates a second near-identical vertex in
    # the sectional solid without changing the physical contact.
    u = a if R == a + radial else b if R == b + radial else R - radial
    return gap + x - axial, u


def _contact_minima(m, radial, *, lower):
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    if lower:
        spans = _gap_minima(face, track, radial, face.left, face.right)[1]
    else:
        _, spans = _gap_minima(
            track, face, -radial, radial + face.left, radial + face.right
        )
    tolerance = (
        32
        * np.finfo(float).eps
        * max(abs(radial), abs(face.left), abs(face.right), 1e-3)
    )

    def local(v):
        u = v - radial
        if abs(u - face.left) <= tolerance:
            return face.left
        if abs(u - face.right) <= tolerance:
            return face.right
        return u

    if not lower:
        spans = tuple((local(a), local(b)) for a, b in spans)
    slopes = [track.gradient(radial + (a + b) / 2) for a, b in spans]
    if (
        len(spans) > 1
        and all(a == b for a, b in spans)
        and (max(slopes) - min(slopes) > 2e-10 * max(1.0, *(abs(v) for v in slopes)))
    ):
        # Close unequal minima can fall inside the double-precision gap tie
        # tolerance, especially near a smooth cubic envelope switch. Re-evaluate
        # their values at higher precision before inventing multiple normals.
        with localcontext() as context:
            context.prec = 60
            values = []
            for a, _ in spans:
                u = Decimal.from_float(float(a))
                R = Decimal.from_float(float(radial)) + u
                gap = _decimal_profile(face, u) - _decimal_profile(track, R)
                values.append(gap if lower else -gap)
            minimum = min(values)
            tolerance = Decimal("1e-24") * max(
                Decimal("0.001"), *(abs(v) for v in values)
            )
            spans = tuple(
                span
                for span, value in zip(spans, values)
                if value - minimum <= tolerance
            )
    return spans


def _decimal_profile(p, r):
    """Evaluate the supplied float geometry, without subtraction roundoff."""

    def d(v):
        return Decimal.from_float(float(v))

    if p.kind == "spline":
        i = min(max(bisect_right(p.knots, float(r)) - 1, 0), len(p.coefficients) - 1)
        t = (r - d(p.knots[i])) / (d(p.knots[i + 1]) - d(p.knots[i]))
        value = Decimal(0)
        for c in reversed(p.coefficients[i]):
            value = value * t + d(c)
        return value + d(p.offset)
    dr = r - d(p.origin)
    if p.kind == "circle":
        return d(p.offset) + p.circle_sign * (
            d(p.radius) - (d(p.radius) ** 2 - dr**2).sqrt()
        )
    return (
        d(p.offset)
        + d(p.slope) * dr
        + (d(p.curvature) * dr**2 / 2 if p.kind == "quadratic" else 0)
    )


def _decimal_polynomial(p, left, right, shift):
    """Polynomial for p(left + (right-left)*t + shift), in current precision."""

    def d(v):
        return Decimal.from_float(float(v))

    a, width = d(left) + d(shift), d(right) - d(left)
    if p.kind == "spline":
        i = min(
            max(bisect_right(p.knots, (left + right) / 2 + shift) - 1, 0),
            len(p.coefficients) - 1,
        )
        h = d(p.knots[i + 1]) - d(p.knots[i])
        a, width = (a - d(p.knots[i])) / h, width / h
        coefficients = list(map(d, p.coefficients[i]))
    else:
        a -= d(p.origin)
        coefficients = [d(p.offset), d(p.slope)]
        if p.kind == "quadratic":
            coefficients.append(d(p.curvature) / 2)
    result = [Decimal(0)]
    for value in reversed(coefficients):
        out = [Decimal(0)] * (len(result) + 1)
        for i, c in enumerate(result):
            out[i] += a * c
            out[i + 1] += width * c
        out[0] += value
        result = out
    if p.kind == "spline":
        result[0] += d(p.offset)
    while len(result) > 1 and result[-1] == 0:
        result.pop()
    return result


def _decimal_roots(coefficients):
    """Derivative-isolated roots in (0,1), for the high-precision endpoint check."""
    c = list(coefficients)
    while len(c) > 1 and c[-1] == 0:
        c.pop()
    if len(c) < 2:
        return []
    if len(c) == 2:
        root = -c[0] / c[1]
        return [root] if 0 < root < 1 else []

    def value(x):
        y = Decimal(0)
        for coefficient in reversed(c):
            y = y * x + coefficient
        return y

    critical = _decimal_roots([i * v for i, v in enumerate(c)][1:])
    tolerance = max(map(abs, c)) * Decimal("1e-55")
    roots = [x for x in critical if abs(value(x)) <= tolerance]
    cuts = [Decimal(0), *critical, Decimal(1)]
    for a, b in zip(cuts, cuts[1:]):
        va, vb = value(a), value(b)
        if abs(va) <= tolerance or abs(vb) <= tolerance or va * vb >= 0:
            continue
        for _ in range(190):
            middle = (a + b) / 2
            vm = value(middle)
            if va * vm <= 0:
                b = middle
            else:
                a, va = middle, vm
        roots.append((a + b) / 2)
    return sorted(roots)


def calibrate_zero(m: Mechanism) -> Mechanism:
    """Choose the two track axial offsets so both contacts close at (r_ref, z=0, x=0)."""
    lo_gap, _ = _min_gap(m, m.radius_ref, 0.0, 0.0, lower=True)
    lo = replace(m.lower_track, offset=m.lower_track.offset + lo_gap)
    intermediate = replace(m, lower_track=lo)
    hi_gap, _ = _min_gap(intermediate, m.radius_ref, 0.0, 0.0, lower=False)
    hi = replace(m.upper_track, offset=m.upper_track.offset - hi_gap)
    return replace(intermediate, upper_track=hi)


def _contact(
    m: Mechanism, radial: float, x: float, u: float, *, lower: bool, intervals=()
) -> Contact:
    face = m.lower_face if lower else m.upper_face
    track = m.lower_track if lower else m.upper_track
    R = radial + u
    slope = track.gradient(R)
    fc = track.second(R)
    bc = face.second(u)
    endpoint = u == face.left or u == face.right
    # The envelope theorem gives the gap gradient, even if u moves.
    # For an interior tangent: face'' * du/dr = track''*(1+du/dr).
    curvature_scale = max(abs(bc), abs(fc), np.finfo(float).tiny)
    if not endpoint and abs(bc - fc) > 128 * np.finfo(float).eps * curvature_scale:
        du_dr = fc / (bc - fc)
        mode = "interior tangent"
    elif not endpoint and fc == 0:
        du_dr = 0.0
        mode = "interior tangent"
    elif not endpoint:
        raise SlidingBlockGeometryError(
            "Contact migration is degenerate; this derivative construction cannot establish the body envelope",
            code="contact_derivative_unresolved",
            category="numerical",
            axial_position=x,
            contact="lower" if lower else "upper",
        )
    else:
        du_dr = 0.0
        mode = "end contact (ideal point)"
    if intervals and (len(intervals) > 1 or intervals[0][1] - intervals[0][0] > 2e-13):
        slopes, second = [], []
        for a, b in intervals:
            if b - a > 2e-13:
                slopes.extend(track.bounds(radial + a, radial + b, 1))
                second.append(0.0)
            else:
                slopes.append(track.gradient(radial + a))
                f2, b2 = track.second(radial + a), face.second(a)
                if a in (face.left, face.right):
                    second.append(f2)
                elif f2 == 0:
                    second.append(0.0)
                elif abs(b2 - f2) <= 128 * np.finfo(float).eps * max(abs(b2), abs(f2)):
                    raise SlidingBlockGeometryError(
                        "A contact candidate has unresolved degenerate migration",
                        code="contact_derivative_unresolved",
                        category="numerical",
                        axial_position=x,
                        contact="lower" if lower else "upper",
                    )
                else:
                    second.append(f2 * b2 / (b2 - f2))
        if max(slopes) - min(slopes) > 2e-10 * max(1.0, max(abs(v) for v in slopes)):
            raise SlidingBlockGeometryError(
                "Contact set has different envelope slopes; nonsmooth motion requires an event model",
                code="nonsmooth_contact_transition",
                category="model",
                axial_position=x,
                contact="lower" if lower else "upper",
            )
        # When candidates share their value and first derivative, the maximum
        # lower support selects the greatest curvature; the minimum upper
        # support selects the least. A candidate touching only at this pose
        # need not have the active envelope's curvature on either side.
        envelope_second = (max if lower else min)(second)
        du_dr = fc / (bc - fc) if bc != fc else 0.0
        mode = (
            "conformal (undetermined contact distribution)"
            if any(b - a > 2e-13 for a, b in intervals)
            else "multiple points (undetermined contact distribution)"
        )
    slope_derivative = fc * (1 + du_dr)
    if intervals and (len(intervals) > 1 or intervals[0][1] - intervals[0][0] > 2e-13):
        slope_derivative = envelope_second
    if lower:
        nr, nz = -slope, 1.0
        world_axial = track.value(R)
    else:
        nr, nz = slope, -1.0
        world_axial = track.value(R) + x
    length = hypot(nr, nz)
    return Contact(
        u,
        R,
        world_axial,
        slope,
        slope_derivative,
        (nr / length, nz / length),
        mode,
        tuple(intervals),
    )


def _invalid(
    x: float, reason: str, radial: float = float("nan"), axial: float = float("nan")
) -> Point:
    n = float("nan")
    return Point(x, radial, axial, *(n,) * 14, None, None, (reason,))


def evaluate(
    m: Mechanism,
    x: float,
    *,
    omega: float = 350.0,
    alpha: float = 0.0,
    xdot: float = 0.0,
    xddot: float = 0.0,
    guess: tuple[float, float] | None = None,
    max_condition: float = 1e3,
    allow_end_contacts: bool = True,
) -> Point:
    """Solve both active gaps then check geometry, compressive normals and v4 maps.

    Reacted loads depend on the *assumed operating accelerations*. This does NOT
    solve CINDER's coupled shift acceleration. It probes whether its assumed
    two-contact branch could remain closed at this instantaneous state.
    """
    if not all(isfinite(v) for v in (omega, alpha, xdot, xddot)):
        return _invalid(x, "non-finite operating state")
    if not isfinite(max_condition) or max_condition <= 1:
        raise ValueError("max_condition must be finite and greater than one")
    if not (m.x_min <= x <= m.x_max):
        return _invalid(x, "travel outside configured range")
    face = m.lower_face
    radius_min = max(m.lower_track.left, m.upper_track.left) - face.left
    radius_max = min(m.lower_track.right, m.upper_track.right) - face.right
    radius_min = max(radius_min, 0.0)
    if radius_min >= radius_max:
        return _invalid(x, "no shared track footprint")
    rguess, zguess = guess if guess is not None else (m.radius_ref + x * 0.4, 0.4 * x)
    rguess = float(
        np.clip(
            rguess,
            np.nextafter(radius_min, radius_max),
            np.nextafter(radius_max, radius_min),
        )
    )

    def residual(y: np.ndarray) -> tuple[float, float]:
        r, z = float(y[0]), float(y[1])
        l, _ = _min_gap(m, r, z, x, lower=True)
        h, _ = _min_gap(m, r, z, x, lower=False)
        return l, h

    try:
        opt = least_squares(
            residual,
            (rguess, zguess),
            bounds=((radius_min, -np.inf), (radius_max, np.inf)),
            xtol=1e-13,
            ftol=1e-13,
            gtol=1e-13,
            max_nfev=120,
        )
        r, z = map(float, opt.x)
        if max(abs(a) for a in opt.fun) > 2.0e-8:
            return _invalid(
                x,
                (
                    "track limit / no compatible double contact"
                    if (abs(r - radius_min) < 1e-7 or abs(r - radius_max) < 1e-7)
                    else "no simultaneous nonpenetrating double contact"
                ),
                r,
                z,
            )
        _, ulo = _min_gap(m, r, z, x, lower=True)
        _, uhi = _min_gap(m, r, z, x, lower=False)
        lo = _contact(
            m, r, x, ulo, lower=True, intervals=_contact_minima(m, r, lower=True)
        )
        hi = _contact(
            m, r, x, uhi, lower=False, intervals=_contact_minima(m, r, lower=False)
        )
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

    r += m.com_offset[0]
    z += m.com_offset[1]
    M = m.total_mass
    Mf = M * (rp**2 + zp**2)
    Mfp = 2 * M * (rp * rpp + zp * zpp)
    Jf = M * (r**2 + m.gyration_radius**2)
    Jfp = 2 * M * r * rp
    # F_mech and shaft reaction are evaluated from EXACTLY the same maps.
    Fi = _closing_force(
        PulleyActuationContext(
            time=0.0,
            axial_position=x,
            axial_speed=xdot,
            shaft_speed=omega,
            axial_acceleration=AffineClosureScalar.constant(xddot),
        ),
        CentrifugalInertiaSample(Mf, Mfp, Jf, Jfp),
    ).bias

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

    # Contact-only moment about the representative COM, positive in the (r,z)
    # plane. Divide by count for one block. This is not a global vector sum
    # around the pulley. A full guide-wrench calculation also needs I_C:
    # I_C*alpha_vec + omega_vec x (I_C*omega_vec). Gyration radius alone cannot
    # supply its transverse components, e.g. a centrifugal product-inertia
    # couple. The reported value assumes zero required inertial rocking moment.
    def arm_moment(c: Contact, force: float) -> float:
        return ((c.radial - r) * c.normal[1] - (c.axial - z) * c.normal[0]) * force

    guide_moment = -(arm_moment(lo, Nlo) + arm_moment(hi, Nhi))
    if any(
        len(c.u_intervals) > 1 or any(b - a > 2e-13 for a, b in c.u_intervals)
        for c in (lo, hi)
    ):
        guide_moment = None
    F_contact = Nhi / sqrt(1.0 + hi.slope**2)
    issues: list[str] = []
    if r <= 0:
        issues.append("nonpositive shaft radius")
    if Nlo < -1e-7 or Nhi < -1e-7:
        issues.append("contact liftoff (negative normal reaction)")
    if not allow_end_contacts and (
        "end contact" in lo.mode or "end contact" in hi.mode
    ):
        issues.append("sharp-end contact excluded by configuration")
    if abs(F_contact - Fi) > 2e-7 * (1 + abs(Fi)):
        issues.append("contact force / v4 interface mismatch")
    if Jfp**2 > 4 * Jf * Mf + 1e-10:
        issues.append("inertia inequality violated")
    return Point(
        x,
        r,
        z,
        rp,
        zp,
        rpp,
        zpp,
        Mf,
        Mfp,
        Jf,
        Jfp,
        Nlo,
        Nhi,
        guide_tan,
        guide_moment,
        Fi,
        F_contact,
        lo,
        hi,
        tuple(issues),
    )


def sweep(m: Mechanism, *, n: int = 81, **operating_point: float) -> list[Point]:
    points: list[Point] = []
    guess = (m.radius_ref, 0.0)
    for x in np.linspace(m.x_min, m.x_max, n):
        p = evaluate(m, float(x), guess=guess, **operating_point)
        points.append(p)
        if isfinite(p.radial) and isfinite(p.axial):
            guess = (p.radial - m.com_offset[0], p.axial - m.com_offset[1])
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
    return (
        calibrate_zero(mechanism) if spec.get("calibrate_at_zero", False) else mechanism
    )
