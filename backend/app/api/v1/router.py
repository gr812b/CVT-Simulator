"""Version-one feature router."""

from __future__ import annotations

from app.api.v1.dependencies import get_current_principal
from app.schemas.common import ErrorResponse
from fastapi import APIRouter, Depends

from . import (
    auth,
    experiments,
    library,
    metadata,
    physical_library,
    presets,
    primary_design,
    publications,
    results,
    runs,
    simulation_cases,
    studies,
    validation,
)

router = APIRouter(
    responses={
        code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 429)
    }
)
router.include_router(auth.router)
router.include_router(publications.router)
router.include_router(results.router, dependencies=[Depends(get_current_principal)])
router.include_router(experiments.router, dependencies=[Depends(get_current_principal)])
router.include_router(metadata.router)
router.include_router(library.router, dependencies=[Depends(get_current_principal)])
router.include_router(physical_library.router, dependencies=[Depends(get_current_principal)])
router.include_router(presets.router)
router.include_router(
    simulation_cases.router, dependencies=[Depends(get_current_principal)]
)
router.include_router(studies.router, dependencies=[Depends(get_current_principal)])
router.include_router(
    primary_design.router, dependencies=[Depends(get_current_principal)]
)
router.include_router(runs.router, dependencies=[Depends(get_current_principal)])
router.include_router(validation.router, dependencies=[Depends(get_current_principal)])
