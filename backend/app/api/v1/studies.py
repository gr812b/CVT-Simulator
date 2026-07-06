"""Named engineering studies, not a generic internal-solver endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from app.schemas.studies import (
    ClampingResponseStudyRequest,
    EndpointRadiiGeometryStudyRequest,
    StaticStudyResponse,
    TargetRatiosGeometryStudyRequest,
)

router = APIRouter(prefix="/studies", tags=["studies"])


@router.post("/geometry/endpoint-radii", response_model=StaticStudyResponse)
def geometry_endpoint_radii(
    request: EndpointRadiiGeometryStudyRequest,
    container: ApplicationContainer = Depends(get_container),
) -> StaticStudyResponse:
    try:
        study = container.gateway.geometry_from_endpoint_radii(request.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "geometry_study_invalid", str(error)) from error
    return StaticStudyResponse(study=study)


@router.post("/geometry/target-ratios", response_model=StaticStudyResponse)
def geometry_target_ratios(
    request: TargetRatiosGeometryStudyRequest,
    container: ApplicationContainer = Depends(get_container),
) -> StaticStudyResponse:
    try:
        study = container.gateway.geometry_from_target_ratios(request.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "geometry_study_invalid", str(error)) from error
    return StaticStudyResponse(study=study)


@router.post("/actuation/clamping-response", response_model=StaticStudyResponse)
def clamping_response(
    request: ClampingResponseStudyRequest,
    container: ApplicationContainer = Depends(get_container),
) -> StaticStudyResponse:
    try:
        study = container.gateway.clamping_response(request.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "clamping_study_invalid", str(error)) from error
    return StaticStudyResponse(study=study)
