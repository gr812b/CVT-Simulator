from dataclasses import dataclass, fields, replace, field, is_dataclass
from typing import Any, Mapping, Union, get_args, get_origin
from cvt_simulator.ramps.ramp_config import (
    PiecewiseRampConfig,
    LinearSegmentConfig,
    CircularSegmentConfig,
)
from cvt_simulator.utils.conversions import inch_to_meter
from cvt_simulator.constants.car_specs import MAX_SHIFT


def _get_default_primary_ramp() -> PiecewiseRampConfig:
    """Factory function for default primary ramp config."""
    # Match frontend default: single circular segment (length in meters)
    return PiecewiseRampConfig(
        segments=[
            CircularSegmentConfig(
                length=0.024,
                angle_start=40.0,
                angle_end=15.0,
                quadrant=2,
            ),
        ]
    )


def _get_default_secondary_ramp() -> PiecewiseRampConfig:
    """Factory function for default secondary ramp config."""
    # Match frontend default: linear segment (length unit taken from frontend)
    return PiecewiseRampConfig(segments=[LinearSegmentConfig(length=1.0, angle=50.0)])


@dataclass(slots=True)
class SimulationArgs:
    flyweight_mass: float = 0.5  # kg
    primary_ramp_config: PiecewiseRampConfig = field(
        default_factory=_get_default_primary_ramp
    )
    primary_spring_rate: float = 12784.0  # N/m
    primary_spring_pretension: float = 0.1  # m
    secondary_ramp_config: PiecewiseRampConfig = field(
        default_factory=_get_default_secondary_ramp
    )
    secondary_torsion_spring_rate: float = 3.476  # Nm/rad
    secondary_compression_spring_rate: float = 3532.0  # N/m
    secondary_rotational_spring_pretension: float = 200.0  # degrees
    secondary_linear_spring_pretension: float = 0.1  # m
    vehicle_weight: float = 225.0  # kg
    driver_weight: float = 75.0  # kg
    traction: float = 100.0  # percentage
    angle_of_incline: float = 0.0  # degrees
    total_distance: float = 200.0  # meters

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SimulationArgs":
        """
        Merge a (possibly partial) dict with dataclass defaults.
        Accepts keys with '-' or '_' (e.g., 'vehicle-weight' or 'vehicle_weight').
        Ignores unknown keys.
        Automatically converts nested dict values to dataclass objects if the field type
        is a dataclass with a from_dict method.
        """
        allowed = {f.name: f for f in fields(cls)}
        overrides = {}
        for k, v in data.items():
            key = k.replace("-", "_")
            if key in allowed and v is not None:
                field_type = allowed[key].type
                # Handle Optional/Union types by extracting the actual type
                origin = get_origin(field_type)
                if origin is Union:
                    # Extract non-None types from Union
                    types = [t for t in get_args(field_type) if t is not type(None)]
                    if types:
                        field_type = types[0]
                # If the value is a dict and the field type is a dataclass with from_dict
                if (
                    isinstance(v, dict)
                    and is_dataclass(field_type)
                    and hasattr(field_type, "from_dict")
                ):
                    overrides[key] = field_type.from_dict(v)
                else:
                    overrides[key] = v
        return replace(cls(), **overrides)
