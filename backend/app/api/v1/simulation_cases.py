"""Validation for complete versioned CINDER simulation documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_container, get_database_session
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from app.database.resolver import resolve_simulation_case
from app.schemas.simulation_cases import (
    ResolveLibrarySimulationCaseRequest,
    ResolveLibrarySimulationCaseResponse,
    SimulationCaseDocumentRequest,
    SimulationCaseValidationResponse,
)

router = APIRouter(prefix="/simulation-cases", tags=["simulation cases"])


@router.post("/validate", response_model=SimulationCaseValidationResponse)
def validate_simulation_case(
    request: SimulationCaseDocumentRequest,
    container: ApplicationContainer = Depends(get_container),
) -> SimulationCaseValidationResponse:
    return SimulationCaseValidationResponse(
        validation=container.gateway.validate_simulation_case(request.simulation_case)
    )


@router.post("/resolve-from-library", response_model=ResolveLibrarySimulationCaseResponse)
def resolve_from_library_selection(
    request: ResolveLibrarySimulationCaseRequest,
    session: Session = Depends(get_database_session),
) -> ResolveLibrarySimulationCaseResponse:
    try:
        simulation_case = resolve_simulation_case(
            session,
            vehicle_assembly_version_id=request.vehicle_assembly_version_id,
            tune_id=request.tune_id,
            load_case_id=request.load_case_id,
            execution_preset_id=request.execution_preset_id,
        )
    except ValueError as exc:
        raise ApiProblem(400, "library_run_resolution_failed", str(exc)) from exc
    return ResolveLibrarySimulationCaseResponse(simulation_case=simulation_case)
