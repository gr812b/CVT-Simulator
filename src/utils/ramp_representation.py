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
    Instead of passing tangent angles, you supply the starting and ending slopes.
    The slopes are converted to tangent angles (θ = arctan(slope)).
    
    This implementation now allows the initial slope to be flatter (e.g. -0.25)
    and the final slope to be steeper (e.g. -10). The tangent angle then decreases 
    along the segment, i.e. theta_start > theta_end.
    """
    def __init__(self, x_start: float, x_end: float, slope_start: float, slope_end: float):
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
        integral, _ = quad(lambda u: np.cos(self.theta_start + self.delta * u**2), 0, u_upper)
        return self.s_end * integral

    def _y_of_s(self, s: float) -> float:
        """Computes the vertical displacement for a given arc length s."""
        u_upper = s / self.s_end
        integral, _ = quad(lambda u: np.sin(self.theta_start + self.delta * u**2), 0, u_upper)
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


def visualize_ramps(ramps):
    """
    Visualizes the ramp profiles for height, slope, and angle as three separate graphs.
    The height graph is displayed with an equal aspect ratio.
    
    :param ramps: A list of ramp objects. Each ramp should have a .segments attribute,
                  and each segment must support .height(x) and .slope(x) methods.
    """
    # Helper function to determine style based on segment type.
    def get_segment_style(segment):
        if hasattr(segment, '__class__'):
            if segment.__class__.__name__ == "LinearSegment":
                return "blue", "Linear"
            elif segment.__class__.__name__ == "EulerSpiralSegment":
                return "red", "Euler Spiral"
        # Default for other types:
        return "black", type(segment).__name__
    
    # Generic helper to plot a given attribute for all ramp segments.
    def plot_attribute(attribute_func, ylabel, title, equal_aspect=False):
        plt.figure()
        used_labels = set()
        for ramp in ramps:
            for segment in ramp.segments:
                x_vals = np.linspace(segment.x_start, segment.x_end, 200)
                y_vals = [attribute_func(segment, x) for x in x_vals]
                color, label = get_segment_style(segment)
                if label in used_labels:
                    label = None
                else:
                    used_labels.add(label)
                plt.plot(x_vals, y_vals, color=color, label=label)
        plt.xlabel("X Position")
        plt.ylabel(ylabel)
        plt.title(title)
        plt.grid(True)
        if equal_aspect:
            plt.gca().set_aspect("equal", adjustable="box")
        plt.legend()
    
    # Plot Height Profile (equal aspect ratio).
    plot_attribute(lambda seg, x: seg.height(x), "Height", "Height Profile by Segment", equal_aspect=True)
    
    # Plot Slope Profile.
    plot_attribute(lambda seg, x: seg.slope(x), "Slope (dy/dx)", "Slope Profile by Segment", equal_aspect=False)
    
    # Plot Angle Profile (angle computed as arctan(slope)).
    plot_attribute(lambda seg, x: np.arctan(seg.slope(x)), "Angle (radians)", "Angle Profile by Segment", equal_aspect=False)
    
    plt.show()


if __name__ == "__main__":
    length = 1.125
    eulerLength = 0.025
    # Sample primary ramp
    ramp = PiecewiseRamp()

    line = LinearSegment(x_start=0, x_end=0.125, slope=math.tan(math.radians(-15)))
    circle = CircularSegment(
        x_start=line.x_end + eulerLength,
        x_end=length,
        radius=25,
        theta_start=0.971816735418,
        theta_end=1.1984521248,
    )
    euler = EulerSpiralSegment(
        x_start=line.x_end,
        x_end=line.x_end + eulerLength,
        slope_start=line.slope(line.x_start),
        slope_end=circle.slope(circle.x_start)
    )
    ramp.add_segment(line)
    ramp.add_segment(euler)
    ramp.add_segment(circle)

    visualize_ramps([ramp])

    