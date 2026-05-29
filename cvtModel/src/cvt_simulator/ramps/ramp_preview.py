"""
Utilities for generating preview/analysis data from ramp configurations.
Can be used standalone or integrated into other applications.
"""

from typing import List, Dict, Union
import numpy as np
from cvt_simulator.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.ramps.ramp_config import PiecewiseRampConfig
from cvt_simulator.utils.conversions import inch_to_meter
from cvt_simulator.constants.car_specs import MAX_SHIFT


def generate_ramp_preview(
    ramp: Union[PiecewiseRamp, PiecewiseRampConfig, dict],
    num_points: int = 500,
) -> Dict[str, Union[List[float], float]]:
    """
    Generate preview data for a ramp configuration.

    Args:
        ramp: Can be a PiecewiseRamp, PiecewiseRampConfig, or dict representation
        num_points: Number of sample points to generate (default: 500)

    Returns:
        Dictionary containing:
            - x: List of x positions
            - y: List of heights at each x
            - slopes: List of slopes at each x
            - x_min: Minimum x value
            - x_max: Maximum x value

    Raises:
        ValueError: If ramp has no segments or invalid configuration
    """
    # Convert to PiecewiseRamp if needed
    if isinstance(ramp, dict):
        config = PiecewiseRampConfig.from_dict(ramp)
        ramp_obj = PiecewiseRamp.from_config(config)
    elif isinstance(ramp, PiecewiseRampConfig):
        ramp_obj = PiecewiseRamp.from_config(ramp)
    else:
        ramp_obj = ramp

    if not ramp_obj.segments:
        raise ValueError("Ramp must have at least one segment")

    x_min = ramp_obj.segments[0].x_start
    x_max = ramp_obj.segments[-1].x_end

    # Generate sample points for smooth visualization
    x_points = np.linspace(x_min, x_max, num_points)

    heights: List[float] = []
    slopes: List[float] = []

    for x in x_points:
        try:
            heights.append(float(ramp_obj.height(x)))
            slopes.append(float(ramp_obj.slope(x)))
        except ValueError as e:
            raise ValueError(f"Error calculating ramp at x={x}: {e}") from e

    return {
        "x": x_points.tolist(),
        "y": heights,
        "slopes": slopes,
        "x_min": float(x_min),
        "x_max": float(x_max),
    }


def main():
    """Example usage of ramp preview generation with visualization."""
    import matplotlib.pyplot as plt

    print("=" * 60)
    print("Ramp Preview Generator - Visualization Example")
    print("=" * 60)

    # Secondary Ramp Example
    config = {
        "segments": [
            {
                "type": "linear",
                "length": MAX_SHIFT,
                "angle": -16.699244234,
            },
        ]
    }

    # Create a ramp with linear and circular segments using config format
    # This is the default "Enman" ramp at McMaster baja (updated to positive convention)
    config = {
        "segments": [
            {
                "type": "linear",
                "length": inch_to_meter(0.18126),
                "angle": 25,  # Positive angle from horizontal
            },
            {
                "type": "circular",
                "length": inch_to_meter(1.125 - 0.181226),
                "angle_start": 33.4248111826,  # degrees (steep start)
                "angle_end": 20.8067910127,  # degrees (gentle end)
                "quadrant": 2,  # Mirrored Q3: positive slopes, steep-to-gentle
            },
        ]
    }

    print("\nGenerating preview for Linear + Circular ramp...")
    result = generate_ramp_preview(config, num_points=500)
    print(f"Generated {len(result['x'])} points")
    print(f"Range: x=[{result['x_min']:.2f}, {result['x_max']:.2f}]")
    print(f"Height range: [{min(result['y']):.2f}, {max(result['y']):.2f}]")
    print(f"Slope range: [{min(result['slopes']):.2f}, {max(result['slopes']):.2f}]")

    # Create plots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

    # Plot 1: Height vs X (1:1 aspect ratio)
    ax1.plot(result["x"], result["y"], "b-", linewidth=2)
    ax1.set_xlabel("X Position")
    ax1.set_ylabel("Height")
    ax1.set_title("Ramp Profile: Height vs Position")
    ax1.grid(True, alpha=0.3)
    ax1.set_aspect("equal", adjustable="datalim")

    # Plot 2: Slope vs X
    ax2.plot(result["x"], result["slopes"], "r-", linewidth=2)
    ax2.set_xlabel("X Position")
    ax2.set_ylabel("Slope")
    ax2.set_title("Ramp Profile: Slope vs Position")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    print("\nDisplaying plots...")
    plt.show()

    print("=" * 60)


if __name__ == "__main__":
    main()
