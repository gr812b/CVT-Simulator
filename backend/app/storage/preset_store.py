"""JSON-backed presets behind a future database-friendly interface."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

from app.core.errors import PresetNotFoundError


@dataclass(frozen=True, slots=True)
class PresetRecord:
    id: str
    name: str
    description: str
    simulation_case: dict


class PresetStore(Protocol):
    def list(self) -> list[PresetRecord]:
        raise NotImplementedError

    def get(self, preset_id: str) -> PresetRecord:
        raise NotImplementedError


class JsonPresetStore:
    """Load immutable bundled presets from one directory of JSON files."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._records = self._load_records(directory)

    def list(self) -> list[PresetRecord]:
        return [self._records[key] for key in sorted(self._records)]

    def get(self, preset_id: str) -> PresetRecord:
        try:
            return self._records[preset_id]
        except KeyError as error:
            raise PresetNotFoundError(preset_id) from error

    @staticmethod
    def _load_records(directory: Path) -> dict[str, PresetRecord]:
        if not directory.is_dir():
            raise ValueError(f"Preset directory does not exist: {directory}")
        records: dict[str, PresetRecord] = {}
        for path in sorted(directory.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = PresetRecord(
                id=str(payload["id"]),
                name=str(payload["name"]),
                description=str(payload.get("description", "")),
                simulation_case=dict(payload["simulation_case"]),
            )
            if record.id in records:
                raise ValueError(f"Duplicate preset id {record.id!r}.")
            records[record.id] = record
        return records
