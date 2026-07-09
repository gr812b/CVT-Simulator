"""Editable-field metadata for composed simulation documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class EditableFieldDescriptor:
    """One stable JSON-pointer field exposed to a UI or backend editor."""

    path: str
    label: str
    section: str
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    when: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "label": self.label,
            "section": self.section,
        }
        if self.unit is not None:
            payload["unit"] = self.unit
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.when is not None:
            payload["when"] = dict(self.when)
        return payload


def editable_simulation_case_schema() -> dict[str, Any]:
    """Return UI-oriented fields for the current composed document contract."""

    fields = [
        EditableFieldDescriptor("/assembly/geometry/deadzone_shift_m", "Deadzone shift", "CVT geometry", "m", 0.0),
        EditableFieldDescriptor("/assembly/geometry/max_shift_m", "Maximum shift", "CVT geometry", "m", 0.0),
        EditableFieldDescriptor("/assembly/contact/static_friction_coefficient", "Static friction coefficient", "CVT contact", None, 0.0),
        EditableFieldDescriptor("/assembly/contact/kinetic_friction_coefficient", "Kinetic friction coefficient", "CVT contact", None, 0.0),
        EditableFieldDescriptor("/shaft_boundaries/primary/equivalent_rotational_inertia_kg_m2", "Primary boundary inertia", "Primary shaft boundary", "kg m^2", 0.0, when={"/shaft_boundaries/primary/kind": "full_throttle_engine"}),
        EditableFieldDescriptor("/shaft_boundaries/primary/points/*/angular_speed_rad_per_s", "Engine curve speed", "Primary shaft boundary", "rad/s", 0.0, when={"/shaft_boundaries/primary/kind": "full_throttle_engine"}),
        EditableFieldDescriptor("/shaft_boundaries/primary/points/*/torque_Nm", "Engine curve torque", "Primary shaft boundary", "N m", when={"/shaft_boundaries/primary/kind": "full_throttle_engine"}),
        EditableFieldDescriptor("/shaft_boundaries/secondary/vehicle/mass_kg", "Vehicle mass", "Secondary shaft boundary", "kg", 0.0, when={"/shaft_boundaries/secondary/kind": "locked_final_drive"}),
        EditableFieldDescriptor("/shaft_boundaries/secondary/final_drive/reduction_ratio", "Final-drive reduction", "Secondary shaft boundary", "1", 0.0, when={"/shaft_boundaries/secondary/kind": "locked_final_drive"}),
        EditableFieldDescriptor("/shaft_boundaries/secondary/final_drive/wheel_radius_m", "Wheel radius", "Secondary shaft boundary", "m", 0.0, when={"/shaft_boundaries/secondary/kind": "locked_final_drive"}),
        EditableFieldDescriptor("/shaft_boundaries/secondary/road_load/rolling_resistance_coefficient", "Rolling resistance coefficient", "Secondary shaft boundary", None, 0.0, when={"/shaft_boundaries/secondary/kind": "locked_final_drive"}),
        EditableFieldDescriptor("/shaft_boundaries/secondary/road_load/drag_coefficient", "Drag coefficient", "Secondary shaft boundary", None, 0.0, when={"/shaft_boundaries/secondary/kind": "locked_final_drive"}),
        EditableFieldDescriptor("/shaft_boundaries/secondary/road_load/frontal_area_m2", "Frontal area", "Secondary shaft boundary", "m^2", 0.0, when={"/shaft_boundaries/secondary/kind": "locked_final_drive"}),
        EditableFieldDescriptor("/host/initial_state/secondary_shaft_angle_rad", "Initial secondary shaft angle", "Host state", "rad"),
        EditableFieldDescriptor("/scenario/initial_cvt_state/primary_angular_speed_rad_per_s", "Initial primary speed", "Initial CVT state", "rad/s"),
        EditableFieldDescriptor("/scenario/initial_cvt_state/shift_position_m", "Initial shift", "Initial CVT state", "m", 0.0),
    ]
    return {"fields": [field.as_dict() for field in fields]}
