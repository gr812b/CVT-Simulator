"""Static-study request envelopes.

These models define public study inputs, not CINDER mechanics classes.  The
single CINDER gateway translates them into CINDER's typed study requests.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import ApiModel, JsonObject


class BeltSectionRequest(ApiModel):
    height_m: float = Field(gt=0.0)
    outer_width_m: float = Field(gt=0.0)
    inner_width_m: float = Field(gt=0.0)
    cord_depth_from_outer_m: float = Field(ge=0.0)


class GeometryDesignContextRequest(ApiModel):
    belt: BeltSectionRequest
    belt_outer_length_m: float = Field(gt=0.0)
    sheave_half_angle_rad: float = Field(gt=0.0, lt=1.5707963267948966)
    deadzone_shift_m: float = Field(ge=0.0)
    max_shift_m: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _check_shift_range(self) -> "GeometryDesignContextRequest":
        if self.max_shift_m < self.deadzone_shift_m:
            raise ValueError("max_shift_m must be greater than or equal to deadzone_shift_m.")
        return self


class GeometryFieldSamplingRequest(ApiModel):
    primary_outer_radius_m: list[float] = Field(min_length=2)
    secondary_outer_radius_m: list[float] = Field(min_length=2)

    @field_validator("primary_outer_radius_m", "secondary_outer_radius_m")
    @classmethod
    def _strictly_increasing_positive(cls, values: list[float]) -> list[float]:
        if any(value <= 0.0 for value in values):
            raise ValueError("radius axes must contain positive values.")
        if any(next_value <= value for value, next_value in zip(values, values[1:])):
            raise ValueError("radius axes must be strictly increasing.")
        return values


class GeometryStudyOptions(ApiModel):
    sample_count: int = Field(default=301, ge=2, le=4001)
    minimum_primary_wrap_angle_rad: float | None = Field(default=None, gt=0.0)
    minimum_secondary_wrap_angle_rad: float | None = Field(default=None, gt=0.0)
    field_sampling: GeometryFieldSamplingRequest | None = None


class EndpointRadiiGeometryStudyRequest(GeometryStudyOptions):
    context: GeometryDesignContextRequest
    primary_outer_radius_at_zero_shift_m: float = Field(gt=0.0)
    secondary_outer_radius_at_zero_shift_m: float = Field(gt=0.0)


class TargetRatiosGeometryStudyRequest(GeometryStudyOptions):
    context: GeometryDesignContextRequest
    maximum_ratio: float = Field(gt=0.0)
    minimum_ratio: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _check_ratio_order(self) -> "TargetRatiosGeometryStudyRequest":
        if self.maximum_ratio <= self.minimum_ratio:
            raise ValueError("maximum_ratio must exceed minimum_ratio.")
        return self


class ClosureUnknownValuesRequest(ApiModel):
    primary_angular_acceleration_rad_per_s2: float = 0.0
    secondary_angular_acceleration_rad_per_s2: float = 0.0
    belt_acceleration_m_per_s2: float = 0.0
    shift_acceleration_m_per_s2: float = 0.0
    primary_torque_Nm: float = 0.0
    secondary_torque_Nm: float = 0.0
    primary_normal_resultant_N: float = 0.0
    secondary_normal_resultant_N: float = 0.0


ActuationCoordinate = Literal[
    "shift_position",
    "shaft_speed",
    "shift_speed",
    "primary_angular_acceleration",
    "secondary_angular_acceleration",
    "belt_acceleration",
    "shift_acceleration",
    "primary_torque",
    "secondary_torque",
    "primary_normal_resultant",
    "secondary_normal_resultant",
]


class ActuationAxisRequest(ApiModel):
    coordinate: ActuationCoordinate
    values: list[float] = Field(min_length=1, max_length=1001)


class ClampingResponseStudyRequest(ApiModel):
    assembly_document: JsonObject
    pulley: Literal["input", "output"]
    shift_position_m: float = Field(ge=0.0)
    shaft_speed_rad_per_s: float = 0.0
    shift_speed_m_per_s: float = 0.0
    closure_unknowns: ClosureUnknownValuesRequest = Field(
        default_factory=ClosureUnknownValuesRequest
    )
    axes: list[ActuationAxisRequest] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def _check_axis_coordinates(self) -> "ClampingResponseStudyRequest":
        coordinates = [axis.coordinate for axis in self.axes]
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("each actuation axis must use a distinct coordinate.")
        return self


class StaticStudyResponse(ApiModel):
    study: JsonObject
