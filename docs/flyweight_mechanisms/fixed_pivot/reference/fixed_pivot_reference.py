"""Reference construction accompanying CINDER Clamping Implementations, Part I.

This module has no CINDER imports. It constructs the finite-roller mechanism
and returns M, dM/dx, J, dJ/dx. Its exact solver is deliberately restricted to
the forward-arm, monotone contact branch described in the document; it is not
a replacement for CINDER's general branch/interference audit.

Units: metres, kilograms, seconds, radians. The included profile is the
pinned v1.1.5 reference fixture, not a newly measured hardware profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan, atan2, cos, isfinite, radians, sin, sqrt, tan
from typing import Callable

import numpy as np
from scipy.interpolate import BPoly, CubicSpline
from scipy.optimize import brentq


@dataclass(frozen=True)
class InertiaSample:
    M: float
    M_prime: float
    J: float
    J_prime: float

    def __post_init__(self):
        if not all(isfinite(v) for v in self.values()):
            raise ValueError("All four inertia quantities must be finite.")
        if self.M < 0 or self.J < 0:
            raise ValueError("Inertia contributions must be nonnegative.")

    def values(self):
        return (self.M, self.M_prime, self.J, self.J_prime)


@dataclass(frozen=True)
class MassMoments:
    """One flyweight's moments; n identical, reflection-symmetric members."""
    n: int
    m: float
    Mu: float
    Mv: float
    Su: float
    Sv: float
    Suv: float = 0.
    Sz: float = 0.

    @property
    def I(self):
        return self.n * (self.Su + self.Sv)

    @classmethod
    def slender_arm_and_tip(cls, n, L, arm_mass, tip_mass):
        return cls(n, arm_mass+tip_mass,
                   arm_mass*L/2 + tip_mass*L, 0.,
                   arm_mass*L*L/3 + tip_mass*L*L, 0.)

    def inertias(self, rP, q, q_prime, q_second):
        s, c = sin(q), cos(q)
        J = self.n * (self.m*rP*rP + 2*rP*(self.Mu*s+self.Mv*c)
                      + self.Su*s*s + self.Sv*c*c + 2*self.Suv*s*c + self.Sz)
        Jq = self.n * (2*rP*(self.Mu*c-self.Mv*s)
                       + 2*(self.Su-self.Sv)*s*c + 2*self.Suv*(c*c-s*s))
        return InertiaSample(self.I*q_prime*q_prime,
                             2*self.I*q_prime*q_second, J, Jq*q_prime)


class StraightRamp:
    def __init__(self, angle_degrees=35., length=.038):
        self.k = tan(radians(angle_degrees))
        self.length = length
        self.joins = ()

    def evaluate(self, xi):
        if not 0 <= xi <= self.length:
            raise ValueError("Ramp coordinate outside its domain.")
        return self.k*xi, self.k, 0., 0.


class ReferenceRamp:
    """35 deg / 5 mm; C3 / 3 mm; circular 35 to 20 deg / 30 mm.

    The slope of the blend is a quintic Hermite polynomial in Bernstein form.
    Its integral is the sixth-degree height profile. This independently
    constructs the same polynomial as the production power-basis routine.
    """
    linear_length = .005
    blend_length = .003
    circular_length = .030
    length = .038
    joins = (.005, .008)

    def __init__(self):
        self.alpha0, self.alpha1 = radians(35), radians(20)
        self.k = tan(self.alpha0)
        self.radius = self.circular_length/(sin(self.alpha0)-sin(self.alpha1))
        _, p, p1, p2 = self.circular(0.)
        self.slope = BPoly.from_derivatives(
            [0., self.blend_length], [[self.k, 0., 0.], [p, p1, p2]])
        self.slope_d1 = self.slope.derivative(1)
        self.slope_d2 = self.slope.derivative(2)
        self.integral = self.slope.antiderivative()
        self.blend_height = float(self.integral(self.blend_length)-self.integral(0.))

    def circular(self, t):
        u = sin(self.alpha0)-t/self.radius
        w = sqrt(1-u*u)
        return (self.radius*(w-cos(self.alpha0)), u/w,
                -1/(self.radius*w**3), 3*u/(self.radius**2*w**5))

    def evaluate(self, xi):
        if not 0 <= xi <= self.length:
            raise ValueError("Ramp coordinate outside its domain.")
        l, b = self.linear_length, self.blend_length
        if xi <= l:
            return self.k*xi, self.k, 0., 0.
        if xi <= l+b:
            t = xi-l
            return (self.k*l + float(self.integral(t)-self.integral(0.)),
                    float(self.slope(t)), float(self.slope_d1(t)), float(self.slope_d2(t)))
        h, p, p1, p2 = self.circular(xi-l-b)
        return self.k*l+self.blend_height+h, p, p1, p2


@dataclass(frozen=True)
class Geometry:
    XP: float = 0.
    rP: float = .042545
    L: float = .0315214
    R: float = .0065
    XA: float = .0381
    rA: float = .04959604
    direction: int = -1
    side: int = 1
    x_min: float = 0.
    x_max: float = .01905


@dataclass(frozen=True)
class Contact:
    x: float
    xi: float
    q: float
    q_prime: float
    q_second: float
    a: float
    b: float
    normal_x: float
    normal_r: float
    offset_factor: float
    g_xi: float
    arm_residual: float


