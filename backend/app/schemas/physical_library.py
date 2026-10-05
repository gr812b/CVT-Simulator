"""Generated transport contracts for the physical library and working copies.

The assembly schema comes directly from CINDER. The small engine/vehicle
projections describe this product's supported boundary inputs, not new physics.
"""

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, WithJsonSchema, model_validator

from app.application.cinder_gateway import CinderGateway
from app.schemas.common import ApiModel, JsonObject
from app.schemas.projections import CaseValidation

PhysicalKind = Literal["engines", "belts", "cvts", "setups"]
Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
Name = Annotated[str, Field(min_length=1, max_length=240)]
CinderAssembly = Annotated[
    JsonObject,
    WithJsonSchema(CinderGateway().inline_assembly_json_schema()),
    AfterValidator(CinderGateway().validate_assembly_shape),
]


class PhysicalModel(ApiModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=True
    )


class PhysicalMetadata(PhysicalModel):
    name: Name
    description: str = Field(default="", max_length=4000)
    source_label: str = Field(default="", max_length=240)
    source_url: str = Field(default="", max_length=500)
    source_notes: str = Field(default="", max_length=4000)


class EnginePoint(PhysicalModel):
    angular_speed_rad_per_s: Nonnegative
    torque_Nm: float


class EngineData(PhysicalModel):
    kind: Literal["full_throttle_engine"] = "full_throttle_engine"
    points: list[EnginePoint] = Field(min_length=2, max_length=1000)
    equivalent_rotational_inertia_kg_m2: Nonnegative
    low_speed_braking_torque_Nm: float
    low_speed_braking_peak_speed_rad_per_s: Positive
    high_speed_braking_torque_Nm: float
    high_speed_braking_transition_width_rad_per_s: Positive

    @model_validator(mode="after")
    def ordered_curve(self):
        if any(
            b.angular_speed_rad_per_s <= a.angular_speed_rad_per_s
            for a, b in zip(self.points, self.points[1:])
        ):
            raise ValueError(
                "Engine speeds must be strictly increasing; remove duplicate RPM values."
            )
        return self


class BeltSection(PhysicalModel):
    height_m: Positive
    outer_width_m: Positive
    inner_width_m: Positive
    half_angle_rad: float = Field(gt=0, lt=math.pi / 2)

    @model_validator(mode="after")
    def consistent_section(self):
        if self.inner_width_m >= self.outer_width_m:
            raise ValueError("Bottom width must be smaller than top width.")
        expected = math.atan(
            (self.outer_width_m - self.inner_width_m) / (2 * self.height_m)
        )
        if not math.isclose(self.half_angle_rad, expected, rel_tol=1e-8, abs_tol=1e-10):
            raise ValueError(
                "Belt widths, height and half-angle must describe the same section."
            )
        return self


class BeltSectionSolveRequest(PhysicalModel):
    height_m: Positive | None = None
    outer_width_m: Positive | None = None
    inner_width_m: Positive | None = None
    half_angle_rad: float | None = Field(default=None, gt=0, lt=math.pi / 2)

    @model_validator(mode="after")
    def three_dimensions(self):
        if sum(value is not None for value in self.model_dump().values()) != 3:
            raise ValueError(
                "Supply exactly three of top width, bottom width, height and half-angle."
            )
        return self


class BeltData(BeltSection):
    length_reference: Literal["outer"] = "outer"
    outer_length_m: Positive
    cord_depth_from_outer_m: Nonnegative
    density_kg_per_m3: Positive

    @model_validator(mode="after")
    def cord_inside_section(self):
        if self.cord_depth_from_outer_m > self.height_m:
            raise ValueError("Cord depth must lie inside the belt height.")
        return self


class EngineChoice(PhysicalMetadata):
    revision_id: str | None = None
    data: EngineData


class BeltChoice(PhysicalMetadata):
    revision_id: str | None = None
    data: BeltData


class CvtData(PhysicalModel):
    assembly: CinderAssembly
    belt: BeltChoice


class CvtChoice(PhysicalMetadata):
    revision_id: str | None = None
    data: CvtData


