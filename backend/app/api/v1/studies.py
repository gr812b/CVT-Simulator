"""Named engineering studies, not a generic internal-solver endpoint."""

from __future__ import annotations

from app.api.v1.dependencies import get_container
from app.application import geometry_inputs
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from app.schemas.studies import (
    ClampingResponseStudyRequest,
    EndpointRadiiGeometryStudyRequest,
    GeometryStudyResponse,
    SimpleGeometryRequest,
    SimpleGeometryResponse,
    StaticStudyResponse,
    TargetRatiosGeometryStudyRequest,
)
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/studies", tags=["studies"])
ContainerDep = Depends(get_container)


@router.post("/geometry/endpoint-radii", response_model=GeometryStudyResponse)
def geometry_endpoint_radii(
    request: EndpointRadiiGeometryStudyRequest,
    container: ApplicationContainer = ContainerDep,
) -> GeometryStudyResponse:
    try:
        study = container.gateway.geometry_from_endpoint_radii(request.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "geometry_study_invalid", str(error)) from error
    return GeometryStudyResponse(study=study)


@router.post("/geometry/target-ratios", response_model=GeometryStudyResponse)
def geometry_target_ratios(
    request: TargetRatiosGeometryStudyRequest,
    container: ApplicationContainer = ContainerDep,
) -> GeometryStudyResponse:
    try:
        study = container.gateway.geometry_from_target_ratios(request.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "geometry_study_invalid", str(error)) from error
    return GeometryStudyResponse(study=study)


@router.post("/actuation/clamping-response", response_model=StaticStudyResponse)
def clamping_response(
    request: ClampingResponseStudyRequest,
    container: ApplicationContainer = ContainerDep,
) -> StaticStudyResponse:
    try:
        study = container.gateway.clamping_response(request.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "clamping_study_invalid", str(error)) from error
    return StaticStudyResponse(study=study)


@router.get("/geometry/template", response_model=SimpleGeometryRequest)
def geometry_template():
    return geometry_inputs.template()


@router.post("/geometry/simple", response_model=SimpleGeometryResponse)
def geometry_simple(
    request: SimpleGeometryRequest,
    container: ApplicationContainer = ContainerDep,
):
    resolved = geometry_inputs.resolve(request)
    try:
        study = container.gateway.geometry_from_endpoint_radii(resolved.model_dump())
    except (TypeError, ValueError) as error:
        raise ApiProblem(422, "geometry_study_invalid", str(error)) from error
    scene = container.gateway.scene_preview(
        {
            **resolved.context.model_dump(),
            "primary_outer_radius_at_zero_shift_m": (resolved.primary_outer_radius_at_zero_shift_m),
            "secondary_outer_radius_at_zero_shift_m": (
                resolved.secondary_outer_radius_at_zero_shift_m
            ),
        },
        frame_count=21,
    )
    return SimpleGeometryResponse(study=study, resolved_context=resolved.context, scene=scene)
