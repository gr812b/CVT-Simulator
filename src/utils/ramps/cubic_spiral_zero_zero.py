from utils.ramps.ramp_segment import RampSegment
import math
from scipy.integrate import quad


class CubicSpiralZeroZero(RampSegment):
    """
    A cubic spiral transition defined by:

      θ(s) = θ₀ + B·s² + C·s³,   0 ≤ s ≤ L_eff,

    with boundary conditions:
      θ(0)=θ₀,    κ(0)=θ'(0)=0,
      θ(L_eff)=θ₁, κ(L_eff)=θ'(L_eff)=0.

    These conditions yield:
      B = 3(θ₁ - θ₀) / L_eff²,     C = -2(θ₁ - θ₀) / L_eff³.

    In our implementation, the user specifies x_start and x_end (thus a chord length),
    but because the horizontal projection of the spiral is:

      x(L_eff) = ∫₀^(L_eff) cos(θ(s)) ds,

    we iterate on L_eff until x(L_eff) matches the chord length exactly.
    """

    def __init__(
        self,
        x_start: float,
        x_end: float,
        slope_start: float,
        slope_end: float,
        tol: float = 1e-8,
    ):
        super().__init__(x_start, x_end)
        # The desired horizontal chord length.
        chord_target = x_end - x_start

        # Convert slopes to tangent angles.
        self.theta0 = math.atan(slope_start)
        self.theta1 = math.atan(slope_end)
        dtheta = self.theta1 - self.theta0

        # --- Find effective arc length L_eff such that the horizontal projection matches chord_target.
        # Our cubic spiral is defined as:
        #   θ(s) = θ₀ + B s² + C s³,   with B = 3*dθ / L_eff² and C = -2*dθ / L_eff³.
        # Then, horizontal projection is:
        #   x(L_eff) = ∫_0^(L_eff) cos(θ₀ + (3*dθ/L_eff²) s² - (2*dθ/L_eff³) s³) ds.
        # We want: x(L_eff) = chord_target.
        def chord_projection(L_eff):
            B = 3 * dtheta / (L_eff**2)
            C = -2 * dtheta / (L_eff**3)
            val, _ = quad(
                lambda u: math.cos(self.theta0 + B * u**2 + C * u**3), 0, L_eff
            )
            return val

        # Use bisection to solve f(L_eff) = chord_projection(L_eff) - chord_target = 0.
        # Initial guess: For a straight line, L_eff would equal chord_target.
        L_low = chord_target
        L_high = chord_target * 1.5  # a reasonable upper bound

        # Ensure that f(L_low) and f(L_high) have opposite signs.
        f_low = chord_projection(L_low) - chord_target
        f_high = chord_projection(L_high) - chord_target

        # In some cases, if dtheta is small, they may both be nearly zero.
        # We'll assume we can find bounds. Otherwise, no iteration is needed.
        while f_low * f_high > 0:
            L_high *= 1.1
            f_high = chord_projection(L_high) - chord_target

        # Bisection iteration.
        while abs(L_high - L_low) > tol:
            L_mid = (L_low + L_high) / 2.0
            f_mid = chord_projection(L_mid) - chord_target
            if f_mid * f_low < 0:
                L_high = L_mid
                f_high = f_mid
            else:
                L_low = L_mid
                f_low = f_mid
        L_eff = (L_low + L_high) / 2.0
        self.L = L_eff  # effective arc-length that gives the correct chord

        # Now compute B and C based on L_eff.
        self.B = 3 * dtheta / (self.L**2)
        self.C = -2 * dtheta / (self.L**3)
        self.delta = dtheta  # total change in angle over the spiral

    def _theta(self, s: float) -> float:
        return self.theta0 + self.B * s**2 + self.C * s**3

    def _x_of_s(self, s: float) -> float:
        val, _ = quad(lambda u: math.cos(self._theta(u)), 0, s)
        return val

    def _y_of_s(self, s: float) -> float:
        val, _ = quad(lambda u: math.sin(self._theta(u)), 0, s)
        return val

    def _find_s_for_x(self, x_offset: float, tol: float = 1e-8) -> float:
        lower, upper = 0.0, self.L
        while self._x_of_s(upper) < x_offset:
            upper *= 2
        while upper - lower > tol:
            mid = (lower + upper) / 2.0
            if self._x_of_s(mid) < x_offset:
                lower = mid
            else:
                upper = mid
        return (lower + upper) / 2.0

    def height(self, x: float) -> float:
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"{x} out of range")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return self.y_start + self._y_of_s(s_val)

    def slope(self, x: float) -> float:
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"{x} out of range")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return math.tan(self._theta(s_val))
