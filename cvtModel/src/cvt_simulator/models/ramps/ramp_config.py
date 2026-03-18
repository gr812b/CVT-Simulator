"""
Dataclass definitions for ramp segment configurations.

These dataclasses define the structure for serializing/deserializing ramp
configurations. The backend will automatically generate Pydantic models from these
using auto_model.py.
"""

from dataclasses import dataclass, field
from typing import List, Union, Literal
from enum import Enum


def _coerce_float(value, field_name: str) -> float:
    """Parse numeric payload values to float with clear errors."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid value for {field_name}: {value!r}") from exc


def _coerce_quadrant(value) -> int:
    """Parse and validate circular-segment quadrant from payload values."""
    if isinstance(value, bool):
        raise ValueError(f"Invalid value for quadrant: {value!r}")

    # Accept common frontend forms like "2" or 2.0
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            raise ValueError("Invalid value for quadrant: empty string")

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid value for quadrant: {value!r}") from exc

    if not numeric.is_integer():
        raise ValueError(f"Invalid value for quadrant: {value!r}")

    quadrant = int(numeric)
    if quadrant not in {1, 2, 3, 4}:
        raise ValueError(f"quadrant must be 1, 2, 3, or 4 (got {quadrant})")
    return quadrant


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

            # Normalize payload numerics from UI/forms before dataclass construction.
            if config_class is LinearSegmentConfig:
                seg_dict_copy["length"] = _coerce_float(
                    seg_dict_copy.get("length"), "length"
                )
                seg_dict_copy["angle"] = _coerce_float(
                    seg_dict_copy.get("angle"), "angle"
                )
            elif config_class is CircularSegmentConfig:
                seg_dict_copy["length"] = _coerce_float(
                    seg_dict_copy.get("length"), "length"
                )
                seg_dict_copy["angle_start"] = _coerce_float(
                    seg_dict_copy.get("angle_start"), "angle_start"
                )
                seg_dict_copy["angle_end"] = _coerce_float(
                    seg_dict_copy.get("angle_end"), "angle_end"
                )
                if "quadrant" in seg_dict_copy:
                    seg_dict_copy["quadrant"] = _coerce_quadrant(
                        seg_dict_copy.get("quadrant")
                    )

            segments.append(config_class(**seg_dict_copy))

        return cls(segments=segments)
