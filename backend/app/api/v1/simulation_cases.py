"""Validation for complete versioned CINDER simulation documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.schemas.simulation_cases import (
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
