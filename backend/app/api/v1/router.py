"""Version-one feature router."""

from __future__ import annotations

from fastapi import APIRouter

from . import library, metadata, presets, runs, simulation_cases, studies

router = APIRouter()
router.include_router(metadata.router)
router.include_router(library.router)
router.include_router(presets.router)
router.include_router(simulation_cases.router)
router.include_router(studies.router)
router.include_router(runs.router)
