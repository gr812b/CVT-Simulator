from cvt_simulator.ramps.ramp_segment import RampSegment
import math


class LinearSegment(RampSegment):
    """Linear segment: y = mx"""

    def __init__(self, length: float, angle: float):
        """
        :param length: Horizontal length of the segment
        :param angle: Slope angle in degrees (e.g., -45 for slope of -1, 30 for slope of 0.577)
        """
        super().__init__(length)
        self.angle = angle
        self.m = math.tan(math.radians(angle))

    def height(self, x: float) -> float:
        return self.m * (x - self.x_start) + self.y_start

    def slope(self, x: float) -> float:
        return self.m

    def inverse_height(self, y: float) -> float:
        """Given a height y, find the x position that produces that height.

        Solves: y = m*(x - x_start) + y_start
        For:    x = (y - y_start)/m + x_start

        Args:
            y: Target height

        Returns:
            x position that produces the given height

        Raises:
            ValueError: If slope is zero (horizontal line) or y is out of range
        """
        if abs(self.m) < 1e-10:
            raise ValueError("Cannot invert horizontal line (slope ~0)")

        x = (y - self.y_start) / self.m + self.x_start

        # Check if x is within segment bounds
        if not (self.x_start <= x <= self.x_end):
            raise ValueError(
                f"Height y={y} corresponds to x={x} which is outside "
                f"segment range [{self.x_start}, {self.x_end}]"
            )

        return x
