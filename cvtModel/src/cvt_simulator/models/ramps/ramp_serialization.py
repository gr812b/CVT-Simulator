"""
Conversion utilities between ramp config dataclasses and RampSegment instances.

This module bridges the gap between configuration (dataclasses for API transport)
and runtime instances (RampSegment subclasses for simulation).
"""

import math
from typing import Type, Callable
from cvt_simulator.models.ramps.ramp_segment import RampSegment
from cvt_simulator.models.ramps.linear_segment import LinearSegment
from cvt_simulator.models.ramps.circular_segment import CircularSegment
from cvt_simulator.models.ramps.cubic_spiral_zero_k1 import CubicSpiralZeroK1
from cvt_simulator.models.ramps.cubic_spiral_zero_zero import CubicSpiralZeroZero
from cvt_simulator.models.ramps.euler_spiral_segment import EulerSpiralSegment
from cvt_simulator.models.ramps.pro_defined_segment import ProDefinedSegment
from cvt_simulator.models.ramps.ramp_config import (
    LinearSegmentConfig,
    CircularSegmentConfig,
    CubicSpiralZeroK1Config,
    CubicSpiralZeroZeroConfig,
    EulerSpiralConfig,
    ProDefinedSegmentConfig,
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
        length=seg.x_end - seg.x_start,
        slope=seg.m,
    ),
    lambda cfg: LinearSegment(
        x_start=0, x_end=cfg.length, slope=cfg.slope  # Will be set during ramp assembly
    ),
)

# Register CircularSegment conversions
_register_segment_conversion(
    CircularSegment,
    CircularSegmentConfig,
    lambda seg: CircularSegmentConfig(
        length=seg.x_end - seg.x_start,
        radius=seg.radius,
        # CircularSegment stores transformed values (π + original), so subtract π to get original
        theta_start=seg.theta_start - math.pi,
        theta_end=seg.theta_end - math.pi,
    ),
    lambda cfg: CircularSegment(
        x_start=0,  # Will be set during ramp assembly
        x_end=cfg.length,
        radius=cfg.radius,
        theta_start=cfg.theta_start,
        theta_end=cfg.theta_end,
    ),
)

# Register CubicSpiralZeroK1 conversions
_register_segment_conversion(
    CubicSpiralZeroK1,
    CubicSpiralZeroK1Config,
    lambda seg: CubicSpiralZeroK1Config(
        length=seg.x_end - seg.x_start,
        slope_start=seg.theta0,
        slope_end=seg.theta1,
        target_curvature=seg.k1,
    ),
    lambda cfg: CubicSpiralZeroK1(
        x_start=0,  # Will be set during ramp assembly
        x_end=cfg.length,
        slope_start=math.tan(cfg.slope_start),
        slope_end=math.tan(cfg.slope_end),
        target_curvature=cfg.target_curvature,
    ),
)

# Register CubicSpiralZeroZero conversions
_register_segment_conversion(
    CubicSpiralZeroZero,
    CubicSpiralZeroZeroConfig,
    lambda seg: CubicSpiralZeroZeroConfig(
        length=seg.x_end - seg.x_start,
        slope_start=seg.theta0,
        slope_end=seg.theta1,
    ),
    lambda cfg: CubicSpiralZeroZero(
        x_start=0,  # Will be set during ramp assembly
        x_end=cfg.length,
        slope_start=math.tan(cfg.slope_start),
        slope_end=math.tan(cfg.slope_end),
    ),
)

# Register EulerSpiralSegment conversions
_register_segment_conversion(
    EulerSpiralSegment,
    EulerSpiralConfig,
    lambda seg: EulerSpiralConfig(
        length=seg.x_end - seg.x_start,
        slope_start=seg.theta_start,
        slope_end=seg.theta_end,
    ),
    lambda cfg: EulerSpiralSegment(
        x_start=0,  # Will be set during ramp assembly
        x_end=cfg.length,
        slope_start=math.tan(cfg.slope_start),
        slope_end=math.tan(cfg.slope_end),
    ),
)

# Register ProDefinedSegment conversions
_register_segment_conversion(
    ProDefinedSegment,
    ProDefinedSegmentConfig,
    lambda seg: ProDefinedSegmentConfig(
        length=seg.x_end - seg.x_start,
        prev_seg_height=seg.y_start if seg.y_start is not None else 0,
        end_length=seg.end_length,
        initial_slope=seg.f_prime(-seg.x_offset),
        r_initial=seg.r_initial,
    ),
    lambda cfg: ProDefinedSegment(
        x_start=0,  # Will be set during ramp assembly
        x_end=cfg.length,
        prev_seg_height=cfg.prev_seg_height,
        end_length=cfg.end_length,
        initial_slope=cfg.initial_slope,
        r_initial=cfg.r_initial,
    ),
)


def segment_to_config(segment: RampSegment) -> RampSegmentConfig:
    """
    Convert a RampSegment instance to its config dataclass.

    Args:
        segment: RampSegment instance

    Returns:
        Appropriate config dataclass (LinearSegmentConfig, etc.)
    """
    converter = _TO_CONFIG_REGISTRY.get(type(segment))
    if converter is None:
        raise ValueError(f"Unknown segment type: {type(segment)}")
    return converter(segment)


def config_to_segment(config: RampSegmentConfig) -> RampSegment:
    """
    Convert a ramp config dataclass to a RampSegment instance.

    Args:
        config: RampSegmentConfig dataclass (union of all segment config types)

    Returns:
        RampSegment instance for simulation
    """
    converter = _FROM_CONFIG_REGISTRY.get(type(config))
    if converter is None:
        raise ValueError(f"Unknown config type: {type(config)}")
    return converter(config)
