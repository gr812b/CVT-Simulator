"""Metadata endpoint transport envelopes."""

from __future__ import annotations

from .common import ApiModel, ContractDocumentResponse
from .projections import ComponentCatalog, EditorDocument


class ConventionsResponse(ContractDocumentResponse):
    pass


class ComponentCatalogResponse(ApiModel):
    document: ComponentCatalog


class EditorSchemaResponse(ApiModel):
    document: EditorDocument


class SimulationCaseJsonSchemaResponse(ContractDocumentResponse):
    pass


class CinderRuntimeResponse(ApiModel):
    package: str
    package_version: str
    simulation_case_schema_version: int
    simulation_result_contract_version: int
    execution_policy_version: int
    default_secondary_helix_topology: str
