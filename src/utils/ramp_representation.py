import numpy as np
from typing import List
import matplotlib.pyplot as plt
from constants.car_specs import BELT_WIDTH


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
        return self.m * (x - self.x_start)

    def slope(self, x: float) -> float:
        return self.m


class CircularSegment(RampSegment):
    """Circular segment where user defines only radius and rotation."""

    def __init__(
        self, x_start: float, x_end: float, radius: float, theta_fraction: float
    ):
        """
        :param x_start: Start x position
        :param x_end: End x position (automatically inferred)
        :param radius: Circle radius
        :param theta_fraction: Fraction of π/2 to rotate (0 to 1 for 0° to 90°)
        """
        super().__init__(x_start, x_end)
        self.radius = radius
        self.theta_start = np.pi  # Start at π (pointing left)
        self.theta_end = np.pi + theta_fraction * (np.pi / 2)  # Rotate counterclockwise

    def height(self, x: float) -> float:
        """Finds y-coordinate on the circular arc corresponding to x."""
        # Map x linearly into the circle’s angle.
        t = (x - self.x_start) / (self.x_end - self.x_start)
        theta = self.theta_start + t * (self.theta_end - self.theta_start)
        # Use the circle equation. Since at x_start we have theta = π and sin(π)=0, height equals y_start.
        return self.y_start + self.radius * np.sin(theta)

    def slope(self, x: float) -> float:
        """Derivative of a circular segment = -tan(theta)"""
        # As above, map x to theta.
        t = (x - self.x_start) / (self.x_end - self.x_start)
        theta = self.theta_start + t * (self.theta_end - self.theta_start)
        dtheta_dx = (self.theta_end - self.theta_start) / (self.x_end - self.x_start)
        # Chain rule: d(height)/dx = R*cos(theta) * dtheta/dx.
        return self.radius * np.cos(theta) * dtheta_dx


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
    # Example usage
    x_midpoint = 0.02
    ramp_length = 0.06

    # Sample primary ramp
    ramp = PiecewiseRamp()
    ramp.add_segment(LinearSegment(x_start=0, x_end=BELT_WIDTH / 5, slope=-1))
    ramp.add_segment(
        CircularSegment(
            x_start=BELT_WIDTH / 5,
            x_end=BELT_WIDTH,
            radius=0.025,
            theta_fraction=1,
        )
    )

    # Evaluate ramp
    x_values = np.linspace(0, BELT_WIDTH, 100)
    y_values = [-ramp.height(x) for x in x_values]

    # Plot results
    plt.plot(x_values, y_values)
    plt.xlabel("X Position")
    plt.ylabel("Height")
    plt.title("Piecewise Ramp Profile")
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
    angle_values = [np.arctan(slope) * 180 / np.pi for slope in slope_values]

    # Plot results
    plt.plot(x_values, angle_values)
    plt.xlabel("X Position")
    plt.ylabel("Angle")
    plt.title("Piecewise Ramp Angle Profile")
    plt.grid()
    plt.show()
