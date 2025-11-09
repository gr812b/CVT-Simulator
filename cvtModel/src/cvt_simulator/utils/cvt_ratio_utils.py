from dataclasses import dataclass
import math
from math import asin, pi, sqrt, tan
import numpy as np
from scipy.optimize import bisect
from cvt_simulator.constants.car_specs import BELT_LENGTH, BELT_HEIGHT, MIN_PRIM_RADIUS, MAX_SEC_RADIUS, INITIAL_SHEAVE_DISPLACEMENT, SHEAVE_ANGLE, MAX_SHIFT

@dataclass
class CVTRatioResult:
    r1: float
    r2: float
    ratio: float

class CVTGeometry:
    def __init__(self):
        self.L = BELT_LENGTH
        self.h = BELT_HEIGHT
        self.r_1_min = MIN_PRIM_RADIUS
        self.r_2_max = MAX_SEC_RADIUS
        # Distance along the sheave axis where the belt starts to transfer torque
        self.d_contact = INITIAL_SHEAVE_DISPLACEMENT
        # Groove half angle
        self.β = SHEAVE_ANGLE / 2
        self.d_max = MAX_SHIFT
        self.c2c = self.compute_center_to_center()

    # ---------- 1) Primary radius from axial distance d ----------
    def r_primary(self, d: float) -> float:
        if d < 0.0 or d > self.d_max:
            raise ValueError(f"d={d} out of bounds [0, {self.d_max}]")
        return self.r_1_min + max((self.d_contact - d) / (2 * tan(self.β)), 0.0)

    # ---------- 2) Secondary radius from primary radius r1 ----------
    def _open_form_r_sec(self, r2: float, r1: float) -> float:
        """
        This is the open form equation relating r1 and r2 based on the belt length constraint.
        """
        delta = abs(r2 - r1)

        if delta > self.c2c:
            raise ValueError(f"Invalid radius values: r1={r1}, r2={r2}, larger than center-to-center distance={self.c2c}.")
        
        a = asin(delta / self.c2c)

        return (pi * r1
                - 2 * r1 * a
                + r2 * pi
                + 2 * r2 * a
                + 2 * sqrt(self.c2c ** 2 - (r2 - r1) ** 2)
                - self.L)

    # TODO: Decide to use this in solver or not
    def _r2_approx(self, r1: float) -> float:
        """
        Approximate solution for r2 given r1 using a closed-form expression. (r2 - r1 << C)

        Do not use this method for final calculations, only as an initial guess for more precise methods.
        """
        inner = (-self.L ** 2 + 4 * pi * self.L * r1 + pi ** 2 * self.C ** 2 + 4 * self.C ** 2 - 4 * pi ** 2 * r1 ** 2)
        
        if inner < 0:
            raise ValueError("No real solution exists for the given r1.")
        
        num = (pi * self.L - pi ** 2 * r1 + 4 * r1 - 2 * sqrt(inner))
        den = (pi ** 2 + 4)
        approx = num / den

        return approx

    def _solve_r2(self, r1: float) -> float:
        """
        Use the bisection method to solve for r2 given r1.
        
        Starts with a low and high 
        """
        C = self.C
        eps = 1e-9  # small safety margin since arcsin is steep near domain boundaries

        # Define an upper and lower bound for r2, which our total belt length equation will cross zero
        lo, hi = r1 - C + eps, r1 + C - eps
        g_lo, g_hi = self._open_form_r_sec(lo, r1), self._open_form_r_sec(hi, r1)

        # must exist a sign change across the interval
        if g_lo * g_hi > 0:
            raise RuntimeError("g(x) doesn't cross zero in valid domain. This should not occur!")

        return bisect(self._open_form_r_sec, lo, hi, args=(r1,), xtol=1e-9)

    # Public method to get secondary radius from d
    def r_secondary(self, d: float) -> float:
        r1 = self.r_primary(d)
        return self._solve_r2(r1)

    # ---------- 3) Ratio from d ----------
    def ratio_from_d(self, d: float):
        r1 = self.r_primary(d)
        r2 = self._solve_r2(r1)
        r1_eff = r1 - self.h / 2
        r2_eff = r2 - self.h / 2
        ratio = r2_eff / r1_eff
        return CVTRatioResult(r1=r1, r2=r2, ratio=ratio)
    
    # TODO: Check this math
    def _compute_center_to_center(self) -> float:
        outer_prim = self.r_1_min + self.h
        c2c = (
            self.L
            - np.pi * (outer_prim + self.r_2_max)
            + math.sqrt(
                (np.pi * (outer_prim + self.r_2_max)) ** 2
                - 2 * np.pi * self.L * (outer_prim + self.r_2_max)
                + self.L ** 2
                - 8 * (self.r_2_max - outer_prim) ** 2
            )
        ) / 4
        return c2c