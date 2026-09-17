"""HTTP adapter for the fixed-pivot primary engineering design tool."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from app.engineering.fixed_pivot_primary.inverse_design import ForceTargetPoint
from app.engineering.fixed_pivot_primary import (
    ArchitectureDesign,
    ForceRequirement,
    OperatingCondition,
    PackagingZone,
    PrimaryDesignError,
    RampDesign,
)
from app.schemas.primary_design import (
    FixedPivotArchitectureAnalysisResponse,
    FixedPivotArchitectureAnalyzeRequest,
    FixedPivotConcreteAnalysisResponse,
    FixedPivotConcreteAnalyzeRequest,
    FixedPivotDefaultsResponse,
    FixedPivotOperatingRequest,
    FixedPivotOperatingResponse,
    FixedPivotPathDomainRequest,
    FixedPivotPathDomainResponse,
    FixedPivotPathDomainConditionRequest,
    FixedPivotPathDomainConditionResponse,
    FixedPivotInverseDesignRequest,
    FixedPivotInverseDesignResponse,
    FixedPivotPathDomainCompareRequest,
    FixedPivotPathDomainCompareResponse,
    FixedPivotPathDomainCompareTargetRequest,
    FixedPivotPathDomainCompareTargetResponse,
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


@router.post(
    "/architecture/analyze",
    response_model=FixedPivotArchitectureAnalysisResponse,
)
def analyze_architecture(
    request: FixedPivotArchitectureAnalyzeRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotArchitectureAnalysisResponse:
    architecture = ArchitectureDesign(**request.architecture.model_dump())
    zones = tuple(
        PackagingZone(
            **zone.model_dump(exclude={"polygon_m"}),
            polygon_m=tuple(tuple(point) for point in zone.polygon_m),
        )
        for zone in request.zones
    )
    try:
        result = container.primary_design.analyze_architecture(
            architecture=architecture,
            zones=zones,
            reach_sample_count=request.reach_sample_count,
            shift_sample_count=request.shift_sample_count,
        )
    except PrimaryDesignError as error:
        raise ApiProblem(422, error.code.lower(), str(error), error.details) from error
    return FixedPivotArchitectureAnalysisResponse(**result)


@router.post(
    "/architecture/path-domain",
    response_model=FixedPivotPathDomainResponse,
)
def analyze_path_domain(
    request: FixedPivotPathDomainRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotPathDomainResponse:
    architecture = ArchitectureDesign(**request.architecture.model_dump())
    zones = tuple(
        PackagingZone(
            **zone.model_dump(exclude={"polygon_m"}),
            polygon_m=tuple(tuple(point) for point in zone.polygon_m),
        )
        for zone in request.zones
    )
    try:
        result = container.primary_design.analyze_path_domain(
            architecture=architecture,
            zones=zones,
            shift_station_count=request.shift_station_count,
            q_sample_count=request.q_sample_count,
            alpha_sample_count=request.alpha_sample_count,
            representative_path_count=request.representative_path_count,
            edge_audit_sample_count=request.edge_audit_sample_count,
            history_trace_sample_count=request.history_trace_sample_count,
        )
    except PrimaryDesignError as error:
        raise ApiProblem(422, error.code.lower(), str(error), error.details) from error
    return FixedPivotPathDomainResponse(**result)


@router.post(
    "/architecture/path-domain/condition",
    response_model=FixedPivotPathDomainConditionResponse,
)
def condition_path_domain(
    request: FixedPivotPathDomainConditionRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotPathDomainConditionResponse:
    requirements = tuple(
        ForceRequirement(**requirement.model_dump())
        for requirement in request.requirements
    )
    try:
        result = container.primary_design.condition_path_domain(
            domain_id=request.domain_id,
            requirements=requirements,
            max_tip_mass_per_flyweight_kg=request.max_tip_mass_per_flyweight_kg,
            mass_sample_count=request.mass_sample_count,
            representative_solution_count=request.representative_solution_count,
            reference_shaft_speed_rad_s=request.reference_shaft_speed_rad_s,
        )
    except PrimaryDesignError as error:
        status = 404 if error.code == "DOMAIN_EXPIRED" else 422
        raise ApiProblem(status, error.code.lower(), str(error), error.details) from error
    return FixedPivotPathDomainConditionResponse(**result)


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

@router.post("/inverse-design", response_model=FixedPivotInverseDesignResponse)
def inverse_design_force_curve(
    request: FixedPivotInverseDesignRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotInverseDesignResponse:
    architecture = ArchitectureDesign(**request.architecture.model_dump())
    zones = tuple(
        PackagingZone(
            **zone.model_dump(exclude={"polygon_m"}),
            polygon_m=tuple(tuple(point) for point in zone.polygon_m),
        )
        for zone in request.zones
    )
    target_points = tuple(
        ForceTargetPoint(shift_m=point.shift_m, force_N=point.force_N)
        for point in request.target_points
    )
    try:
        result = container.primary_design.inverse_design_force_curve(
            architecture=architecture,
            zones=zones,
            target_points=target_points,
            shaft_speed_rad_s=request.shaft_speed_rad_s,
            max_tip_mass_per_flyweight_kg=request.max_tip_mass_per_flyweight_kg,
            fixed_tip_mass_per_flyweight_kg=request.fixed_tip_mass_per_flyweight_kg,
            solution_count=request.solution_count,
            sample_count=request.sample_count,
        )
    except PrimaryDesignError as error:
        raise ApiProblem(422, error.code.lower(), str(error), error.details) from error
    return FixedPivotInverseDesignResponse(**result)


@router.post(
    "/architecture/path-domain/compare",
    response_model=FixedPivotPathDomainCompareResponse,
)
def compare_path_domains(
    request: FixedPivotPathDomainCompareRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotPathDomainCompareResponse:
    try:
        result = container.primary_design.compare_path_domains(
            domain_id_a=request.domain_id_a,
            domain_id_b=request.domain_id_b,
            atlas_path_count=request.atlas_path_count,
            mass_mix_count=request.mass_mix_count,
        )
    except PrimaryDesignError as error:
        status = 404 if error.code == "DOMAIN_EXPIRED" else 422
        raise ApiProblem(status, error.code.lower(), str(error), error.details) from error
    return FixedPivotPathDomainCompareResponse(**result)

@router.post(
    "/architecture/path-domain/compare-target",
    response_model=FixedPivotPathDomainCompareTargetResponse,
)
def compare_path_domains_to_target(
    request: FixedPivotPathDomainCompareTargetRequest,
    container: ApplicationContainer = Depends(get_container),
) -> FixedPivotPathDomainCompareTargetResponse:
    try:
        result = container.primary_design.compare_path_domains_to_target(
            domain_id_a=request.domain_id_a,
            domain_id_b=request.domain_id_b,
            target_points=[(point.shift_fraction, point.relative_force) for point in request.target_points],
            atlas_path_count=request.atlas_path_count,
            mass_mix_count=request.mass_mix_count,
            sample_count=request.sample_count,
        )
    except PrimaryDesignError as error:
        status = 404 if error.code == "DOMAIN_EXPIRED" else 422
        raise ApiProblem(status, error.code.lower(), str(error), error.details) from error
    return FixedPivotPathDomainCompareTargetResponse(**result)

