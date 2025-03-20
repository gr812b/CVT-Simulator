import numpy as np
from typing import List
import matplotlib.pyplot as plt
from constants.car_specs import MAX_SHIFT
import math


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
        self, x_start: float, x_end: float, radius: float, theta_start: float, theta_end: float
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
        return -math.sqrt(self.radius - x ** 2)
    
    def f_prime(self, x: float) -> float:
        return x / math.sqrt(self.radius - x ** 2)
    
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
        return  self.f(adjusted_x) - starting_height + self.y_start

    def slope(self, x: float) -> float:
        """Returns the slope (dy/dx) at position x on the ramp."""
        adjusted_x = self.map_x(x)
        return self.f_prime(adjusted_x)


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
    ramp.add_segment(LinearSegment(x_start=0, x_end=MAX_SHIFT / 6, slope=-0.3))
    ramp.add_segment(
        CircularSegment(
            x_start=MAX_SHIFT / 6,
            x_end=MAX_SHIFT,
            radius=0.001,
            theta_start=0.5,
            theta_end=np.pi / 2 - 0.4,
        )
    )

    # Evaluate ramp
    x_values = np.linspace(0, MAX_SHIFT, 1000)
    y_values = [-ramp.height(x) for x in x_values]

    # Plot results
    plt.plot(x_values, y_values)
    plt.xlabel("X Position")
    plt.ylabel("Height")
    plt.title("Piecewise Ramp Profile")
    plt.gca().set_aspect('equal', adjustable='box')
    plt.grid()
    plt.show()

    # Evaluate slope
    slope_values = [ramp.slope(x) for x in x_values]

    # Plot results
    plt.plot(x_values, slope_values)
    plt.xlabel("X Position")
    plt.ylabel("Slope")
    plt.title("Piecewise Ramp Slope Profile")
    plt.grid()
    plt.show()

    # Evaluate angle
    angle_values = [np.arctan(slope) for slope in slope_values]

    # Plot results
    plt.plot(x_values, angle_values)
    plt.xlabel("X Position")
    plt.ylabel("Angle")
    plt.title("Piecewise Ramp Angle Profile")
    plt.grid()
    plt.show()
