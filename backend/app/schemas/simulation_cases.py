"""Full-document validation transport schemas."""

from __future__ import annotations

from .common import ApiModel, JsonObject


class SimulationCaseDocumentRequest(ApiModel):
    simulation_case: JsonObject


class ResolveLibrarySimulationCaseRequest(ApiModel):
    vehicle_assembly_version_id: str
    tune_id: str | None = None
    load_case_id: str | None = None
    execution_preset_id: str | None = None


class ResolveLibrarySimulationCaseResponse(ApiModel):
    simulation_case: JsonObject


class SimulationCaseValidationResponse(ApiModel):
    validation: JsonObject
