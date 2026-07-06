"""Metadata endpoint transport envelopes."""

from __future__ import annotations

from .common import ContractDocumentResponse


class ConventionsResponse(ContractDocumentResponse):
    pass


class ComponentCatalogResponse(ContractDocumentResponse):
    pass


class EditorSchemaResponse(ContractDocumentResponse):
    pass


class SimulationCaseJsonSchemaResponse(ContractDocumentResponse):
    pass
