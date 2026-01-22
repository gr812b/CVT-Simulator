from dataclasses import dataclass
from math import asin, pi, sqrt, tan
from scipy.optimize import brentq
from cvt_simulator.constants.car_specs import (
    BELT_LENGTH,
    BELT_HEIGHT,
    MIN_PRIM_RADIUS,
    MAX_SEC_RADIUS,
    INITIAL_SHEAVE_DISPLACEMENT,
    SHEAVE_ANGLE,
    MAX_SHIFT,
)


@dataclass
class CVTRatioResult:
    r1: float
    r2: float
    ratio: float


class CVTGeometry:
    """
    CVT (Continuously Variable Transmission) geometry calculator.
    
    This class provides methods to compute primary/secondary pulley radii, 
    CVT ratio, and the rate of change of the CVT ratio with respect to shift distance.
    
    Mathematical derivations:
    - Belt length constraint and radius calculations: https://www.desmos.com/calculator/dd9whqmxcz
    - CVT ratio rate of change (di/dd): https://github.com/gr812b/CVT-Simulator/blob/develop/docs/Kai's%20folder%20of%20derivations/cvtRatioRateOfChange.png
    
    The calculations use the belt length constraint equation with center-to-center distance
    and sheave geometry to determine pulley radii at any given shift distance.
    """

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
        self.c2c = self._compute_center_to_center()

    # ---------- 1) Primary radius from axial distance d ----------
    def r_primary(self, d: float) -> float:
        if d < 0.0 or d > self.d_max:
            raise ValueError(f"d={d} out of bounds [0, {self.d_max}]")
        return (self.r_1_min + self.h) + max(
            (d - self.d_contact) / (2 * tan(self.β)), 0.0
        )

    # ---------- 2) Secondary radius from primary radius r1 ----------
    def _open_form_r_sec(self, r2: float, r1: float) -> float:
        """
        This is the open form equation relating r1 and r2 based on the belt length constraint.
        """
        delta = abs(r2 - r1)

        if delta > self.c2c:
            raise ValueError(
                f"Invalid radius values: r1={r1}, r2={r2}, larger than center-to-center distance={self.c2c}."
            )

        a = asin(delta / self.c2c)

        return (
            pi * r1
            - 2 * r1 * a
            + r2 * pi
            + 2 * r2 * a
            + 2 * sqrt(self.c2c**2 - (r2 - r1) ** 2)
            - self.L
        )

    # TODO: Decide to use this in solver or not
    def _r2_approx(self, r1: float) -> float:
        """
        Approximate solution for r2 given r1 using a closed-form expression. (r2 - r1 << C)

        Do not use this method for final calculations, only as an initial guess for more precise methods.
        """
        inner = (
            -self.L**2
            + 4 * pi * self.L * r1
            + pi**2 * self.c2c**2
            + 4 * self.c2c**2
            - 4 * pi**2 * r1**2
        )

        if inner < 0:
            raise ValueError("No real solution exists for the given r1.")

        num = pi * self.L - pi**2 * r1 + 4 * r1 - 2 * sqrt(inner)
        den = pi**2 + 4
        approx = num / den

        return approx

    def _solve_r2(self, r1: float) -> float:
        """
        Use Brent's method (`scipy.optimize.brentq`) to solve for r2 given r1.

        Starts with a low and high bracket for r2 and finds the root of `_open_form_r_sec`  
        within this interval.  
        """
        C = self.c2c
        eps = 1e-9  # small safety margin since arcsin is steep near domain boundaries

        # Define an upper and lower bound for r2, which our total belt length equation will cross zero
        lo, hi = r1 - C + eps, r1 + C - eps
        g_lo, g_hi = self._open_form_r_sec(lo, r1), self._open_form_r_sec(hi, r1)

        # must exist a sign change across the interval
        if g_lo * g_hi > 0:
            raise RuntimeError(
                "g(x) doesn't cross zero in valid domain. This should not occur!"
            )

        return brentq(self._open_form_r_sec, lo, hi, args=(r1,), xtol=1e-9)

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

    # ---------- 4) CVT Ratio Rate of Change w.r.t. d ----------
    def _cvt_ratio_derivative(self, d: float) -> float:
        """
        Computes di/dd using differentiation on the belt length constraint.
        """
        if d < self.d_contact:
            return 0

        prim_deriv = 1 / (2 * tan(self.β))
        r1 = self.r_primary(d)
        r2 = self._solve_r2(r1)

        term = pi
        # Additional term to include if r1 > r2
        if r1 > r2:
            term -= (4 * (r2 - r1)) / (sqrt(self.c2c**2 - (r2 - r1) ** 2))

        a = 2 * asin((r2 - r1) / self.c2c)
        partial_deriv_term = (term - a) / (term + a)

        rate = prim_deriv * (
            (partial_deriv_term / (r1 - self.h / 2))
            - ((r2 - self.h / 2) / ((r1 - self.h / 2) ** 2))
        )
        return rate

    def cvt_ratio_rate_of_change(self, d: float, d_vel: float) -> float:
        return self._cvt_ratio_derivative(d) * d_vel

    # ---------- Center-to-center distance calculation ----------
    # TODO: Decide to use this in solver or not
    def _c2c_approx(self) -> float:
        """
        Approximate solution for center-to-center distance using a closed-form expression.
        Uses effective radii (at belt centerline): r1 = r_1_min + h/2, r2 = r_2_max + h/2

        Do not use this method for final calculations, only as an initial guess for more precise methods.

        C_approx = sqrt((L^2 - 2*L*π*(r1+r2) + π^2*(r1+r2)^2) / 4 + (r2-r1)^2)
        """
        # Use effective radii at belt centerline
        r1_eff = self.r_1_min + self.h / 2
        r2_eff = self.r_2_max + self.h / 2

        sum_radii = r1_eff + r2_eff
        diff_radii = r2_eff - r1_eff

        inner = (
            self.L**2 - 2 * self.L * pi * sum_radii + pi**2 * sum_radii**2
        ) / 4 + diff_radii**2

        if inner < 0:
            raise ValueError("No real solution exists for center-to-center distance.")

        return sqrt(inner)

    # open form eqn needing solving
    def _c2c_constraint_equation(self, c2c: float, r1: float, r2: float) -> float:
        """
        Constraint equation for solving center-to-center distance.
        This should equal zero when c2c is correct for the given r1, r2, and belt length.

        q(c2c) = π*r1 - 2*r1*arcsin(|r2-r1|/c2c) + r2*π + 2*r2*arcsin(|r2-r1|/c2c)
                 + 2*sqrt(c2c^2 - (r2-r1)^2) - L
        """
        delta = abs(r2 - r1)

        if delta >= c2c:
            # Invalid: radii difference exceeds center-to-center distance
            return float("inf")

        a = asin(delta / c2c)

        return (
            pi * r1
            - 2 * r1 * a
            + r2 * pi
            + 2 * r2 * a
            + 2 * sqrt(c2c**2 - delta**2)
            - self.L
        )

    def _compute_center_to_center(self) -> float:
        """
        Solve for center-to-center distance using the belt length constraint
        at the boundary condition where primary is at minimum and secondary is at maximum.
        Uses effective radii (at belt centerline): r1 = r_1_min + h/2, r2 = r_2_max + h/2
        """
        # Use effective radii at belt centerline
        r1_eff = self.r_1_min + self.h / 2
        r2_eff = self.r_2_max + self.h / 2

        # Define bounds for c2c - must be greater than |r2 - r1| for arcsin to be defined
        delta = abs(r2_eff - r1_eff)
        eps = 1e-9

        # Start search slightly above delta, up to some reasonable upper bound
        lo = delta + eps
        hi = self.L / 2  # Maximum possible c2c would be roughly half the belt length

        # Check that we have a sign change
        g_lo = self._c2c_constraint_equation(lo, r1_eff, r2_eff)
        g_hi = self._c2c_constraint_equation(hi, r1_eff, r2_eff)

        if g_lo * g_hi > 0:
            raise RuntimeError(
                f"c2c constraint equation doesn't cross zero in [{lo}, {hi}]. "
                f"g(lo)={g_lo}, g(hi)={g_hi}"
            )

        return brentq(
            self._c2c_constraint_equation, lo, hi, args=(r1_eff, r2_eff), xtol=1e-9
        )


