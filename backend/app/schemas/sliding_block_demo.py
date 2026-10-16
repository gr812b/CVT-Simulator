"""Read-only geometry and CINDER poses for the sliding-block sample."""

from math import atan, pi
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Point = tuple[float, float]  # radial, axial, metres
Feature = Literal["block", "cup", "ramp", "assembly"]
InputKey = Literal[
    "block_span_m",
    "block_thickness_m",
    "block_cup_radius_m",
    "block_width_m",
    "cup_radius_m",
    "cup_backing_m",
    "ramp_angle_rad",
    "travel_m",
]


def dimension(default, title, description, feature, *, unit="m", **limits):
    return Field(
        default=default,
        title=title,
        description=description,
        json_schema_extra={"feature": feature, "unit": unit},
        **limits
    )


class SlidingBlockDemoInputs(BaseModel):
    """Bounded dimensions for this synthetic template; all values are SI."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        json_schema_serialization_defaults_required=True,
    )

    block_span_m: float = dimension(
        0.020,
        "Block radial span",
        "End-to-end radial size of the block.",
        "block",
        ge=0.002,
        le=0.040,
    )
    block_thickness_m: float = dimension(
        0.040,
        "Block datum thickness",
        "Axial thickness at the block's radial datum. Increasing it separates the cup and ramp.",
        "block",
        ge=0.002,
        le=0.080,
    )
    block_cup_radius_m: float = dimension(
        0.020,
        "Rounded face radius",
        "Radius of the block face against the cup. Its centre follows this template's radial span.",
        "block",
        ge=0.002,
        le=0.200,
    )
    block_width_m: float = dimension(
        0.024,
        "Block tangential width",
        "Extrusion width perpendicular to this section. Uniform steel defines the mass.",
        "block",
        ge=0.001,
        le=0.050,
    )
    cup_radius_m: float = dimension(
        0.125,
        "Cup contact radius",
        "Radius of the cup's contact arc. Must exceed 105 mm to cover this template's radial extent.",
        "cup",
        gt=0.105,
        le=0.250,
    )
    cup_backing_m: float = dimension(
        0.0035,
        "Cup backing thickness",
        "Axial backing behind the cup track. This changes CVT material, not weight mass.",
        "cup",
        ge=0.0005,
        le=0.010,
    )
    ramp_angle_rad: float = dimension(
        atan(0.5),
        "Shared ramp angle",
        "Angle from the radial direction. The block face stays parallel to the ramp.",
        "ramp",
        unit="rad",
        ge=0,
        le=85 * pi / 180,
    )
    travel_m: float = dimension(
        0.015,
        "Sheave stroke",
        "Positive axial travel from the open reference pose. Contact must remain supported over the full stroke.",
        "assembly",
        ge=0.001,
        le=0.030,
    )


class SlidingBlockDemoField(BaseModel):
    key: InputKey
    label: str
    description: str
    feature: Feature
    unit: str
    minimum: float | None
    maximum: float | None


class SlidingBlockFinding(BaseModel):
    code: str
    field: InputKey | None = None
    message: str


class SlidingBlockDimension(BaseModel):
    key: InputKey
    feature: Feature
    attachment: Literal["fixed", "block", "moving"]
    points_m: tuple[Point, Point]


class SlidingBlockDemoFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    closure_m: float
    datum_m: Point
    com_m: Point
    fixed_contact_m: Point
    # Entire conformal face, not a uniquely located pressure resultant.
    moving_contact_span_m: tuple[Point, Point]
    fixed_normal: Point
    moving_normal: Point
    fixed_reaction_N: float
    moving_reaction_N: float
    closing_force_N: float
    belt_section_m: list[Point]
    interference_pairs: list[Literal["cup_moving", "cup_fixed", "moving_fixed"]]


class SlidingBlockDemoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: str
    cinder_version: str
    name: str
    description: str
    simulation_ready: bool
    inputs: SlidingBlockDemoInputs
    fields: list[SlidingBlockDemoField]
    dimensions: list[SlidingBlockDimension]
    findings: list[SlidingBlockFinding]
    minimum_hardware_clearance_m: float
    cup_touching_thickness_m: float
    rpm: float
    travel_m: float
    total_mass_kg: float
    block_count: int
    block_width_m: float
    block_outline_m: list[Point]
    cup_section_m: list[Point]
    cup_track_m: list[Point]
    moving_section_m: list[Point]
    moving_track_m: list[Point]
    fixed_section_m: list[Point]
    shaft_radius_m: float
    shaft_limits_m: Point  # axial endpoints, metres
    frames: list[SlidingBlockDemoFrame]


class SlidingBlockPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, le=2**31 - 1)
    inputs: SlidingBlockDemoInputs


class SlidingBlockPreviewResponse(BaseModel):
    revision: int
    preview: SlidingBlockDemoResponse | None
    findings: list[SlidingBlockFinding]