class VehicleData(PhysicalModel):
    mass_kg: Positive
    wheel_rotational_inertia_kg_m2: Nonnegative
    reduction_ratio: Positive
    wheel_radius_m: Positive
    direct_secondary_shaft_inertia_kg_m2: Nonnegative
    rolling_resistance_coefficient: Nonnegative
    drag_coefficient: Nonnegative
    frontal_area_m2: Positive
    air_density_kg_per_m3: Positive


class SetupData(PhysicalModel):
    engine: EngineChoice
    cvt: CvtChoice
    vehicle: VehicleData


class EngineDocument(PhysicalMetadata):
    kind: Literal["engines"]
    data: EngineData


class BeltDocument(PhysicalMetadata):
    kind: Literal["belts"]
    data: BeltData


class CvtDocument(PhysicalMetadata):
    kind: Literal["cvts"]
    data: CvtData


class SetupDocument(PhysicalMetadata):
    kind: Literal["setups"]
    data: SetupData


PhysicalDocument = Annotated[
    EngineDocument | BeltDocument | CvtDocument | SetupDocument,
    Field(discriminator="kind"),
]


class PhysicalSaveRequest(PhysicalModel):
    # Required even for a first save. A stale tab must not replace a newer edit.
    expected_revision_id: str | None
    document: PhysicalDocument
    change_note: str = Field(default="", max_length=2000)


class PhysicalValidateRequest(PhysicalModel):
    document: PhysicalDocument


class PhysicalRevision(PhysicalModel):
    id: str
    number: int
    created_at: datetime
    change_note: str
    name: str
    validation_status: str


class ComponentUpdate(PhysicalModel):
    component: Literal["engine", "cvt", "belt"]
    name: str
    current_revision_id: str
    current_number: int
    available_revision_id: str
    available_number: int


class PhysicalItem(PhysicalModel):
    author_id: str | None
    author: str
    sample: bool
    is_default: bool
    id: str
    kind: PhysicalKind
    name: str
    description: str
    source_label: str
    revision_id: str
    revision_number: int
    updated_at: datetime
    owned: bool
    archived: bool
    validation_status: str


class PhysicalListResponse(PhysicalModel):
    items: list[PhysicalItem]


class PhysicalSelection(PhysicalModel):
    item: PhysicalItem
    document: PhysicalDocument


class PhysicalReference(PhysicalModel):
    kind: PhysicalKind
    object_id: str
    revision_id: str
    name: str


class PhysicalDetail(PhysicalSelection):
    references: list[PhysicalReference] = Field(default_factory=list)
    history: list[PhysicalRevision]
    updates: list[ComponentUpdate]
    validation: CaseValidation


class PhysicalSaveResponse(PhysicalModel):
    detail: PhysicalDetail
    changed: bool


class PhysicalRestoreRequest(PhysicalModel):
    expected_revision_id: str
    revision_id: str


class PhysicalCopyRequest(PhysicalModel):
    name: Name | None = None


class PhysicalArchiveRequest(PhysicalModel):
    expected_revision_id: str
    archived: bool


class PhysicalDifference(PhysicalModel):
    path: str
    before: str
    after: str


class PhysicalCompareResponse(PhysicalModel):
    differences: list[PhysicalDifference]


class PhysicalUpdatePreview(PhysicalModel):
    expected_revision_id: str
    document: PhysicalDocument
    differences: list[PhysicalDifference]
    validation: CaseValidation


class PhysicalTemplateResponse(PhysicalModel):
    document: PhysicalDocument


class PhysicalValidationResponse(PhysicalModel):
    validation: CaseValidation
    resolved_simulation_case: JsonObject | None = None


class CurveImportRequest(PhysicalModel):
    text: str = Field(max_length=100000)
    speed_unit: Literal["rpm", "rad/s"] = "rpm"
    torque_unit: Literal["N·m", "lb·ft"] = "N·m"


class CurveImportResponse(PhysicalModel):
    points: list[EnginePoint]


class PhysicalField(PhysicalModel):
    path: str
    label: str
    unit: str
    display_unit: str
    display_scale: float = 1
    description: str = ""
    advanced: bool = False
    minimum: float | None = None
    maximum: float | None = None
    integer: bool = False


class PhysicalMetadataResponse(PhysicalModel):
    cvt_fields: list[PhysicalField]
