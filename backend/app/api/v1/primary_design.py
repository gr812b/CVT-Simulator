"""HTTP adapter for the fixed-pivot primary engineering design tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from app.engineering.fixed_pivot_primary import (
    ArchitectureDesign,
    OperatingCondition,
    PrimaryDesignError,
    RampDesign,
)
from app.schemas.primary_design import (
    FixedPivotConcreteAnalysisResponse,
    FixedPivotConcreteAnalyzeRequest,
    FixedPivotDefaultsResponse,
    FixedPivotOperatingRequest,
    FixedPivotOperatingResponse,
)

router = APIRouter(
    prefix="/engineering/fixed-pivot-primary",
    tags=["engineering: fixed-pivot primary"],
)


@router.get("/defaults", response_model=FixedPivotDefaultsResponse)
def defaults(
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotDefaultsResponse:
    return FixedPivotDefaultsResponse(**container.primary_design.defaults())


@router.post("/concrete/analyze", response_model=FixedPivotConcreteAnalysisResponse)
def analyze_concrete(
    request: FixedPivotConcreteAnalyzeRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotConcreteAnalysisResponse:
    architecture = ArchitectureDesign(**request.architecture.model_dump())
    ramp = RampDesign(**request.ramp.model_dump())
    try:
        result = container.primary_design.analyze_concrete(
            architecture=architecture,
            ramp=ramp,
            sample_count=request.sample_count,
        )
    except PrimaryDesignError as error:
        raise ApiProblem(422, error.code.lower(), str(error), error.details) from error
    return FixedPivotConcreteAnalysisResponse(**result)


@router.post("/concrete/response", response_model=FixedPivotOperatingResponse)
def concrete_response(
    request: FixedPivotOperatingRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotOperatingResponse:
    operating = OperatingCondition(
        tip_mass_per_flyweight_kg=request.tip_mass_per_flyweight_kg,
        shaft_speed_rad_s=request.shaft_speed_rad_s,
        shift_speed_m_s=request.shift_speed_m_s,
        shift_acceleration_m_s2=request.shift_acceleration_m_s2,
    )
    try:
        result = container.primary_design.evaluate_concrete_response(
            analysis_id=request.analysis_id,
            operating=operating,
        )
    except PrimaryDesignError as error:
        status = 404 if error.code == "ANALYSIS_EXPIRED" else 422
        raise ApiProblem(status, error.code.lower(), str(error), error.details) from error
    return FixedPivotOperatingResponse(**result)
