import numpy as np
from typing import List
import matplotlib.pyplot as plt
from constants.car_specs import MAX_SHIFT
import math
from scipy.integrate import quad


class RampSegment:
    """Base class for ramp segments."""

    def __init__(self, x_start: float, x_end: float):
        self.x_start = x_start
        self.x_end = x_end
        self.y_start = None  # Will be set automatically

    def height(self, x: float) -> float:
        """Returns height at given x."""
        raise NotImplementedError

    def slope(self, x: float) -> float:
        """Returns derivative (slope) at given x."""
        raise NotImplementedError


class LinearSegment(RampSegment):
    """Linear segment: y = mx"""

    def __init__(self, x_start: float, x_end: float, slope: float):
        super().__init__(x_start, x_end)
        self.m = slope

    def height(self, x: float) -> float:
        return self.m * (x - self.x_start) + self.y_start

    def slope(self, x: float) -> float:
        return self.m


class CircularSegment(RampSegment):
    """Circular segment where user defines rotation."""

    def __init__(
        self,
        x_start: float,
        x_end: float,
        radius: float,
        theta_start: float,
        theta_end: float,
    ):
        """
        :param x_start: Start x position
        :param x_end: End x position (automatically inferred)
        :param theta_start: Start angle in radians (from 0 to π/2)
        :param theta_end: End angle in radians (from 0 to π/2)
        """
        super().__init__(x_start, x_end)

        if not (0 <= theta_start <= np.pi / 2):
            raise ValueError("theta_start must be in [0, π/2]")
        if not (0 <= theta_end <= np.pi / 2):
            raise ValueError("theta_end must be in [0, π/2]")
        if theta_start >= theta_end:
            raise ValueError("theta_start must be less than theta_end")

        self.theta_start = np.pi + theta_start
        self.theta_end = np.pi + theta_end
        self.radius = radius

    # Convert from an angle to the x distance from axis
    def helpful_guy(self, theta: float) -> float:
        return -math.sqrt(self.radius / (1 + np.tan(theta) ** 2))

    # Equation of a circle in the third quadrant
    def f(self, x: float) -> float:
        return -math.sqrt(self.radius - x**2)

    def f_prime(self, x: float) -> float:
        return x / math.sqrt(self.radius - x**2)

    def map_x(self, x: float) -> float:
        start_offset = self.helpful_guy(self.theta_start)
        end_offset = self.helpful_guy(self.theta_end)

        scaled_x = (x - self.x_start) / (self.x_end - self.x_start)
        adjusted_x = start_offset + scaled_x * (end_offset - start_offset)

        return adjusted_x

    def height(self, x: float) -> float:
        """Finds y-coordinate on the circular arc corresponding to x."""
        adjusted_x = self.map_x(x)
        starting_height = self.f(self.helpful_guy(self.theta_start))
        return self.f(adjusted_x) - starting_height + self.y_start

    def slope(self, x: float) -> float:
        """Returns the slope (dy/dx) at position x on the ramp."""
        adjusted_x = self.map_x(x)
        return self.f_prime(adjusted_x)


class EulerSpiralSegment(RampSegment):
    """
    Euler spiral segment that transitions smoothly between two slopes.
    Instead of tangent angles, you supply the initial and final slopes.
    The slopes are converted to tangent angles (θ = arctan(slope)).
    This version assumes slopes are in the range -∞ to 0.
    """
    def __init__(self, x_start: float, x_end: float, slope_start: float, slope_end: float):
        """
        :param x_start: start horizontal coordinate
        :param x_end: end horizontal coordinate (defines the horizontal span L)
        :param slope_start: starting slope (e.g., a very negative value, approaching -∞)
        :param slope_end: ending slope (e.g., 0 for horizontal)
        """
        super().__init__(x_start, x_end)
        # Convert slopes to tangent angles
        self.theta_start = np.arctan(slope_start)
        self.theta_end = np.arctan(slope_end)
        
        if self.theta_start >= self.theta_end:
            raise ValueError("slope_start must be less than slope_end (i.e. more negative than slope_end)")
        
        self.delta = self.theta_end - self.theta_start  # total change in tangent angle
        
        # Horizontal length of the segment
        self.L = self.x_end - self.x_start
        
        # Compute normalization factor I = ∫₀¹ cos(θ_start + delta * u²) du.
        I, _ = quad(lambda u: np.cos(self.theta_start + self.delta * u**2), 0, 1)
        # s_end is chosen so that the horizontal projection matches L
        self.s_end = self.L / I

    def _x_of_s(self, s: float) -> float:
        """Computes the horizontal distance traveled for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(lambda u: np.cos(self.theta_start + self.delta * u**2), 0, u_upper)
        return self.s_end * integral

    def _y_of_s(self, s: float) -> float:
        """Computes the vertical displacement for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(lambda u: np.sin(self.theta_start + self.delta * u**2), 0, u_upper)
        return self.s_end * integral

    def _find_s_for_x(self, x_offset: float, tol: float = 1e-8) -> float:
        """
        Given a horizontal offset (x - x_start), find the corresponding arc length s.
        Uses a simple binary search.
        """
        lower = 0.0
        upper = self.s_end
        # Ensure the value at upper is at least x_offset
        while self._x_of_s(upper) < x_offset:
            upper *= 2
        
        while upper - lower > tol:
            mid = (lower + upper) / 2.0
            x_mid = self._x_of_s(mid)
            if x_mid < x_offset:
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
        # Instantaneous tangent angle:
        angle = self.theta_start + self.delta * (s_val / self.s_end) ** 2
        return math.tan(angle)


