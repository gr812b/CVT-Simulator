"""Versioned JSON-safe assembly design documents.

This is an adapter around CINDER's current built-in physical objects.  It does
not alter the internal construction contract: a decoded document simply builds
an ordinary :class:`CVTAssemblySpec` through the same specs and builders used by
Python callers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from cinder.model.cvt.actuation import (
    AxialSpringForce,
    AxialSpringForceSpec,
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
    HelicalTorqueReactionForce,
    HelicalTorqueReactionSpec,
    PulleyActuator,
)
from cinder.model.cvt.geometry import BeltPulleyGeometry, BeltPulleyGeometrySpec, BeltSectionSpec
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    resolve_inertias,
)
from cinder.model.cvt.profiles import CircularSegment, HelixProfile, LinearSegment, PiecewiseRamp
from cinder.model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    HelicalPulleyCoupling,
    PulleyPairSpec,
    PulleySpec,
)

from .conventions import PUBLIC_CONTRACT_VERSION

ASSEMBLY_DOCUMENT_TYPE = "cinder_cvt_assembly"


class DesignDocumentError(ValueError):
    """Raised when a design document is malformed or unsupported."""


class UnsupportedDesignDocumentError(DesignDocumentError):
    """Raised when a valid-looking document uses an unsupported component."""


def encode_assembly_document(assembly: CVTAssemblySpec) -> dict[str, Any]:
    """Encode one assembly into CINDER's current JSON-safe document format."""

    if not isinstance(assembly, CVTAssemblySpec):
        raise TypeError("assembly must be a CVTAssemblySpec.")

    spec = assembly.geometry.spec
    belt = spec.belt
    primary = assembly.inertias.primary
    secondary = assembly.inertias.secondary
    masses = assembly.inertias.axial_translation

    return {
        "schema_version": PUBLIC_CONTRACT_VERSION,
        "document_type": ASSEMBLY_DOCUMENT_TYPE,
        "geometry": {
            "belt": {
                "height_m": belt.height,
                "outer_width_m": belt.outer_width,
                "inner_width_m": belt.inner_width,
                "cord_depth_from_outer_m": belt.cord_depth_from_outer,
            },
            "belt_outer_length_m": spec.belt_outer_length,
            "primary_outer_radius_at_zero_shift_m": spec.primary_outer_radius_at_zero_shift,
            "secondary_outer_radius_at_zero_shift_m": spec.secondary_outer_radius_at_zero_shift,
            "sheave_half_angle_rad": spec.sheave_half_angle,
            "deadzone_shift_m": spec.deadzone_shift,
            "max_shift_m": spec.max_shift,
        },
        "contact": {
            "friction_coefficient": assembly.contact.friction_coefficient,
        },
        "inertias": {
            "primary": {
                "engine_rotational_inertia_kg_m2": primary.engine_rotational_inertia,
                "cvt_rotational_inertia_kg_m2": primary.cvt_rotational_inertia,
                "moving_sheave_mass_kg": masses.primary_moving_sheave_mass,
            },
            "secondary": {
                "fixed_rotational_inertia_kg_m2": secondary.fixed_side.output_fixed_rotational_inertia,
                "gearbox_input_rotational_inertia_kg_m2": secondary.fixed_side.gearbox_input_rotational_inertia,
                "movable_sheave_rotational_inertia_kg_m2": secondary.movable_sheave_rotational_inertia,
                "moving_sheave_mass_kg": masses.secondary_moving_sheave_mass,
            },
            "belt_density_kg_per_m3": assembly.inertias.belt.density,
        },
        "pulleys": {
            "input": _encode_pulley(assembly.pulleys.input),
            "output": _encode_pulley(assembly.pulleys.output),
        },
    }


