"""Transport schemas for the experimental-validation workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .common import ApiModel, JsonObject


class ValidationWorkspaceResponse(ApiModel):
    id: str
    account_id: str
    setup_document: JsonObject
    metrology: JsonObject
    controller_templates: list[JsonObject]
    workflow_defaults: JsonObject
    updated_at: datetime


class ValidationWorkspaceUpdate(ApiModel):
    account_id: str
    setup_document: JsonObject
    metrology: JsonObject = Field(default_factory=dict)
    controller_templates: list[JsonObject] = Field(default_factory=list)
    workflow_defaults: JsonObject = Field(default_factory=dict)


class ValidationRunCreate(ApiModel):
    account_id: str
    source_filename: str
    raw_csv: str
    crop_start_s: float
    crop_end_s: float
    channel_config: JsonObject
    initial_state_config: JsonObject
    workspace_snapshot: JsonObject
    resolved_document: JsonObject
    simulation_run_id: str | None = None
    result_snapshot: JsonObject
    metrics: JsonObject = Field(default_factory=dict)


class ValidationRunResponse(ValidationRunCreate):
    id: str
    created_at: datetime
