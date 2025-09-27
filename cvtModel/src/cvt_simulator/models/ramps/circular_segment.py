from cvt_simulator.models.ramps.ramp_segment import RampSegment
import numpy as np
import math


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
    def angle_to_x(self, theta: float) -> float:
        return self.radius * math.cos(theta)

    # Equation of a circle in the third quadrant
    def f(self, x: float) -> float:
        return -math.sqrt(self.radius**2 - x**2)

    def f_prime(self, x: float) -> float:
        return x / math.sqrt(self.radius**2 - x**2)

    def map_x(self, x: float) -> float:
        start_offset = self.angle_to_x(self.theta_start)
        end_offset = self.angle_to_x(self.theta_end)

        scaled_x = (x - self.x_start) / (self.x_end - self.x_start)
        adjusted_x = start_offset + scaled_x * (end_offset - start_offset)

        return adjusted_x

    def height(self, x: float) -> float:
        """Finds y-coordinate on the circular arc corresponding to x."""
        adjusted_x = self.map_x(x)
        starting_height = self.f(self.angle_to_x(self.theta_start))
        return self.f(adjusted_x) - starting_height + self.y_start

    def slope(self, x: float) -> float:
        """Returns the slope (dy/dx) at position x on the ramp."""
        adjusted_x = self.map_x(x)
        return self.f_prime(adjusted_x)