def decode_assembly_document(document: Mapping[str, Any]) -> CVTAssemblySpec:
    """Decode a version-one assembly document into an ordinary CINDER assembly.

    Only the built-in components exposed by :func:`component_catalog_document`
    are accepted.  Custom Python force laws remain a Python-level extension
    point rather than being serialized ambiguously.
    """

    root = _mapping(document, "document")
    _require_exact_schema(root)
    geometry_doc = _mapping(_require(root, "geometry"), "geometry")
    belt_doc = _mapping(_require(geometry_doc, "belt"), "geometry.belt")

    belt = BeltSectionSpec(
        height=_number(belt_doc, "height_m"),
        outer_width=_number(belt_doc, "outer_width_m"),
        inner_width=_number(belt_doc, "inner_width_m"),
        cord_depth_from_outer=_number(belt_doc, "cord_depth_from_outer_m"),
    )
    geometry_spec = BeltPulleyGeometrySpec(
        belt=belt,
        belt_outer_length=_number(geometry_doc, "belt_outer_length_m"),
        primary_outer_radius_at_zero_shift=_number(geometry_doc, "primary_outer_radius_at_zero_shift_m"),
        secondary_outer_radius_at_zero_shift=_number(geometry_doc, "secondary_outer_radius_at_zero_shift_m"),
        sheave_half_angle=_number(geometry_doc, "sheave_half_angle_rad"),
        deadzone_shift=_number(geometry_doc, "deadzone_shift_m"),
        max_shift=_number(geometry_doc, "max_shift_m"),
    )
    geometry = BeltPulleyGeometry(geometry_spec)

    contact_doc = _mapping(_require(root, "contact"), "contact")
    contact = BeltContactSpec(friction_coefficient=_number(contact_doc, "friction_coefficient"))

    inertias_doc = _mapping(_require(root, "inertias"), "inertias")
    primary_doc = _mapping(_require(inertias_doc, "primary"), "inertias.primary")
    secondary_doc = _mapping(_require(inertias_doc, "secondary"), "inertias.secondary")
    inertias = resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
                engine_rotational_inertia=_number(primary_doc, "engine_rotational_inertia_kg_m2"),
                cvt_rotational_inertia=_number(primary_doc, "cvt_rotational_inertia_kg_m2"),
                moving_sheave_mass=_number(primary_doc, "moving_sheave_mass_kg"),
            ),
            secondary=SecondaryInertia(
                fixed_rotational_inertia=_number(secondary_doc, "fixed_rotational_inertia_kg_m2"),
                gearbox_input_rotational_inertia=_number(secondary_doc, "gearbox_input_rotational_inertia_kg_m2"),
                movable_sheave_rotational_inertia=_number(secondary_doc, "movable_sheave_rotational_inertia_kg_m2"),
                moving_sheave_mass=_number(secondary_doc, "moving_sheave_mass_kg"),
            ),
            belt=BeltMass(density=_number(inertias_doc, "belt_density_kg_per_m3")),
        ),
        belt_section=belt,
        belt_outer_length=geometry_spec.belt_outer_length,
    )

    pulleys_doc = _mapping(_require(root, "pulleys"), "pulleys")
    input_pulley = _decode_pulley(_mapping(_require(pulleys_doc, "input"), "pulleys.input"), location="input")
    output_pulley = _decode_pulley(_mapping(_require(pulleys_doc, "output"), "pulleys.output"), location="output")

    return CVTAssemblySpec(
        geometry=geometry,
        pulleys=PulleyPairSpec(input=input_pulley, output=output_pulley),
        inertias=inertias,
        contact=contact,
    )


def _encode_pulley(pulley: PulleySpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "components": [_encode_force_law(force_law) for force_law in pulley.actuator.force_laws],
    }
    if pulley.helical_coupling is not None:
        coupling = pulley.helical_coupling
        payload["helical_coupling"] = {
            "opening_per_axial_position": coupling.opening_per_axial_position,
            "opening_offset_m": coupling.opening_offset,
            "profile": _encode_helix_profile(coupling.profile),
        }
    return payload


