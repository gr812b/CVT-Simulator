from cvt_simulator.models.ramps.ramp_segment import RampSegment
import numpy as np
import math
from scipy.integrate import quad


class EulerSpiralSegment(RampSegment):
    """
    Euler spiral segment that transitions smoothly between two slopes.
    Instead of passing tangent angles, you supply the starting and ending slopes.
    The slopes are converted to tangent angles (θ = arctan(slope)).

    This implementation now allows the initial slope to be flatter (e.g. -0.25)
    and the final slope to be steeper (e.g. -10). The tangent angle then decreases
    along the segment, i.e. theta_start > theta_end.
    """

    def __init__(
        self, x_start: float, x_end: float, slope_start: float, slope_end: float
    ):
        """
        :param x_start: start horizontal coordinate.
        :param x_end: end horizontal coordinate (defines the horizontal span L).
        :param slope_start: starting slope (e.g. -0.25 for a flat start).
        :param slope_end: ending slope (e.g. -10 for a steep end).
        """
        super().__init__(x_start, x_end)
        # Convert slopes to tangent angles.
        self.theta_start = np.arctan(slope_start)
        self.theta_end = np.arctan(slope_end)
        # Note: for a transition from flatter to steeper (more negative) slope,
        # theta_start > theta_end.
        self.delta = self.theta_end - self.theta_start  # This will be negative.

        # Horizontal length of the segment.
        self.L = self.x_end - self.x_start

        # Compute the normalization factor:
        # I = ∫₀¹ cos(theta_start + delta*u²) du.
        I, _ = quad(lambda u: np.cos(self.theta_start + self.delta * u**2), 0, 1)
        # Set s_end so that the horizontal projection equals L.
        self.s_end = self.L / I

    def _x_of_s(self, s: float) -> float:
        """Computes the horizontal displacement for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(
            lambda u: np.cos(self.theta_start + self.delta * u**2), 0, u_upper
        )
        return self.s_end * integral

    def _y_of_s(self, s: float) -> float:
        """Computes the vertical displacement for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(
            lambda u: np.sin(self.theta_start + self.delta * u**2), 0, u_upper
        )
        return self.s_end * integral

    def _find_s_for_x(self, x_offset: float, tol: float = 1e-8) -> float:
        """
        Uses binary search to find the arc length s corresponding to a given horizontal offset.
        """
        lower = 0.0
        upper = self.s_end
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
        """
        Returns the vertical height at horizontal position x.
        """
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"x={x} is out of the Euler spiral segment range!")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        return self.y_start + self._y_of_s(s_val)

    def slope(self, x: float) -> float:
        """
        Returns the slope (dy/dx) at horizontal position x.
        """
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(f"x={x} is out of the Euler spiral segment range!")
        x_offset = x - self.x_start
        s_val = self._find_s_for_x(x_offset)
        # Compute the instantaneous tangent angle:
        angle = self.theta_start + self.delta * (s_val / self.s_end) ** 2
        return math.tan(angle)
