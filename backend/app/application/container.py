"""Application composition root. No route constructs CINDER-facing services."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.cinder_gateway import CinderGateway
from app.application.run_manager import RunManager
from app.core.settings import Settings
from app.storage.preset_store import JsonPresetStore, PresetStore
from app.storage.run_store import InMemoryRunStore, RunStore


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    gateway: CinderGateway
    presets: PresetStore
    runs: RunManager


def build_container(settings: Settings) -> ApplicationContainer:
    gateway = CinderGateway()
    run_store: RunStore = InMemoryRunStore()
    return ApplicationContainer(
        settings=settings,
        gateway=gateway,
        presets=JsonPresetStore(settings.resolved_preset_directory()),
        runs=RunManager(
            gateway=gateway,
            store=run_store,
            timeout_seconds=settings.run_timeout_seconds,
            executor_mode=settings.run_executor_mode,
        ),
    )