def _decode_pulley(payload: Mapping[str, Any], *, location: str) -> PulleySpec:
    components = _sequence(_require(payload, "components"), f"pulleys.{location}.components")
    if not components:
        raise DesignDocumentError(f"pulleys.{location}.components must not be empty.")
    force_laws = tuple(
        _decode_force_law(_mapping(component, f"pulleys.{location}.components[{index}]"))
        for index, component in enumerate(components)
    )
    coupling_document = payload.get("helical_coupling")
    coupling = None
    if coupling_document is not None:
        coupling_data = _mapping(coupling_document, f"pulleys.{location}.helical_coupling")
        coupling = HelicalPulleyCoupling(
            profile=_decode_helix_profile(_mapping(_require(coupling_data, "profile"), f"pulleys.{location}.helical_coupling.profile")),
            opening_per_axial_position=_number(coupling_data, "opening_per_axial_position"),
            opening_offset=_number(coupling_data, "opening_offset_m"),
        )
    return PulleySpec(actuator=PulleyActuator(*force_laws), helical_coupling=coupling)


def _encode_force_law(force_law: object) -> dict[str, Any]:
    if isinstance(force_law, AxialSpringForce):
        spec = force_law.spec
        return {
            "kind": "axial_spring",
            "stiffness_N_per_m": spec.stiffness,
            "initial_compression_m": spec.initial_compression,
            "compression_per_axial_position": spec.compression_per_axial_position,
        }
    if isinstance(force_law, CentrifugalRampForce):
        spec = force_law.spec
        return {
            "kind": "centrifugal_ramp",
            "flyweight_mass_kg": spec.flyweight_mass,
            "radius_at_zero_position_m": spec.radius_at_zero_position,
            "radial_displacement_profile": _encode_piecewise_ramp(spec.radial_displacement_profile),
        }
    if isinstance(force_law, HelicalTorqueReactionForce):
        spec = force_law.spec
        return {
            "kind": "helical_torque_reaction",
            "torsional_stiffness_Nm_per_rad": spec.torsional_stiffness,
            "initial_twist_rad": spec.initial_twist,
            "movable_member_torque_fraction": spec.movable_member_torque_fraction,
        }
    raise UnsupportedDesignDocumentError(
        f"Cannot encode unsupported pulley force law {type(force_law).__name__}."
    )


def _decode_force_law(payload: Mapping[str, Any]) -> object:
    kind = _string(payload, "kind")
    if kind == "axial_spring":
        return AxialSpringForce(
            AxialSpringForceSpec(
                stiffness=_number(payload, "stiffness_N_per_m"),
                initial_compression=_number(payload, "initial_compression_m"),
                compression_per_axial_position=_number(payload, "compression_per_axial_position"),
            )
        )
    if kind == "centrifugal_ramp":
        return CentrifugalRampForce(
            CentrifugalRampForceSpec(
                flyweight_mass=_number(payload, "flyweight_mass_kg"),
                radius_at_zero_position=_number(payload, "radius_at_zero_position_m"),
                radial_displacement_profile=_decode_piecewise_ramp(
                    _mapping(_require(payload, "radial_displacement_profile"), "radial_displacement_profile")
                ),
            )
        )
    if kind == "helical_torque_reaction":
        return HelicalTorqueReactionForce(
            spec=HelicalTorqueReactionSpec(
                torsional_stiffness=_number(payload, "torsional_stiffness_Nm_per_rad"),
                initial_twist=_number(payload, "initial_twist_rad"),
                movable_member_torque_fraction=_optional_number(payload, "movable_member_torque_fraction", default=0.5),
            )
        )
    raise UnsupportedDesignDocumentError(f"Unsupported pulley component kind {kind!r}.")


def _encode_piecewise_ramp(profile: object) -> dict[str, Any]:
    if not isinstance(profile, PiecewiseRamp):
        raise UnsupportedDesignDocumentError(
            "Only PiecewiseRamp profiles composed of built-in segments are serializable."
        )
    return {
        "kind": "piecewise_ramp",
        "segments": [_encode_ramp_segment(segment) for segment in profile.segments],
    }


def _decode_piecewise_ramp(payload: Mapping[str, Any]) -> PiecewiseRamp:
    if _string(payload, "kind") != "piecewise_ramp":
        raise UnsupportedDesignDocumentError("Only kind='piecewise_ramp' is supported here.")
    segments = _sequence(_require(payload, "segments"), "piecewise_ramp.segments")
    if not segments:
        raise DesignDocumentError("piecewise_ramp.segments must not be empty.")
    return PiecewiseRamp(
        _decode_ramp_segment(_mapping(segment, f"piecewise_ramp.segments[{index}]"))
        for index, segment in enumerate(segments)
    )


