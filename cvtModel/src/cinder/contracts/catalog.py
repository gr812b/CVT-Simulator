"""Factual catalog of document-supported CINDER construction blocks.

The catalog is not a recommendation engine.  It only says which component
kinds can be represented in the public design document and which fields they
require.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .conventions import PUBLIC_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ComponentParameter:
    key: str
    label: str
    unit: str
    required: bool
    description: str
    minimum: float | None = None
    maximum: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "required": self.required,
            "description": self.description,
        }
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        return payload


@dataclass(frozen=True, slots=True)
class ComponentDescriptor:
    kind: str
    label: str
    description: str
    parameters: tuple[ComponentParameter, ...]
    supported_mounts: tuple[str, ...] = ("input", "output")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "supported_mounts": list(self.supported_mounts),
            "parameters": [parameter.as_dict() for parameter in self.parameters],
        }


def component_catalog() -> tuple[ComponentDescriptor, ...]:
    """Return document-supported physical components and their scalar inputs."""

    return (
        ComponentDescriptor(
            kind="axial_spring",
            label="Axial spring",
            description="Linear compression spring expressed in the mounted pulley local axial coordinate.",
            parameters=(
                ComponentParameter("stiffness_N_per_m", "Stiffness", "N/m", True, "Linear spring stiffness.", 0.0),
                ComponentParameter("initial_compression_m", "Initial compression", "m", True, "Compression at local coordinate zero."),
                ComponentParameter("compression_per_axial_position", "Compression per axial position", "1", True, "Signed local-coordinate mapping from axial position to spring compression."),
            ),
        ),
        ComponentDescriptor(
            kind="centrifugal_ramp",
            label="Centrifugal ramp",
            description="Quasi-static centrifugal flyweight force projected through a radial-displacement profile.",
            parameters=(
                ComponentParameter("flyweight_mass_kg", "Equivalent flyweight mass", "kg", True, "Equivalent moving flyweight mass.", 0.0),
                ComponentParameter("radius_at_zero_position_m", "Radius at zero position", "m", True, "Flyweight radius before profile displacement.", 0.0),
                ComponentParameter("radial_displacement_profile", "Radial displacement profile", "object", True, "Piecewise ramp profile used by the flyweight mechanism."),
            ),
        ),
        ComponentDescriptor(
            kind="helical_torque_reaction",
            label="Helical torque reaction",
            description="Torque-reactive helix with torsional preload and movable-member torque fraction.",
            parameters=(
                ComponentParameter("torsional_stiffness_Nm_per_rad", "Torsional stiffness", "N·m/rad", True, "Helix torsional spring stiffness.", 0.0),
                ComponentParameter("initial_twist_rad", "Initial twist", "rad", True, "Torsional preload at the helix reference."),
                ComponentParameter("movable_member_torque_fraction", "Movable-member torque fraction", "1", False, "Fraction of reacted shaft torque assigned to the movable member.", 0.0, 1.0),
            ),
            supported_mounts=("output",),
        ),
    )


def component_catalog_document() -> dict[str, Any]:
    """Return a JSON-safe factual catalog for a backend or frontend."""

    return {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "document_type": "cinder_component_catalog",
        "components": [component.as_dict() for component in component_catalog()],
        "profile_kinds": [
            {
                "kind": "piecewise_ramp",
                "description": "Ordered linear and/or circular local ramp segments.",
                "segment_kinds": ["linear_segment", "circular_segment"],
            },
            {
                "kind": "helix_profile",
                "description": "Secondary helix defined by a positive-opening circumferential piecewise ramp and radius.",
            },
        ],
    }
