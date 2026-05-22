from cvt_simulator.ramps.ramp_segment import RampSegment
from cvt_simulator.ramps.ramp_serialization import (
    segment_to_config,
    config_to_segment,
)
from cvt_simulator.ramps.ramp_config import PiecewiseRampConfig
from typing import List


class PiecewiseRamp:
    """Handles multiple ramp segments and ensures continuity automatically."""

    def __init__(self):
        self.segments: List[RampSegment] = []

    def add_segment(self, segment: RampSegment):
        """Adds a new segment and ensures continuity with previous ones."""
        if self.segments:
            prev_segment = self.segments[-1]
            # Set x positions based on previous segment
            segment.x_start = prev_segment.x_end
            segment.x_end = segment.x_start + segment.length
            # Set y_start for continuity
            prev_y_end = prev_segment.height(prev_segment.x_end)
            segment.y_start = prev_y_end
        else:
            # First segment starts at origin
            segment.x_start = 0.0
            segment.x_end = segment.length
            segment.y_start = 0.0

        self.segments.append(segment)

    def height(self, x: float) -> float:
        """Computes the height at x, ensuring continuity dynamically."""
        for segment in self.segments:
            if segment.x_start <= x <= segment.x_end:
                return segment.height(x)
        raise ValueError(f"x={x} is out of ramp range!")

    def slope(self, x: float) -> float:
        """Finds the appropriate segment and computes slope."""
        for segment in self.segments:
            if segment.x_start <= x <= segment.x_end:
                return segment.slope(x)
        raise ValueError(f"x={x} is out of ramp range!")

    def find_x_at_height(self, target_height: float) -> float:
        """Find the x position that produces a given height.

        This is the inverse of height(x). Searches through segments to find
        which one contains the target height, then inverts that segment.

        Args:
            target_height: The height value to search for

        Returns:
            x position that produces the target height

        Raises:
            ValueError: If height is not within ramp range or segment doesn't support inversion

        Note:
            Currently supports LinearSegment and CircularSegment inversion.
            CircularSegment will raise an error if the height produces ambiguous
            solutions (two valid x positions).
        """
        # Search through segments to find which contains this height
        for segment in self.segments:
            y_start = segment.height(segment.x_start)
            y_end = segment.height(segment.x_end)
            y_min = min(y_start, y_end)
            y_max = max(y_start, y_end)

            # Check if target height is in this segment's height range
            if y_min <= target_height <= y_max:
                # Try to invert this segment
                if hasattr(segment, "inverse_height"):
                    try:
                        return segment.inverse_height(target_height)
                    except ValueError as e:
                        # Check if it's an ambiguity error - if so, re-raise
                        if "ambiguous" in str(e).lower():
                            raise
                        # Otherwise, this segment's inverse failed, try next segment
                        continue
                else:
                    raise ValueError(
                        f"Segment type {type(segment).__name__} does not support inverse_height."
                    )

        raise ValueError(
            f"Height {target_height} is not within ramp range. "
            f"Ramp height range: [{self.segments[0].height(self.segments[0].x_start)}, "
            f"{self.segments[-1].height(self.segments[-1].x_end)}]"
        )

    def to_config(self) -> PiecewiseRampConfig:
        """
        Convert this ramp to its config dataclass.

        Returns:
            PiecewiseRampConfig dataclass
        """
        return PiecewiseRampConfig(
            segments=[segment_to_config(seg) for seg in self.segments]
        )

    @classmethod
    def from_config(cls, config: PiecewiseRampConfig) -> "PiecewiseRamp":
        """
        Create a PiecewiseRamp from a config dataclass.

        Args:
            config: PiecewiseRampConfig dataclass

        Returns:
            New PiecewiseRamp instance

        Note:
            Segments are added in order, and PiecewiseRamp automatically
            handles continuity by setting y_start of each segment and
            positioning them sequentially based on their length property.
        """
        ramp = cls()

        for seg_config in config.segments:
            segment = config_to_segment(seg_config)
            ramp.add_segment(segment)
        return ramp
