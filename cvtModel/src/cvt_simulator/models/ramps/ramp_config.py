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
    CUBIC_SPIRAL_ZERO_K1 = "cubic_spiral_zero_k1"
    CUBIC_SPIRAL_ZERO_ZERO = "cubic_spiral_zero_zero"
    EULER_SPIRAL = "euler_spiral"
    PRO_DEFINED = "pro_defined"


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


@dataclass
class CubicSpiralZeroK1Config:
    """Configuration for a cubic spiral with specified final curvature."""

    length: float
    slope_start: float  # As angle in radians
    slope_end: float  # As angle in radians
    target_curvature: float
    type: Literal[RampSegmentType.CUBIC_SPIRAL_ZERO_K1] = field(
        default=RampSegmentType.CUBIC_SPIRAL_ZERO_K1, init=False
    )


@dataclass
class CubicSpiralZeroZeroConfig:
    """Configuration for a cubic spiral with zero curvature at both ends."""

    length: float
    slope_start: float  # As angle in radians
    slope_end: float  # As angle in radians
    type: Literal[RampSegmentType.CUBIC_SPIRAL_ZERO_ZERO] = field(
        default=RampSegmentType.CUBIC_SPIRAL_ZERO_ZERO, init=False
    )


@dataclass
class EulerSpiralConfig:
    """Configuration for an Euler spiral segment."""

    length: float
    slope_start: float  # As angle in radians
    slope_end: float  # As angle in radians
    type: Literal[RampSegmentType.EULER_SPIRAL] = field(
        default=RampSegmentType.EULER_SPIRAL, init=False
    )


@dataclass
class ProDefinedSegmentConfig:
    """Configuration for a pro-defined segment."""

    length: float
    prev_seg_height: float
    end_length: float
    initial_slope: float
    r_initial: float
    type: Literal[RampSegmentType.PRO_DEFINED] = field(
        default=RampSegmentType.PRO_DEFINED, init=False
    )


# Union type for any segment configuration
RampSegmentConfig = Union[
    LinearSegmentConfig,
    CircularSegmentConfig,
    CubicSpiralZeroK1Config,
    CubicSpiralZeroZeroConfig,
    EulerSpiralConfig,
    ProDefinedSegmentConfig,
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
            RampSegmentType.CUBIC_SPIRAL_ZERO_K1: CubicSpiralZeroK1Config,
            RampSegmentType.CUBIC_SPIRAL_ZERO_ZERO: CubicSpiralZeroZeroConfig,
            RampSegmentType.EULER_SPIRAL: EulerSpiralConfig,
            RampSegmentType.PRO_DEFINED: ProDefinedSegmentConfig,
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
