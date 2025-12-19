"""
Dataclass definitions for ramp segment configurations.

These dataclasses define the structure for serializing/deserializing ramp
configurations. The backend will automatically generate Pydantic models from these
using auto_model.py.
"""

from dataclasses import dataclass
from typing import List, Union


@dataclass
class LinearSegmentConfig:
    """Configuration for a linear ramp segment."""
    type: str  # "linear"
    x_start: float
    x_end: float
    slope: float


@dataclass
class CircularSegmentConfig:
    """Configuration for a circular arc ramp segment."""
    type: str  # "circular"
    x_start: float
    x_end: float
    radius: float
    theta_start: float  # Starting angle in radians
    theta_end: float  # Ending angle in radians


@dataclass
class CubicSpiralZeroK1Config:
    """Configuration for a cubic spiral with specified final curvature."""
    type: str  # "cubic_spiral_zero_k1"
    x_start: float
    x_end: float
    slope_start: float  # As angle in radians
    slope_end: float  # As angle in radians
    target_curvature: float


@dataclass
class CubicSpiralZeroZeroConfig:
    """Configuration for a cubic spiral with zero curvature at both ends."""
    type: str  # "cubic_spiral_zero_zero"
    x_start: float
    x_end: float
    slope_start: float  # As angle in radians
    slope_end: float  # As angle in radians


@dataclass
class EulerSpiralConfig:
    """Configuration for an Euler spiral segment."""
    type: str  # "euler_spiral"
    x_start: float
    x_end: float
    slope_start: float  # As angle in radians
    slope_end: float  # As angle in radians


@dataclass
class ProDefinedSegmentConfig:
    """Configuration for a pro-defined segment."""
    type: str  # "pro_defined"
    x_start: float
    x_end: float
    prev_seg_height: float
    end_length: float
    initial_slope: float
    r_initial: float


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
            "linear": LinearSegmentConfig,
            "circular": CircularSegmentConfig,
            "cubic_spiral_zero_k1": CubicSpiralZeroK1Config,
            "cubic_spiral_zero_zero": CubicSpiralZeroZeroConfig,
            "euler_spiral": EulerSpiralConfig,
            "pro_defined": ProDefinedSegmentConfig,
        }
        
        segments = []
        for seg_dict in data.get("segments", []):
            seg_type = seg_dict.get("type")
            config_class = segment_type_map.get(seg_type)
            if config_class is None:
                raise ValueError(f"Unknown segment type: {seg_type}")
            segments.append(config_class(**seg_dict))
        
        return cls(segments=segments)
