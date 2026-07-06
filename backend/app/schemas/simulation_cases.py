"""Full-document validation transport schemas."""

from __future__ import annotations

from .common import ApiModel, JsonObject


class SimulationCaseDocumentRequest(ApiModel):
    simulation_case: JsonObject


class SimulationCaseValidationResponse(ApiModel):
    validation: JsonObject
