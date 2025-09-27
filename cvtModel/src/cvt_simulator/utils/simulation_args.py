from dataclasses import dataclass

from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

@dataclass(slots=True)
class SimulationArgs:
    flyweight_mass: float = 0.8 # kg
    primary_ramp_geometry: float = 1.0 # unitless
    primary_spring_rate: float = 1000.0 # N/m
    primary_spring_pretension: float = 0.0 # m
    secondary_helix_geometry: float = 1.0 # unitless
    secondary_torsion_spring_rate: float = 30.0 # Nm/rad
    secondary_compression_spring_rate: float = 1.0 # N/m
    secondary_rotational_spring_pretension: float = 45.0 # degrees
    secondary_linear_spring_pretension: float = 0.1 # m
    vehicle_weight: float = 225.0 # kg
    driver_weight: float = 75.0 # kg
    traction: float = 100.0 # percentage
    angle_of_incline: float = 0.0 # degrees
    total_distance: float = 200.0 # meters

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SimulationArgs":
        """
        Merge a (possibly partial) dict with dataclass defaults.
        Accepts keys with '-' or '_' (e.g., 'vehicle-weight' or 'vehicle_weight').
        Ignores unknown keys.
        """
        allowed = {f.name: f for f in fields(cls)}
        overrides = {}
        for k, v in data.items():
            key = k.replace("-", "_")
            if key in allowed and v is not None:
                overrides[key] = v
        return replace(cls(), **overrides)
    