def _encode_ramp_segment(segment: object) -> dict[str, Any]:
    if isinstance(segment, LinearSegment):
        return {
            "kind": "linear_segment",
            "length_m": segment.length,
            "angle_degrees": segment.angle_degrees,
        }
    if isinstance(segment, CircularSegment):
        return {
            "kind": "circular_segment",
            "length_m": segment.length,
            "angle_start_degrees": segment.angle_start_degrees,
            "angle_end_degrees": segment.angle_end_degrees,
            "quadrant": segment.quadrant,
        }
    raise UnsupportedDesignDocumentError(
        f"Unsupported ramp segment {type(segment).__name__}."
    )


def _decode_ramp_segment(payload: Mapping[str, Any]) -> LinearSegment | CircularSegment:
    kind = _string(payload, "kind")
    if kind == "linear_segment":
        return LinearSegment(length=_number(payload, "length_m"), angle_degrees=_number(payload, "angle_degrees"))
    if kind == "circular_segment":
        quadrant = _integer(payload, "quadrant")
        return CircularSegment(
            length=_number(payload, "length_m"),
            angle_start_degrees=_number(payload, "angle_start_degrees"),
            angle_end_degrees=_number(payload, "angle_end_degrees"),
            quadrant=quadrant,
        )
    raise UnsupportedDesignDocumentError(f"Unsupported ramp segment kind {kind!r}.")


def _encode_helix_profile(profile: HelixProfile) -> dict[str, Any]:
    return {
        "kind": "helix_profile",
        "circumferential_profile": _encode_piecewise_ramp(profile.circumferential_profile),
        "radius_m": profile.radius,
        "theta_offset_rad": profile.theta_offset,
    }


def _decode_helix_profile(payload: Mapping[str, Any]) -> HelixProfile:
    if _string(payload, "kind") != "helix_profile":
        raise UnsupportedDesignDocumentError("Only kind='helix_profile' is supported here.")
    return HelixProfile(
        circumferential_profile=_decode_piecewise_ramp(
            _mapping(_require(payload, "circumferential_profile"), "helix_profile.circumferential_profile")
        ),
        radius=_number(payload, "radius_m"),
        theta_offset=_optional_number(payload, "theta_offset_rad", default=0.0),
    )


def _require_exact_schema(document: Mapping[str, Any]) -> None:
    version = _integer(document, "schema_version")
    if version != PUBLIC_CONTRACT_VERSION:
        raise UnsupportedDesignDocumentError(
            f"Unsupported CINDER design-document schema_version {version}; expected {PUBLIC_CONTRACT_VERSION}."
        )
    if _string(document, "document_type") != ASSEMBLY_DOCUMENT_TYPE:
        raise UnsupportedDesignDocumentError(
            f"document_type must be {ASSEMBLY_DOCUMENT_TYPE!r}."
        )


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DesignDocumentError(f"{path} must be an object.")
    return value


def _sequence(value: object, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DesignDocumentError(f"{path} must be an array.")
    return value


def _require(mapping: Mapping[str, Any], key: str) -> Any:
    try:
        return mapping[key]
    except KeyError as error:
        raise DesignDocumentError(f"Missing required field {key!r}.") from error


def _number(mapping: Mapping[str, Any], key: str) -> float:
    value = _require(mapping, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DesignDocumentError(f"{key} must be a finite number.")
    numeric = float(value)
    if not isfinite(numeric):
        raise DesignDocumentError(f"{key} must be finite.")
    return numeric


def _optional_number(mapping: Mapping[str, Any], key: str, *, default: float) -> float:
    return default if key not in mapping else _number(mapping, key)


def _integer(mapping: Mapping[str, Any], key: str) -> int:
    value = _require(mapping, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DesignDocumentError(f"{key} must be an integer.")
    return value


def _string(mapping: Mapping[str, Any], key: str) -> str:
    value = _require(mapping, key)
    if not isinstance(value, str) or not value.strip():
        raise DesignDocumentError(f"{key} must be a non-empty string.")
    return value
