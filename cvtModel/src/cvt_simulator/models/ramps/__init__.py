# flake8: noqa
# Segment classes for building ramps
from .circular_segment import CircularSegment
from .linear_segment import LinearSegment

# Main ramp class
from .piecewise_ramp import PiecewiseRamp

# Config dataclasses for API transport (backend auto-generates Pydantic models)
from .ramp_config import (
    LinearSegmentConfig,
    CircularSegmentConfig,
    RampSegmentConfig,
    PiecewiseRampConfig,
)
