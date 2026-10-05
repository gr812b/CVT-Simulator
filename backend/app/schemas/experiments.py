"""Typed experiment intent; CINDER continues to own executable mechanics."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, WithJsonSchema, model_validator

from app.application.cinder_gateway import CinderGateway
from app.schemas.common import ApiModel, JsonObject
from app.schemas.physical_library import PhysicalDifference, PhysicalField
from app.schemas.projections import CaseValidation


class ExperimentModel(ApiModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=True
    )


Name = Annotated[str, Field(min_length=1, max_length=240)]
Positive = Annotated[float, Field(gt=0)]
CinderRamp = Annotated[
    JsonObject,
    WithJsonSchema(
        CinderGateway().inline_assembly_json_schema("assemblyPiecewiseRamp")
    ),
]
TuneValues = dict[str, float | CinderRamp]
ExperimentKind = Literal["tunes", "scenarios"]


class RoadPoint(ExperimentModel):
    distance_m: float = Field(ge=0)
    elevation_m: float


class RoadFeatureBase(ExperimentModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=120)


class FlatFeature(RoadFeatureBase):
    kind: Literal["flat"]
    length_m: Positive


class SlopeFeature(RoadFeatureBase):
    kind: Literal["slope"]
    length_m: Positive
    angle_rad: float = Field(gt=-1.5707963267948966, lt=1.5707963267948966)


class BumpFeature(RoadFeatureBase):
    kind: Literal["crest", "dip"]
    length_m: Positive
    height_m: Positive
    shape: Literal["rounded", "triangular"] = "rounded"


class WhoopsFeature(RoadFeatureBase):
    kind: Literal["whoops"]
    height_m: Positive
    spacing_m: Positive
    count: int = Field(ge=1, le=32)
    shape: Literal["rounded", "triangular"] = "rounded"


class PointsFeature(RoadFeatureBase):
    kind: Literal["points"]
    points: list[RoadPoint] = Field(min_length=2, max_length=512)

    @model_validator(mode="after")
    def ordered_points(self):
        if self.points[0].distance_m != 0 or self.points[0].elevation_m != 0:
            raise ValueError(
                "Each section starts at local distance 0 and relative elevation 0."
            )
        if any(
            b.distance_m <= a.distance_m for a, b in zip(self.points, self.points[1:])
        ):
            raise ValueError("Point distances must increase strictly within a section.")
        return self


RoadFeature = Annotated[
    FlatFeature | SlopeFeature | BumpFeature | WhoopsFeature | PointsFeature,
    Field(discriminator="kind"),
]


class SpatialRoad(ExperimentModel):
    kind: Literal["spatial_road"] = "spatial_road"
    features: list[RoadFeature] = Field(min_length=1, max_length=64)
    endpoint: Literal["flat", "continue_grade"] = "flat"

    @model_validator(mode="after")
    def distinct_features(self):
        if len({feature.id for feature in self.features}) != len(self.features):
            raise ValueError("Road sections must have distinct identifiers.")
        return self


class InitialConditions(ExperimentModel):
    primary_angular_speed_rad_per_s: float = Field(
        default=188.49555921538757, ge=0, le=2000
    )
    secondary_angular_speed_rad_per_s: float = Field(default=0, ge=-2000, le=2000)
    belt_speed_m_per_s: float = Field(default=0, ge=-100, le=100)
    shift_position_m: float = Field(default=0, ge=0, le=1)
    shift_speed_m_per_s: float = Field(default=0, ge=-10, le=10)
    vehicle_distance_m: float = Field(default=0, ge=0)


class ExecutionControls(ExperimentModel):
    relative_tolerance: float = Field(default=1e-4, ge=1e-8, le=0.1)
    absolute_tolerance: float = Field(default=1e-7, ge=1e-12, le=0.01)
    maximum_step_s: float = Field(default=0.02, ge=1e-5, le=1)
    reporting_step_s: float = Field(default=0.01, ge=0.0001, le=1)
    maximum_transitions: int = Field(default=200, ge=1, le=2000)


class CourseStops(ExperimentModel):
    mode: Literal["course", "timed"] = "course"
    rollback_m: Positive | None = 5
    no_progress_s: Positive | None = 5


class ScenarioDocument(ExperimentModel):
    kind: Literal["scenarios"]
    name: Name
    notes: str = Field(default="", max_length=4000)
    road: SpatialRoad
    duration_s: Positive = 180
    stops: CourseStops = Field(default_factory=CourseStops)
    initial: InitialConditions = Field(default_factory=InitialConditions)
    execution: ExecutionControls = Field(default_factory=ExecutionControls)


class TuneDocument(ExperimentModel):
    kind: Literal["tunes"]
    name: Name
    notes: str = Field(default="", max_length=4000)
    setup_revision_id: str
    values: TuneValues = Field(default_factory=dict)


ExperimentDocument = Annotated[
    TuneDocument | ScenarioDocument, Field(discriminator="kind")
]


class ResolvedRoadSegment(ExperimentModel):
    start_distance_m: float
    grade_angle_rad: float


class ResolvedRoadProfile(ExperimentModel):
    kind: Literal["piecewise_constant_grade"] = "piecewise_constant_grade"
    segments: list[ResolvedRoadSegment]


class ResolvedRoadSection(ExperimentModel):
    feature_id: str
    start_distance_m: float
    start_elevation_m: float
    points: list[RoadPoint]


class RoadResolution(ExperimentModel):
    profile: ResolvedRoadProfile
    points: list[RoadPoint]
    sections: list[ResolvedRoadSection]
    length_m: float
    minimum_elevation_m: float
    maximum_elevation_m: float
    maximum_absolute_grade_rad: float
    warnings: list[str] = Field(default_factory=list)


class ExperimentRevisionInfo(ExperimentModel):
    id: str
    number: int
    name: str
    created_at: datetime
    change_note: str


class ExperimentItem(ExperimentModel):
    author_id: str | None
    author: str
    sample: bool = False
    description: str = ""
    id: str
    kind: ExperimentKind
    name: str
    revision_id: str
    revision_number: int
    updated_at: datetime
    owned: bool
    archived: bool
    setup_object_id: str | None = None
    cvt_object_id: str | None = None
    cvt_revision_id: str | None = None


class ExperimentList(ExperimentModel):
    items: list[ExperimentItem]


class ExperimentDetail(ExperimentModel):
    item: ExperimentItem
    document: ExperimentDocument
    history: list[ExperimentRevisionInfo]


class ExperimentSave(ExperimentModel):
    expected_revision_id: str | None
    document: ExperimentDocument
    change_note: str = Field(default="", max_length=2000)


class ExperimentSaved(ExperimentModel):
    detail: ExperimentDetail
    changed: bool


class ExperimentCompare(ExperimentModel):
    differences: list[PhysicalDifference]


class ExperimentRestore(ExperimentModel):
    expected_revision_id: str
    revision_id: str


class ExperimentArchive(ExperimentModel):
    expected_revision_id: str
    archived: bool


class ExperimentCopy(ExperimentModel):
    revision_id: str
    name: Name | None = None


class ScalarTuneField(ExperimentModel):
    kind: Literal["number"]
    key: str
    label: str
    description: str
    group: str
    unit: str
    display_unit: str
    display_scale: float
    minimum: float | None = None
    maximum: float | None = None
    default: float


class ProfileTuneField(ExperimentModel):
    kind: Literal["ramp"]
    key: str
    label: str
    description: str
    group: str
    default: CinderRamp
    fields: list[PhysicalField]


TuneField = Annotated[ScalarTuneField | ProfileTuneField, Field(discriminator="kind")]


class TuneSurface(ExperimentModel):
    cvt_object_id: str
    cvt_revision_id: str
    template: TuneDocument
    setup_name: str
    setup_revision_number: int
    default_vehicle_mass_kg: float
    fields: list[TuneField]


class ExperimentLimits(ExperimentModel):
    max_duration_s: float
    max_features: int
    max_segments: int
    max_distance_m: float
    max_grade_degrees: float
    max_report_samples: int
    outstanding_runs_per_account: Literal[1] = 1
    wall_timeout_s: float


class ExperimentMetadata(ExperimentModel):
    limits: ExperimentLimits
    scenario_template: ScenarioDocument
    feature_templates: list[RoadFeature]
    conventions: list[str]


class TorquePrimaryBoundary(ExperimentModel):
    kind: Literal["fixed_shaft"] = "fixed_shaft"
    external_torque_Nm: float
    equivalent_inertia_kg_m2: float = Field(ge=0)


class SpeedReferencePoint(ExperimentModel):
    time_s: float = Field(ge=0)
    value: float = Field(ge=0, le=2000)


class SpeedReference(ExperimentModel):
    points: list[SpeedReferencePoint] = Field(min_length=2, max_length=1000)

    @model_validator(mode="after")
    def increasing(self):
        if self.points[0].time_s != 0 or any(
            b.time_s <= a.time_s for a, b in zip(self.points, self.points[1:])
        ):
            raise ValueError(
                "Speed profile must start at zero with strictly increasing times."
            )
        return self


class SpeedPrimaryBoundary(ExperimentModel):
    kind: Literal["speed_replay_shaft"] = "speed_replay_shaft"
    speed_reference: SpeedReference
    tracking_gain_Nm_s_per_rad: float = Field(default=400, gt=0)


PrimaryOverride = Annotated[
    TorquePrimaryBoundary | SpeedPrimaryBoundary, Field(discriminator="kind")
]


class ExperimentSelection(ExperimentModel):
    primary_boundary: PrimaryOverride | None = None
    setup_revision_id: str
    tune_revision_id: str | None = None
    scenario_revision_id: str | None = None
    tune_values: TuneValues | None = None
    scenario: ScenarioDocument | None = None
    vehicle_mass_kg: Positive | None = None


class ExperimentPreview(ExperimentModel):
    validation: CaseValidation
    road: RoadResolution
    simulation_case: JsonObject
    provenance: JsonObject


class SubmitExperiment(ExperimentSelection):
    request_key: str = Field(min_length=16, max_length=64)
    name: Name = "Simulation"
    parent_run_id: str | None = None
