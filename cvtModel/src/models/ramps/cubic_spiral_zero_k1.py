from models.ramps.ramp_segment import RampSegment
import math
from scipy.integrate import quad


class CubicSpiralZeroK1(RampSegment):
    """
    Cubic spiral defined by:
      θ(s) = θ₀ + B s² + C s³,   0 ≤ s ≤ L_eff,
    with:
      θ(0) = θ₀ = arctan(slope_start),
      θ'(0)=0,
      θ(L_eff)=θ₁ = arctan(target_slope),
      θ'(L_eff)=k₁  (target curvature).

    The coefficients are given by:
      C = (k₁ L_eff - 2(θ₁-θ₀)) / L_eff³,
      B = -k₁/L_eff + 3(θ₁-θ₀)/L_eff².

    Because the horizontal projection of the spiral is
      x(L_eff) = ∫₀^(L_eff) cos(θ(s)) ds,
    we adjust L_eff using bisection so that x(L_eff) equals the given chord length.
    """

    def __init__(
        self,
        x_start: float,
        x_end: float,
        slope_start: float,
        slope_end: float,
        target_curvature: float,
        tol: float = 1e-8,
    ):
        super().__init__(x_start, x_end)
        chord_target = x_end - x_start

        self.theta0 = math.atan(slope_start)
        self.theta1 = math.atan(slope_end)
        dtheta = self.theta1 - self.theta0
        self.k1 = target_curvature  # target curvature at end

        # Define a function that, given an effective arc length L_eff, returns the horizontal projection.
        def chord_projection(L_eff):
            B = -self.k1 / L_eff + 3 * dtheta / (L_eff**2)
            C = (self.k1 * L_eff - 2 * dtheta) / (L_eff**3)
            val, _ = quad(
                lambda u: math.cos(self.theta0 + B * u**2 + C * u**3), 0, L_eff
            )
            return val

        # Use bisection to solve chord_projection(L_eff) = chord_target.
        L_low = chord_target
        L_high = chord_target * 1.5
        f_low = chord_projection(L_low) - chord_target
        f_high = chord_projection(L_high) - chord_target
        while f_low * f_high > 0:
            L_high *= 1.1
            f_high = chord_projection(L_high) - chord_target
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
        self.L = L_eff  # effective arc length for the spiral

        # Now set coefficients B and C using the formulas:
        self.B = -self.k1 / self.L + 3 * dtheta / (self.L**2)
        self.C = (self.k1 * self.L - 2 * dtheta) / (self.L**3)
        self.delta = dtheta

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
