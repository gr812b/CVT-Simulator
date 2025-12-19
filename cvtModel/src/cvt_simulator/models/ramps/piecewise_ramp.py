from cvt_simulator.models.ramps.ramp_segment import RampSegment
from cvt_simulator.models.ramps.ramp_serialization import segment_to_config, config_to_segment
from cvt_simulator.models.ramps.ramp_config import PiecewiseRampConfig
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
            handles continuity by setting y_start of each segment.
            x_start and x_end are calculated by accumulating segment lengths.
        """
        ramp = cls()
        x_position = 0.0  # Track the current x position
        
        for seg_config in config.segments:
            segment = config_to_segment(seg_config)
            # Calculate length before modifying x_start
            length = segment.x_end - segment.x_start  # segment.x_end was set to length in config_to_segment
            # Update segment's x positions based on accumulated length
            segment.x_start = x_position
            segment.x_end = x_position + length
            x_position = segment.x_end
            ramp.add_segment(segment)
        return ramp
