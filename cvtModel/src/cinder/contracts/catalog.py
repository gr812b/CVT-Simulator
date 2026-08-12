"""Factual catalog of document-supported CINDER construction blocks.

The catalog is not a recommendation engine.  It identifies built-in component
kinds, supported pulley mounts, and the document fields each component needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .conventions import PUBLIC_CONTRACT_VERSION, describe_public_field


@dataclass(frozen=True, slots=True)
class ComponentParameter:
    key: str
    label: str
    unit: str
    required: bool
    description: str
    minimum: float | None = None
    maximum: float | None = None
    value_kind: Literal["number", "object"] = "number"
    dimension: str | None = None

    def as_dict(self) -> dict[str, Any]:
        descriptor = describe_public_field(
            self.key,
            unit=self.unit,
            label=self.label,
            dimension=self.dimension,
        )
        payload: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "value_kind": self.value_kind,
            "canonical_unit": descriptor.unit,
            "dimension": descriptor.dimension,
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
    supported_mounts: tuple[str, ...] = ("primary", "secondary")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "supported_mounts": list(self.supported_mounts),
            "parameters": [parameter.as_dict() for parameter in self.parameters],
        }


def component_catalog() -> tuple[ComponentDescriptor, ...]:
    """Return document-supported physical components and scalar inputs."""

    return (
        ComponentDescriptor(
            kind="axial_spring",
            label="Axial spring",
            description="Linear compression spring expressed in the mounted pulley local axial coordinate.",
            parameters=(
                ComponentParameter(
                    "stiffness_N_per_m",
                    "Stiffness",
                    "N/m",
                    True,
                    "Linear spring stiffness.",
                    0.0,
                    dimension="linear_stiffness",
                ),
                ComponentParameter(
                    "initial_compression_m",
                    "Initial compression",
                    "m",
                    True,
                    "Compression at local coordinate zero.",
                    dimension="length",
                ),
                ComponentParameter(
                    "compression_per_axial_position",
                    "Compression per axial position",
                    "1",
                    True,
                    "Signed local-coordinate mapping from axial position to spring compression.",
                    dimension="dimensionless",
                ),
            ),
        ),
        ComponentDescriptor(
            kind="centrifugal_ramp",
            label="Centrifugal ramp",
            description="Quasi-static centrifugal flyweight force projected through a radial-displacement profile.",
            parameters=(
                ComponentParameter(
                    "flyweight_mass_kg",
                    "Equivalent flyweight mass",
                    "kg",
                    True,
                    "Equivalent moving flyweight mass.",
                    0.0,
                    dimension="mass",
                ),
                ComponentParameter(
                    "radius_at_zero_position_m",
                    "Radius at zero position",
                    "m",
                    True,
                    "Flyweight radius before profile displacement.",
                    0.0,
                    dimension="length",
                ),
                ComponentParameter(
                    "radial_displacement_profile",
                    "Radial displacement profile",
                    "object",
                    True,
                    "Piecewise ramp profile used by the flyweight mechanism.",
                    value_kind="object",
                    dimension="structure",
                ),
            ),
            supported_mounts=("primary",),
        ),
        ComponentDescriptor(
            kind="helical_torque_reaction",
            label="Helical torque reaction",
            description="Torque-reactive helix with torsional preload and movable-member torque fraction.",
            parameters=(
                ComponentParameter(
                    "torsional_stiffness_Nm_per_rad",
                    "Torsional stiffness",
                    "N·m/rad",
                    True,
                    "Helix torsional spring stiffness.",
                    0.0,
                    dimension="torsional_stiffness",
                ),
                ComponentParameter(
                    "initial_twist_rad",
                    "Initial twist",
                    "rad",
                    True,
                    "Torsional preload at the helix reference.",
                    dimension="angle",
                ),
                ComponentParameter(
                    "movable_member_torque_fraction",
                    "Movable-member torque fraction",
                    "1",
                    False,
                    "Fraction of reacted shaft torque assigned to the movable member.",
                    0.0,
                    1.0,
                    dimension="dimensionless",
                ),
            ),
            supported_mounts=("primary", "secondary"),
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
                "segment_kinds": [
                    {
                        "kind": "linear_segment",
                        "parameters": [
                            {
                                "key": "length_m",
                                "canonical_unit": "m",
                                "dimension": "length",
                            },
                            {
                                "key": "angle_rad",
                                "canonical_unit": "rad",
                                "dimension": "angle",
                            },
                        ],
                    },
                    {
                        "kind": "circular_segment",
                        "parameters": [
                            {
                                "key": "length_m",
                                "canonical_unit": "m",
                                "dimension": "length",
                            },
                            {
                                "key": "angle_start_rad",
                                "canonical_unit": "rad",
                                "dimension": "angle",
                            },
                            {
                                "key": "angle_end_rad",
                                "canonical_unit": "rad",
                                "dimension": "angle",
                            },
                            {
                                "key": "quadrant",
                                "value_kind": "integer",
                                "dimension": "dimensionless",
                            },
                        ],
                    },
                ],
            },
            {
                "kind": "helix_profile",
                "description": "Pulley helix defined by a positive-opening circumferential piecewise ramp and radius.",
                "parameters": [
                    {"key": "radius_m", "canonical_unit": "m", "dimension": "length"},
                ],
            },
        ],
    }
