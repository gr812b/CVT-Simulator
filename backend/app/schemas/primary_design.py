"""HTTP schemas for the isolated fixed-pivot primary design tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .common import ApiModel


class FixedPivotArchitectureRequest(ApiModel):
    pivot_axial_position_m: float = 0.0
    pivot_radius_m: float = Field(gt=0.0)
    arm_length_m: float = Field(gt=0.0)
    roller_radius_m: float = Field(gt=0.0)
    required_travel_m: float = Field(gt=0.0)
    number_of_flyweights: int = Field(gt=0)
    arm_mass_per_flyweight_kg: float = Field(ge=0.0)
    ramp_axial_direction: Literal[-1, 1] = -1
    roller_side_sign: Literal[-1, 1] = 1


class FixedPivotRampRequest(ApiModel):
    kind: Literal["progressive", "constant"] = "progressive"
    anchor_axial_from_pivot_m: float
    anchor_radial_from_pivot_m: float
    start_angle_deg: float = Field(gt=0.0, lt=90.0)
    end_angle_deg: float = Field(gt=0.0, lt=90.0)
    linear_length_m: float = Field(gt=0.0)
    blend_length_m: float = Field(gt=0.0)
    circular_length_m: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _check_progressive_order(self) -> "FixedPivotRampRequest":
        if self.kind == "progressive" and self.start_angle_deg <= self.end_angle_deg:
            raise ValueError(
                "progressive ramps require start_angle_deg > end_angle_deg; "
                "use kind=constant when the tangents are equal"
            )
        return self


class FixedPivotConcreteAnalyzeRequest(ApiModel):
    architecture: FixedPivotArchitectureRequest
    ramp: FixedPivotRampRequest
    sample_count: int = Field(default=161, ge=41, le=501)


class FixedPivotOperatingRequest(ApiModel):
    analysis_id: str = Field(min_length=1)
    tip_mass_per_flyweight_kg: float = Field(ge=0.0)
    shaft_speed_rad_s: float = Field(ge=0.0)
    shift_speed_m_s: float = 0.0
    shift_acceleration_m_s2: float = 0.0


class FixedPivotDefaultsResponse(ApiModel):
    architecture: dict[str, Any]
    ramp: dict[str, Any]
    operating: dict[str, float]
    ui_limits: dict[str, list[float]]


class FixedPivotConcreteAnalysisResponse(ApiModel):
    analysis_id: str
    validity: dict[str, Any]
    architecture: dict[str, Any]
    ramp: dict[str, Any]
    requested_travel_m: float
    contact_valid_travel_m: float
    geometry: dict[str, Any]
    ramp_surface_open: dict[str, list[float]]
    summary: dict[str, float]


class FixedPivotOperatingResponse(ApiModel):
    analysis_id: str
    operating: dict[str, float]
    loads: dict[str, Any]
