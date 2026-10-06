"""Product result projections. Values always come from the stored solver result."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel, JsonObject
from app.schemas.experiments import ExperimentDetail, ExperimentSelection, TuneSurface
from app.schemas.physical_library import Name, PhysicalItem, PhysicalSelection
from app.schemas.runs import RunStatusResponse


class RunReference(ApiModel):
    kind: Literal["setup", "cvt", "belt", "engine", "tune", "scenario"]
    href: str | None = None
    name: str
    revision_id: str | None = None
    revision_number: int | None = None
    unsaved: bool = False


class ResultMetric(ApiModel):
    key: str
    label: str
    value: float | str | bool | None
    unit: str = ""


class RunHistoryItem(ApiModel):
    run: RunStatusResponse
    references: list[RunReference]
    metrics: list[ResultMetric]


class RunHistoryPage(ApiModel):
    items: list[RunHistoryItem]
    total: int
    offset: int
    limit: int


class ResultAvailability(ApiModel):
    full_result: bool
    preview: bool
    partial: bool
    original_row_count: int | None = None
    full_result_hash: str | None = None


class ResultTransition(ApiModel):
    time_s: float
    events: list[str]
    reason: str
    terminates: bool


class RunInspection(RunHistoryItem):
    owned: bool
    availability: ResultAvailability
    warnings: list[str]
    transitions: list[ResultTransition]
    termination_reason: str | None
    experiment_unavailable_reason: str | None


class ReportSeriesColumn(ApiModel):
    key: str
    label: str
    canonical_unit: str
    dimension: str
    group: str
    description: str = ""
    values: list[float | None]


class RunSeries(ApiModel):
    resolution: Literal["preview", "full"]
    axis_key: str
    original_row_count: int
    row_count: int
    columns: list[ReportSeriesColumn]


class RenameRun(ApiModel):
    name: Name
    expected_name: str


class CopyConfiguration(ApiModel):
    request_key: str = Field(min_length=16, max_length=64)
    name: Name | None = None


class ConfigurationCopyResult(ApiModel):
    item: PhysicalItem
    scenario_id: str | None = None
    source_run_id: str | None = None


class CopyOrigin(ApiModel):
    publication_id: str | None = None
    run_id: str | None = None
    copied_at: datetime


class RunSummaryExport(ApiModel):
    format: Literal["cinder_run_summary_v1"] = "cinder_run_summary_v1"
    run: RunStatusResponse
    references: list[RunReference]
    availability: ResultAvailability
    summary: JsonObject


class RunExperimentDraft(ApiModel):
    source_run_id: str
    selection: ExperimentSelection
    setup: PhysicalSelection
    surface: TuneSurface
    tune: ExperimentDetail | None
    load_case: ExperimentDetail | None
