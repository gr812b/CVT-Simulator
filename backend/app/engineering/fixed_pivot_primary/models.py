"""Tool-domain models for the fixed-pivot primary design explorer.

These are deliberately independent of FastAPI/Pydantic and of the frontend.
All dimensions use SI units internally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RampKind = Literal["progressive", "constant"]
PackagingZoneRule = Literal["forbid", "contain"]
PackagingZoneSubject = Literal["flyweight", "ramp"]


@dataclass(frozen=True, slots=True)
class ArchitectureDesign:
    pivot_axial_position_m: float
    pivot_radius_m: float
    arm_length_m: float
    roller_radius_m: float
    required_travel_m: float
    number_of_flyweights: int
    arm_mass_per_flyweight_kg: float
    ramp_axial_direction: int = -1
    roller_side_sign: int = 1
    max_tip_mass_per_flyweight_kg: float = 0.650


@dataclass(frozen=True, slots=True)
class PackagingZone:
    id: str
    label: str
    subject: PackagingZoneSubject
    rule: PackagingZoneRule
    polygon_m: tuple[tuple[float, float], ...]
    clearance_m: float = 0.0


@dataclass(frozen=True, slots=True)
class RampDesign:
    """One concrete physical ramp and its initial assembly angle.

    ``initial_flyweight_angle_deg`` replaces the old arbitrary Point-A axial /
    radial placement.  The CINDER adapter places the ramp so that, at zero
    primary shift, the first point of the physical ramp is tangent to the
    finite roller at this flyweight angle.
    """

    kind: RampKind
    initial_flyweight_angle_deg: float
    linear_angle_deg: float
    circular_start_angle_deg: float
    circular_end_angle_deg: float
    constant_length_m: float
    linear_length_m: float
    blend_length_m: float
    circular_length_m: float

    @property
    def total_length_m(self) -> float:
        if self.kind == "constant":
            return self.constant_length_m
        return self.linear_length_m + self.blend_length_m + self.circular_length_m


@dataclass(frozen=True, slots=True)
class OperatingCondition:
    tip_mass_per_flyweight_kg: float
    shaft_speed_rad_s: float
    shift_speed_m_s: float = 0.0
    shift_acceleration_m_s2: float = 0.0
