# flake8: noqa
# Segment classes for building ramps
from .circular_segment import CircularSegment
# from .cubic_spiral_zero_k1 import CubicSpiralZeroK1
# from .cubic_spiral_zero_zero import CubicSpiralZeroZero
# from .euler_spiral_segment import EulerSpiralSegment
from .linear_segment import LinearSegment
# from .archive.pro_defined_segment import ProDefinedSegment

# Main ramp class
from .piecewise_ramp import PiecewiseRamp

# Config dataclasses for API transport (backend auto-generates Pydantic models)
from .ramp_config import (
    LinearSegmentConfig,
    CircularSegmentConfig,
    # CubicSpiralZeroK1Config,
    # CubicSpiralZeroZeroConfig,
    # EulerSpiralConfig,
    # ProDefinedSegmentConfig,
    RampSegmentConfig,
    PiecewiseRampConfig,
)
