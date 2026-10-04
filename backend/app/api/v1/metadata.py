"""Read-only public CINDER contract metadata."""

from __future__ import annotations

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.application.editor_metadata import editor_document
from app.schemas.metadata import (
    CinderRuntimeResponse,
    ComponentCatalogResponse,
    ConventionsResponse,
    EditorSchemaResponse,
    SimulationCaseJsonSchemaResponse,
)
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/runtime", response_model=CinderRuntimeResponse)
def runtime(
    container: ApplicationContainer = Depends(get_container),
) -> CinderRuntimeResponse:
    return CinderRuntimeResponse(**container.gateway.runtime_identity())


@router.get("/conventions", response_model=ConventionsResponse)
def conventions(
    container: ApplicationContainer = Depends(get_container),
) -> ConventionsResponse:
    return ConventionsResponse(document=container.gateway.conventions())


@router.get("/catalog", response_model=ComponentCatalogResponse)
def catalog(
    container: ApplicationContainer = Depends(get_container),
) -> ComponentCatalogResponse:
    return ComponentCatalogResponse(document=container.gateway.component_catalog())


@router.get("/editor-schema", response_model=EditorSchemaResponse)
def editor_schema(
    container: ApplicationContainer = Depends(get_container),
) -> EditorSchemaResponse:
    return EditorSchemaResponse(document=editor_document(container.gateway))


@router.get("/simulation-case-schema", response_model=SimulationCaseJsonSchemaResponse)
def simulation_case_schema(
    container: ApplicationContainer = Depends(get_container),
) -> SimulationCaseJsonSchemaResponse:
    return SimulationCaseJsonSchemaResponse(
        document=container.gateway.simulation_case_json_schema()
    )
