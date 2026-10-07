"""Personal display settings only; no physical documents are converted or rewritten."""

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .common import ApiModel

# Kept in agreement with the typed frontend catalog by the unit integration test.
UNIT_CHOICES = json.loads(Path(__file__).with_name("unit_choices.json").read_text(encoding="utf-8"))
UnitScope = Literal["hardware", "vehicle", "course", "output"]


class UnitPreferences(ApiModel):
    preset: Literal["recommended", "metric", "si", "imperial"] = "recommended"
    hardware_length: Literal["in", "mm", "m"] = "in"
    component_mass: Literal["g", "kg", "oz"] = "g"
    vehicle_length: Literal["m", "ft", "in"] = "m"
    vehicle_mass: Literal["kg", "lb"] = "kg"
    course_length: Literal["m", "ft"] = "m"
    speed: Literal["km/h", "m/s", "mph"] = "km/h"
    output_length: Literal["m", "ft", "mm", "in"] = "m"
    output_speed: Literal["km/h", "m/s", "mph"] = "km/h"
    quantity_units: dict[UnitScope, dict[str, str]] = Field(default_factory=dict)

    @field_validator("quantity_units")
    @classmethod
    def check_dimensions(cls, value: dict[UnitScope, dict[str, str]]) -> dict[UnitScope, dict[str, str]]:
        for scope, settings in value.items():
            for dimension, unit in settings.items():
                if dimension not in UNIT_CHOICES[scope] or unit not in UNIT_CHOICES[scope][dimension]:
                    raise ValueError(f"Unsupported {scope} display unit for {dimension}: {unit}")
        return value

    def apply_to(self, previous: dict | None) -> dict:
        """PATCH preserves omitted settings, including preferences unknown to an old client.

        An explicitly supplied quantity_units map replaces that map, so resetting
        a preset/override is possible without mutating anyone else's preferences.
        """
        stored = UnitPreferences.model_validate(previous or {}).model_dump()
        return UnitPreferences.model_validate({**stored, **self.model_dump(exclude_unset=True)}).model_dump()
