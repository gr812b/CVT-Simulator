"""Version-one feature router."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    library,
    metadata,
    presets,
    primary_design,
    runs,
    simulation_cases,
    studies,
    validation,
)

router = APIRouter()
router.include_router(metadata.router)
router.include_router(library.router)
router.include_router(presets.router)
router.include_router(simulation_cases.router)
router.include_router(studies.router)
router.include_router(primary_design.router)
router.include_router(runs.router)
router.include_router(validation.router)