if __name__ == "__main__":
    import numpy as np

    # Initialize CVT geometry
    cvt = CVTGeometry()

    # Print all default values
    print("=" * 80)
    print("CVT GEOMETRY - DEFAULT PARAMETERS")
    print("=" * 80)
    print(f"Belt Length (L):                  {cvt.L:.6f} m")
    print(f"Belt Height (h):                  {cvt.h:.6f} m")
    print(f"Min Primary Radius (r_1_min):     {cvt.r_1_min:.6f} m")
    print(f"Max Secondary Radius (r_2_max):   {cvt.r_2_max:.6f} m")
    print(f"Initial Sheave Displacement:      {cvt.d_contact:.6f} m")
    print(f"Sheave Half-Angle (β):            {cvt.β:.6f} rad ({cvt.β * 180 / pi:.2f}°)")
    print(f"Max Shift Distance (d_max):       {cvt.d_max:.6f} m")
    print(f"Center-to-Center Distance (c2c):  {cvt.c2c:.6f} m")
    print(f"C2C Approximation:                {cvt._c2c_approx():.6f} m")
    print("=" * 80)
    print()

    # Create table from 0 to max shift distance
    num_points = 10
    d_values = np.linspace(0, cvt.d_max, num_points)

    print("=" * 80)
    print("CVT RATIO TABLE - Shift Distance vs Radii and Ratio")
    print("=" * 80)
    print(f"{'d (m)':<10} {'r1 (m)':<10} {'r2 (m)':<10} {'Ratio':<10} {'di/dd':<12}")
    print("-" * 80)

    for d in d_values:
        result = cvt.ratio_from_d(d)
        derivative = cvt._cvt_ratio_derivative(d)
        print(
            f"{d:<10.6f} {result.r1:<10.6f} {result.r2:<10.6f} "
            f"{result.ratio:<10.6f} {derivative:<12.6f}"
        )

    print("=" * 80)
