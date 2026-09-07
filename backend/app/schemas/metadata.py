"""Metadata endpoint transport envelopes."""

from __future__ import annotations

from .common import ApiModel, ContractDocumentResponse


class ConventionsResponse(ContractDocumentResponse):
    pass


class ComponentCatalogResponse(ContractDocumentResponse):
    pass


class EditorSchemaResponse(ContractDocumentResponse):
    pass


class SimulationCaseJsonSchemaResponse(ContractDocumentResponse):
    pass


class CinderRuntimeResponse(ApiModel):
    package: str
    package_version: str
    simulation_case_schema_version: int
    simulation_result_contract_version: int
