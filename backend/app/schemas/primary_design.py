"""HTTP schemas for the isolated fixed-pivot primary design tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

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
    max_tip_mass_per_flyweight_kg: float = Field(default=0.650, ge=0.0)


class PackagingZoneRequest(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    subject: Literal["flyweight", "ramp"]
    rule: Literal["forbid", "contain"]
    polygon_m: list[tuple[float, float]] = Field(min_length=3, max_length=128)
    clearance_m: float = Field(default=0.0, ge=0.0)

    @field_validator("polygon_m")
    @classmethod
    def _no_duplicate_closing_vertex(
        cls,
        points: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if len(points) > 3 and points[0] == points[-1]:
            return points[:-1]
        return points


class FixedPivotRampRequest(ApiModel):
    kind: Literal["progressive", "constant"] = "progressive"
    initial_flyweight_angle_deg: float = Field(ge=-30.0, lt=90.0)
    linear_angle_deg: float = Field(gt=0.0, lt=90.0)
    circular_start_angle_deg: float = Field(gt=0.0, lt=90.0)
    circular_end_angle_deg: float = Field(gt=0.0, lt=90.0)
    constant_length_m: float = Field(gt=0.0)
    linear_length_m: float = Field(gt=0.0)
    blend_length_m: float = Field(gt=0.0)
    circular_length_m: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _check_progressive_order(self) -> "FixedPivotRampRequest":
        if (
            self.kind == "progressive"
            and self.circular_start_angle_deg <= self.circular_end_angle_deg
        ):
            raise ValueError(
                "the Q2 circular section requires circular_start_angle_deg > "
                "circular_end_angle_deg"
            )
        return self


class FixedPivotArchitectureAnalyzeRequest(ApiModel):
    architecture: FixedPivotArchitectureRequest
    zones: list[PackagingZoneRequest] = Field(default_factory=list, max_length=32)
    reach_sample_count: int = Field(default=361, ge=91, le=1441)
    shift_sample_count: int = Field(default=41, ge=9, le=161)


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
    packaging_zones: list[dict[str, Any]]
    operating: dict[str, float]
    ui_limits: dict[str, list[float]]


class FixedPivotArchitectureAnalysisResponse(ApiModel):
    architecture: dict[str, Any]
    zones: list[dict[str, Any]]
    validity: dict[str, Any]
    limits: dict[str, float]
    workspace: dict[str, Any]
    slices: dict[str, Any]
    boundaries: dict[str, Any]
    zone_diagnostics: list[dict[str, Any]]
    manipulators: dict[str, float]
    viewport: dict[str, float]
    summary: dict[str, Any]


class FixedPivotConcreteAnalysisResponse(ApiModel):
    analysis_id: str
    validity: dict[str, Any]
    architecture: dict[str, Any]
    ramp: dict[str, Any]
    requested_travel_m: float
    contact_valid_travel_m: float
    geometry: dict[str, Any]
    ramp_surface_open: dict[str, list[float]]
    summary: dict[str, Any]


class FixedPivotOperatingResponse(ApiModel):
    analysis_id: str
    operating: dict[str, float]
    loads: dict[str, Any]
