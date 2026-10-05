"""Simulation-run lifecycle transport schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import ApiModel, ErrorBody, JsonObject
from .course import CourseProfile
from .projections import RunPreview
from .scene import SceneGeometry

RunStatus = Literal[
    "queued", "validating", "running", "completed", "failed", "timed_out", "cancelled"
]
RunSource = Literal["direct", "library", "experiment"]


class CreateRunRequest(ApiModel):
    request_key: str = Field(min_length=16, max_length=64)
    simulation_case: JsonObject
    include_reported_segments: bool = False
    include_raw_trace: bool = False

    @model_validator(mode="before")
    @classmethod
    def accept_frozen_input_envelopes(cls, data: object) -> object:
        """Normalize direct-run inputs from debugging and stored-run endpoints.

        The direct run endpoint's canonical request body is
        ``{"simulation_case": <cinder_simulation_case>}``.  This endpoint is a
        debug/contract endpoint. Product reruns of persisted library runs should
        use ``POST /runs/{run_id}/rerun``.  The extra accepted shapes are kept
        for developer regression checks and manual debugging, not as required
        black-box product behavior.
        """

        if not isinstance(data, dict):
            return data
        if "simulation_case" in data:
            return data

        include_reported_segments = data.get("include_reported_segments", False)
        include_raw_trace = data.get("include_raw_trace", False)

        if "input_document_snapshot" in data:
            return {
                "request_key": data.get("request_key"),
                "simulation_case": data["input_document_snapshot"],
                "include_reported_segments": include_reported_segments,
                "include_raw_trace": include_raw_trace,
            }

        if data.get("document_type") == "cinder_simulation_case":
            return {
                "request_key": data.get("request_key"),
                "simulation_case": {
                    key: value for key, value in data.items() if key != "request_key"
                },
                "include_reported_segments": include_reported_segments,
                "include_raw_trace": include_raw_trace,
            }

        return data


class CreateLibraryRunRequest(ApiModel):
    request_key: str = Field(min_length=16, max_length=64)
    vehicle_assembly_version_id: str
    tune_id: str | None = None
    load_case_id: str | None = None
    execution_preset_id: str | None = None
    include_reported_segments: bool = False
    include_raw_trace: bool = False


class RerunStoredRunRequest(ApiModel):
    request_key: str = Field(min_length=16, max_length=64)
    include_reported_segments: bool = False
    include_raw_trace: bool = False


class RunStatusResponse(ApiModel):
    author_id: str | None
    author: str
    id: str
    status: RunStatus
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: ErrorBody | None = None
    source: RunSource = "direct"
    contract_hash: str | None = None
    cache_entry_id: str | None = None
    cache_hit: bool | None = None
    vehicle_assembly_version_id: str | None = None
    cinder_package_version: str | None = None
    input_schema_version: int | None = None
    result_contract_version: int | None = None
    summary_scalars: JsonObject = Field(default_factory=dict)
    has_result: bool = False
    queue_position: int | None = None
    name: str = "Simulation"
    parent_run_id: str | None = None
    cancel_requested_at: datetime | None = None
    deadline_at: datetime | None = None
    provenance: JsonObject = Field(default_factory=dict)
    runtime_identity: JsonObject = Field(default_factory=dict)


class RunListResponse(ApiModel):
    items: list[RunStatusResponse] = Field(default_factory=list)


class RunResultResponse(ApiModel):
    scene_geometry: SceneGeometry
    course: CourseProfile | None
    run: RunStatusResponse
    input_document_snapshot: JsonObject
    result: JsonObject


class RunInputResponse(ApiModel):
    run: RunStatusResponse
    input_document_snapshot: JsonObject


class RunPreviewResponse(ApiModel):
    run: RunStatusResponse
    preview: RunPreview


class RunNotice(ApiModel):
    id: str
    created_at: datetime
    run: RunStatusResponse


class RunActivity(ApiModel):
    active: RunStatusResponse | None = None
    unread: list[RunNotice]
    unread_count: int
