"""
Dataclass definitions for ramp segment configurations.

These dataclasses define the structure for serializing/deserializing ramp
configurations. The backend will automatically generate Pydantic models from these
using auto_model.py.
"""

from dataclasses import dataclass, field
from typing import List, Union, Literal
from enum import Enum


class RampSegmentType(str, Enum):
    """Enum for ramp segment types. Inherits from str for JSON serialization."""

    LINEAR = "linear"
    CIRCULAR = "circular"


@dataclass
class LinearSegmentConfig:
    """Configuration for a linear ramp segment."""

    length: float
    angle: float  # Slope angle in degrees (e.g., -45 for slope of -1, always use actual sign)
    type: Literal[RampSegmentType.LINEAR] = field(
        default=RampSegmentType.LINEAR, init=False
    )


@dataclass
class CircularSegmentConfig:
    """Configuration for a circular arc ramp segment."""

    length: float
    angle_start: float  # Starting slope angle in degrees (e.g., -45 for slope of -1)
    angle_end: float  # Ending slope angle in degrees
    quadrant: int = 3  # Which quadrant of circle (1-4), default 3
    type: Literal[RampSegmentType.CIRCULAR] = field(
        default=RampSegmentType.CIRCULAR, init=False
    )


# Union type for any segment configuration
RampSegmentConfig = Union[
    LinearSegmentConfig,
    CircularSegmentConfig,
]


@dataclass
class PiecewiseRampConfig:
    """
    Configuration for a piecewise ramp composed of multiple segments.

    Segments are automatically connected end-to-end to ensure continuity.
    """

    segments: List[RampSegmentConfig]

    @classmethod
    def from_dict(cls, data: dict) -> "PiecewiseRampConfig":
        """
        Create PiecewiseRampConfig from a dictionary with type discrimination.

        Handles the conversion of segment dicts to proper config dataclass instances
        based on the 'type' field.
        """
        segment_type_map = {
            RampSegmentType.LINEAR: LinearSegmentConfig,
            RampSegmentType.CIRCULAR: CircularSegmentConfig,
        }

        segments = []
        for seg_dict in data.get("segments", []):
            seg_type = seg_dict.get("type")
            # Convert string to enum if needed
            if isinstance(seg_type, str):
                try:
                    seg_type = RampSegmentType(seg_type)
                except ValueError:
                    raise ValueError(f"Unknown segment type: {seg_type}")

            config_class = segment_type_map.get(seg_type)
            if config_class is None:
                raise ValueError(f"Unknown segment type: {seg_type}")

            # Remove 'type' from dict before passing to constructor (it's set automatically)
            seg_dict_copy = {k: v for k, v in seg_dict.items() if k != "type"}
            segments.append(config_class(**seg_dict_copy))

        return cls(segments=segments)