class FixedPivotReference:
    def __init__(self, ramp=None, geometry=None, mass=None):
        self.ramp = ramp if ramp is not None else ReferenceRamp()
        self.geometry = geometry if geometry is not None else Geometry()
        self.mass = mass if mass is not None else MassMoments.slender_arm_and_tip(
            3, self.geometry.L, .013646, .250)
        # These diagnostics are a numerical check of the reference branch.
        # They are not a proof of global noninterference for arbitrary ramps.
        grid = sorted(set(np.linspace(0, self.ramp.length, 401)) | set(self.ramp.joins))
        mapped = np.array([self.closure_from_contact(xi) for xi in grid])
        if np.any(np.diff(mapped) <= 0):
            raise ValueError("Reference solver requires a monotone forward-arm branch.")
        if not mapped[0] <= self.geometry.x_min < self.geometry.x_max <= mapped[-1]:
            raise ValueError("Reference branch does not cover the requested closure interval.")

    def offset(self, xi):
        """Centre curve at zero closure, its xi derivatives, and its normal."""
        h, p, k, t = self.ramp.evaluate(xi)
        g = self.geometry
        w = sqrt(1+p*p)
        normal = g.side*np.array([-p, g.direction])/w
        normal_d1 = -g.side*k*np.array([1., g.direction*p])/w**3
        normal_d2 = -g.side*np.array([
            t/w**3-3*p*k*k/w**5,
            g.direction*((k*k+p*t)/w**3-3*p*p*k*k/w**5)])
        c0 = np.array([g.XA+g.direction*xi, g.rA+h])+g.R*normal
        d1 = np.array([g.direction, p])+g.R*normal_d1
        d2 = np.array([0., k])+g.R*normal_d2
        regular = 1-g.R*g.side*g.direction*k/w**3
        return c0, d1, d2, normal, regular

    def closure_from_contact(self, xi):
        c0, _, _, _, regular = self.offset(xi)
        g = self.geometry
        b = c0[1]-g.rP
        if abs(b) >= g.L or regular <= 0:
            raise ValueError("Outside the reference forward-arm regular branch.")
        a = sqrt(g.L*g.L-b*b)
        return g.XP+a-c0[0]

    def contact(self, x):
        g = self.geometry
        if not g.x_min <= x <= g.x_max:
            raise ValueError("Closure outside the declared interval.")
        xi = brentq(lambda xi: self.closure_from_contact(xi)-x,
                    0., self.ramp.length, xtol=2e-15, rtol=8*np.finfo(float).eps)
        c0, d1, d2, n, regular = self.offset(xi)
        a, b = c0[0]+x-g.XP, c0[1]-g.rP
        D = a*d1[0]+b*d1[1]
        if abs(D) < 1e-12:
            raise ValueError("Contact branch is singular.")
        xi1 = -a/D
        xi2 = -(1+2*d1[0]*xi1+(d1@d1+np.array([a,b])@d2)*xi1*xi1)/D
        c1 = np.array([1.,0.])+d1*xi1
        c2 = d2*xi1*xi1+d1*xi2
        q1 = (a*c1[1]-b*c1[0])/(g.L*g.L)
        q2 = (a*c2[1]-b*c2[0])/(g.L*g.L)
        if q1 <= 0 or -n[0] <= 0:
            raise ValueError("Not the outward-rotating, closing contact branch.")
        return Contact(float(x),float(xi),atan2(b,a),float(q1),float(q2),
                       float(a),float(b),float(n[0]),float(n[1]),float(regular),
                       float(2*D),float(a*a+b*b-g.L*g.L))

    def evaluate(self, x):
        c = self.contact(x)
        return self.mass.inertias(self.geometry.rP,c.q,c.q_prime,c.q_second)

    def normal_per_roller(self, x, force):
        c = self.contact(x)
        return force/(self.mass.n*(-c.normal_x))

    def compile(self, points=257):
        if points < 9:
            raise ValueError("At least nine interpolation nodes are required.")
        xs = np.linspace(self.geometry.x_min,self.geometry.x_max,points)
        cs = [self.contact(float(x)) for x in xs]
        q = CubicSpline(xs,[c.q for c in cs],
                        bc_type=((1,cs[0].q_prime),(1,cs[-1].q_prime)), extrapolate=False)
        return CompiledFixedPivot(self,q,points)


@dataclass(frozen=True)
class CompiledFixedPivot:
    exact: FixedPivotReference
    angle: CubicSpline
    points: int

    def evaluate(self, x):
        g = self.exact.geometry
        if not g.x_min <= x <= g.x_max:
            raise ValueError("Closure outside the declared interval.")
        q, q1, q2 = (float(self.angle(x,k)) for k in range(3))
        if q1 <= 0:
            raise ValueError("Interpolated map reverses the admitted branch.")
        return self.exact.mass.inertias(g.rP,q,q1,q2)


def straight_ramp_oracle(x, g: Geometry, k):
    """Closed-form solution for d=-1, sigma=+1 and cos(q+atan(k))>0."""
    w = sqrt(1+k*k)
    D = (g.rA-g.rP)+k*(g.XA-g.XP+x)-g.R*w
    q = asin(D/(g.L*w))-atan(k)
    q1 = k/(g.L*w*cos(q+atan(k)))
    q2 = q1*q1*tan(q+atan(k))
    return q,q1,q2


def force_torque(sample: InertiaSample, *, omega, x_dot, x_ddot, alpha):
    F = .5*sample.J_prime*omega**2-sample.M*x_ddot-.5*sample.M_prime*x_dot**2
    torque = -sample.J*alpha-sample.J_prime*x_dot*omega
    return F,torque


def energy(sample: InertiaSample, *, omega, x_dot):
    return .5*sample.J*omega**2+.5*sample.M*x_dot**2
