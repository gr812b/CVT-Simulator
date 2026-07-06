"""Built-in immutable design presets."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.schemas.presets import PresetListResponse, PresetResponse, PresetSummary

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("", response_model=PresetListResponse)
def list_presets(container: ApplicationContainer = Depends(get_container)) -> PresetListResponse:
    records = container.presets.list()
    return PresetListResponse(
        presets=[
            PresetSummary(id=item.id, name=item.name, description=item.description)
            for item in records
        ]
    )


@router.get("/{preset_id}", response_model=PresetResponse)
def get_preset(
    preset_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> PresetResponse:
    item = container.presets.get(preset_id)
    return PresetResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        simulation_case=item.simulation_case,
    )
