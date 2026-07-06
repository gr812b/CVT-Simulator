"""Transport-only Pydantic schemas shared across feature routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

JsonObject = dict[str, Any]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: str = "ok"
    api_version: str = "v1"


class ErrorBody(ApiModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(ApiModel):
    error: ErrorBody


class TimestampedStatus(ApiModel):
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ContractDocumentResponse(ApiModel):
    """A public CINDER metadata document retained as generic JSON on purpose.

    The detailed type is generated from CINDER's JSON Schema by frontend build
    tooling. The FastAPI envelope remains explicitly typed without mirroring
    CINDER's internals in Pydantic.
    """

    document: JsonObject


class FindingsResponse(ApiModel):
    validation: JsonObject
