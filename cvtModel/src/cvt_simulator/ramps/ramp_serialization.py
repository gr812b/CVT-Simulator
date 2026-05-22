"""
Conversion utilities between ramp config dataclasses and RampSegment instances.

This module bridges the gap between configuration (dataclasses for API transport)
and runtime instances (RampSegment subclasses for simulation).
"""

from typing import Type, Callable
from cvt_simulator.ramps.ramp_segment import RampSegment
from cvt_simulator.ramps.linear_segment import LinearSegment
from cvt_simulator.ramps.circular_segment import CircularSegment
from cvt_simulator.ramps.ramp_config import (
    LinearSegmentConfig,
    CircularSegmentConfig,
    RampSegmentConfig,
)

# Registry mapping segment classes to their conversion functions
_TO_CONFIG_REGISTRY: dict[
    Type[RampSegment], Callable[[RampSegment], RampSegmentConfig]
] = {}
_FROM_CONFIG_REGISTRY: dict[Type, Callable[[RampSegmentConfig], RampSegment]] = {}


def _register_segment_conversion(
    segment_class: Type[RampSegment],
    config_class: Type,
    to_config_fn: Callable[[RampSegment], RampSegmentConfig],
    from_config_fn: Callable[[RampSegmentConfig], RampSegment],
):
    """Register conversion functions for a segment type."""
    _TO_CONFIG_REGISTRY[segment_class] = to_config_fn
    _FROM_CONFIG_REGISTRY[config_class] = from_config_fn


# Register LinearSegment conversions
_register_segment_conversion(
    LinearSegment,
    LinearSegmentConfig,
    lambda seg: LinearSegmentConfig(
        length=seg.length,
        angle=seg.angle,
    ),
    lambda cfg: LinearSegment(length=cfg.length, angle=cfg.angle),
)

# Register CircularSegment conversions
_register_segment_conversion(
    CircularSegment,
    CircularSegmentConfig,
    lambda seg: CircularSegmentConfig(
        length=seg.length,
        angle_start=seg.angle_start,
        angle_end=seg.angle_end,
        quadrant=seg.quadrant,
    ),
    lambda cfg: CircularSegment(
        length=cfg.length,
        angle_start=cfg.angle_start,
        angle_end=cfg.angle_end,
        quadrant=cfg.quadrant,
    ),
)


def segment_to_config(segment: RampSegment) -> RampSegmentConfig:
    """
    Convert a RampSegment instance to its config dataclass.

    Args:
        segment: RampSegment instance

    Returns:
        Appropriate config dataclass (LinearSegmentConfig, CircularSegmentConfig)
    """
    converter = _TO_CONFIG_REGISTRY.get(type(segment))
    if converter is None:
        raise ValueError(f"Unknown segment type: {type(segment)}")
    return converter(segment)


def config_to_segment(config: RampSegmentConfig) -> RampSegment:
    """
    Convert a ramp config dataclass to a RampSegment instance.

    Args:
        config: RampSegmentConfig dataclass (LinearSegmentConfig or CircularSegmentConfig)

    Returns:
        RampSegment instance for simulation
    """
    converter = _FROM_CONFIG_REGISTRY.get(type(config))
    if converter is None:
        raise ValueError(f"Unknown config type: {type(config)}")
    return converter(config)
