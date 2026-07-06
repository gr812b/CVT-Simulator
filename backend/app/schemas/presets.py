"""Preset transport schemas."""

from __future__ import annotations

from .common import ApiModel, JsonObject


class PresetSummary(ApiModel):
    id: str
    name: str
    description: str = ""


class PresetListResponse(ApiModel):
    presets: list[PresetSummary]


class PresetResponse(PresetSummary):
    simulation_case: JsonObject
