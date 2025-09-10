from models.ramps.ramp_segment import RampSegment
from typing import List


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
