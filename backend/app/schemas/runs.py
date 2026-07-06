"""Simulation-run lifecycle transport schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal


from .common import ApiModel, JsonObject

RunStatus = Literal["queued", "validating", "running", "completed", "failed", "timed_out"]


class CreateRunRequest(ApiModel):
    simulation_case: JsonObject
    include_reported_segments: bool = False
    include_raw_trace: bool = False


class RunStatusResponse(ApiModel):
    id: str
    status: RunStatus
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: JsonObject | None = None


class RunResultResponse(ApiModel):
    run: RunStatusResponse
    input_document_snapshot: JsonObject
    result: JsonObject
