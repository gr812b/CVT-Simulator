"""Application composition root. No route constructs CINDER-facing services."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.cinder_gateway import CinderGateway
from app.core.settings import Settings
from app.engineering.fixed_pivot_primary import FixedPivotPrimaryDesignService
from app.storage.preset_store import JsonPresetStore, PresetStore


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    gateway: CinderGateway
    primary_design: FixedPivotPrimaryDesignService
    presets: PresetStore


def build_container(settings: Settings) -> ApplicationContainer:
    gateway = CinderGateway()
    return ApplicationContainer(
        settings=settings,
        gateway=gateway,
        primary_design=FixedPivotPrimaryDesignService(),
        presets=JsonPresetStore(settings.resolved_preset_directory()),
    )