class PiecewiseRamp:
    """Handles multiple ramp segments and ensures continuity automatically."""

    def __init__(self):
        self.segments: List[RampSegment] = []

    def add_segment(self, segment: RampSegment):
        """Adds a new segment and ensures continuity with previous ones."""
        if self.segments:
            prev_segment = self.segments[-1]
            prev_y_end = prev_segment.height(prev_segment.x_end)
            segment.y_start = prev_y_end  # Auto-connect
        else:
            segment.y_start = 0  # Default start height

        self.segments.append(segment)

    def height(self, x: float) -> float:
        """Computes the height at x, ensuring continuity dynamically."""
        for segment in self.segments:
            if segment.x_start <= x <= segment.x_end:
                return abs(segment.height(x))
        raise ValueError(f"x={x} is out of ramp range!")

    def slope(self, x: float) -> float:
        """Finds the appropriate segment and computes slope."""
        for segment in self.segments:
            if segment.x_start <= x <= segment.x_end:
                return abs(segment.slope(x))
        raise ValueError(f"x={x} is out of ramp range!")


if __name__ == "__main__":
    # Sample primary ramp
    ramp = PiecewiseRamp()
    ramp.add_segment(
        LinearSegment(x_start=0, x_end=MAX_SHIFT/4, slope=-1)
    )
    
    # Euler spiral from MAX_SHIFT/4 to MAX_SHIFT/2,
    # transitioning from the linear segment's slope to a new slope.
    # For example, starting at -0.5 rad and ending at -0.2 rad.
    ramp.add_segment(
        EulerSpiralSegment(
            x_start=MAX_SHIFT/4,
            x_end=MAX_SHIFT*0.4,
            slope_start=-1,
            slope_end=-0.2
        )
    )
    ramp.add_segment(
        LinearSegment(x_start=MAX_SHIFT*0.4, x_end=MAX_SHIFT, slope=-0.2)
    )


    plt.figure()
    used_labels = set()
    for segment in ramp.segments:
        x_vals = np.linspace(segment.x_start, segment.x_end, 200)
        y_vals = [segment.height(x) for x in x_vals]
        if isinstance(segment, LinearSegment):
            color = "blue"
            label = "Linear"
        elif isinstance(segment, EulerSpiralSegment):
            color = "red"
            label = "Euler Spiral"
        else:
            color = "black"
            label = type(segment).__name__
        if label in used_labels:
            label = None
        else:
            used_labels.add(label)
        plt.plot(x_vals, y_vals, color=color, label=label)
    plt.xlabel("X Position")
    plt.ylabel("Height")
    plt.title("Height Profile by Segment")
    plt.grid()
    plt.legend()
    plt.gca().set_aspect("equal", adjustable="box")
    plt.show()

    # Plot the Slope Profile by Segment
    plt.figure()
    used_labels = set()
    for segment in ramp.segments:
        x_vals = np.linspace(segment.x_start, segment.x_end, 200)
        slope_vals = [segment.slope(x) for x in x_vals]
        if isinstance(segment, LinearSegment):
            color = "blue"
            label = "Linear"
        elif isinstance(segment, EulerSpiralSegment):
            color = "red"
            label = "Euler Spiral"
        else:
            color = "black"
            label = type(segment).__name__
        if label in used_labels:
            label = None
        else:
            used_labels.add(label)
        plt.plot(x_vals, slope_vals, color=color, label=label)
    plt.xlabel("X Position")
    plt.ylabel("Slope (dy/dx)")
    plt.title("Slope Profile by Segment")
    plt.grid()
    plt.legend()
    plt.show()

    # Plot the Angle Profile by Segment (angle computed as arctan(slope))
    plt.figure()
    used_labels = set()
    for segment in ramp.segments:
        x_vals = np.linspace(segment.x_start, segment.x_end, 200)
        angle_vals = [np.arctan(segment.slope(x)) for x in x_vals]
        if isinstance(segment, LinearSegment):
            color = "blue"
            label = "Linear"
        elif isinstance(segment, EulerSpiralSegment):
            color = "red"
            label = "Euler Spiral"
        else:
            color = "black"
            label = type(segment).__name__
        if label in used_labels:
            label = None
        else:
            used_labels.add(label)
        plt.plot(x_vals, angle_vals, color=color, label=label)
    plt.xlabel("X Position")
    plt.ylabel("Angle (radians)")
    plt.title("Angle Profile by Segment")
    plt.grid()
    plt.legend()
    plt.show()