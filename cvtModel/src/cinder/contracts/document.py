"""Versioned JSON-safe assembly design documents.

This is an adapter around CINDER's current built-in physical objects.  It does
not alter the internal construction contract: a decoded document simply builds
an ordinary :class:`CVTAssemblySpec` through the same specs and builders used by
Python callers.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import degrees, radians
from typing import Any

from cinder.model.cvt.actuation import (
    AxialSpringForce,
    AxialSpringForceSpec,
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
    FlyweightMassGeometry,
    HelicalTorqueReactionForce,
    HelicalTorqueReactionSpec,
    PulleyActuator,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometrySpec,
)
from cinder.model.cvt.geometry import (
    BeltPulleyGeometry,
    BeltPulleyGeometrySpec,
    BeltSectionSpec,
)
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    resolve_inertias,
)
from cinder.model.cvt.profiles import (
    C3TransitionSegment,
    CircularSegment,
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
)
from cinder.model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    HelicalPulleyCoupling,
    PulleyPairSpec,
    PulleySpec,
)

from .conventions import PUBLIC_CONTRACT_VERSION
from ._decode import (
    DesignDocumentError,
    optional_number as _optional_number,
    require as _require,
    require_integer as _integer,
    require_mapping as _mapping,
    require_number as _number,
    require_sequence as _sequence,
    require_string as _string,
)

ASSEMBLY_DOCUMENT_TYPE = "cinder_cvt_assembly"


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
            "static_friction_coefficient": assembly.contact.static_friction_coefficient,
            "kinetic_friction_coefficient": assembly.contact.kinetic_friction_coefficient,
        },
        "inertias": {
            "primary": {
                "fixed_rotating_hardware_inertia_kg_m2": primary.fixed_rotating_hardware_inertia,
                "movable_sheave_rotational_inertia_kg_m2": primary.movable_sheave_rotational_inertia,
                "moving_sheave_mass_kg": masses.primary_moving_sheave_mass,
            },
            "secondary": {
                "fixed_rotating_hardware_inertia_kg_m2": secondary.fixed_side.fixed_rotating_hardware_inertia,
                "movable_sheave_rotational_inertia_kg_m2": secondary.movable_sheave_rotational_inertia,
                "moving_sheave_mass_kg": masses.secondary_moving_sheave_mass,
            },
            "belt_density_kg_per_m3": assembly.inertias.belt.density,
        },
        "pulleys": {
            "primary": _encode_pulley(assembly.pulleys.primary),
            "secondary": _encode_pulley(assembly.pulleys.secondary),
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
        primary_outer_radius_at_zero_shift=_number(
            geometry_doc, "primary_outer_radius_at_zero_shift_m"
        ),
        secondary_outer_radius_at_zero_shift=_number(
            geometry_doc, "secondary_outer_radius_at_zero_shift_m"
        ),
        sheave_half_angle=_number(geometry_doc, "sheave_half_angle_rad"),
        deadzone_shift=_number(geometry_doc, "deadzone_shift_m"),
        max_shift=_number(geometry_doc, "max_shift_m"),
    )
    geometry = BeltPulleyGeometry(geometry_spec)

    contact_doc = _mapping(_require(root, "contact"), "contact")
    contact = BeltContactSpec(
        static_friction_coefficient=_number(contact_doc, "static_friction_coefficient"),
        kinetic_friction_coefficient=_optional_number(
            contact_doc, "kinetic_friction_coefficient", default=None
        ),
    )

    inertias_doc = _mapping(_require(root, "inertias"), "inertias")
    primary_doc = _mapping(_require(inertias_doc, "primary"), "inertias.primary")
    secondary_doc = _mapping(_require(inertias_doc, "secondary"), "inertias.secondary")
    inertias = resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
                fixed_rotating_hardware_inertia=_number(
                    primary_doc, "fixed_rotating_hardware_inertia_kg_m2"
                ),
                movable_sheave_rotational_inertia=_number(
                    primary_doc, "movable_sheave_rotational_inertia_kg_m2"
                ),
                moving_sheave_mass=_number(primary_doc, "moving_sheave_mass_kg"),
            ),
            secondary=SecondaryInertia(
                fixed_rotating_hardware_inertia=_number(
                    secondary_doc, "fixed_rotating_hardware_inertia_kg_m2"
                ),
                movable_sheave_rotational_inertia=_number(
                    secondary_doc, "movable_sheave_rotational_inertia_kg_m2"
                ),
                moving_sheave_mass=_number(secondary_doc, "moving_sheave_mass_kg"),
            ),
            belt=BeltMass(density=_number(inertias_doc, "belt_density_kg_per_m3")),
        ),
        belt_section=belt,
        belt_outer_length=geometry_spec.belt_outer_length,
    )

    pulleys_doc = _mapping(_require(root, "pulleys"), "pulleys")
    primary_pulley = _decode_pulley(
        _mapping(_require(pulleys_doc, "primary"), "pulleys.primary"),
        location="primary",
    )
    secondary_pulley = _decode_pulley(
        _mapping(_require(pulleys_doc, "secondary"), "pulleys.secondary"),
        location="secondary",
    )

    return CVTAssemblySpec(
        geometry=geometry,
        pulleys=PulleyPairSpec(primary=primary_pulley, secondary=secondary_pulley),
        inertias=inertias,
        contact=contact,
    )


def _encode_pulley(pulley: PulleySpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "components": [
            _encode_force_law(force_law) for force_law in pulley.actuator.force_laws
        ],
    }
    if pulley.helical_coupling is not None:
        coupling = pulley.helical_coupling
        payload["helical_coupling"] = {
            "profile": _encode_helix_profile(coupling.profile),
            "opening_per_axial_position": coupling.opening_per_axial_position,
            "opening_offset_m": coupling.opening_offset,
        }
    return payload


def _decode_pulley(payload: Mapping[str, Any], *, location: str) -> PulleySpec:
    components = _sequence(
        _require(payload, "components"), f"pulleys.{location}.components"
    )
    if not components:
        raise DesignDocumentError(f"pulleys.{location}.components must not be empty.")
    force_laws = tuple(
        _decode_force_law(
            _mapping(component, f"pulleys.{location}.components[{index}]")
        )
        for index, component in enumerate(components)
    )
    coupling_document = payload.get("helical_coupling")
    coupling = None
    if coupling_document is not None:
        coupling_data = _mapping(
            coupling_document, f"pulleys.{location}.helical_coupling"
        )
        coupling = HelicalPulleyCoupling(
            profile=_decode_helix_profile(
                _mapping(
                    _require(coupling_data, "profile"),
                    f"pulleys.{location}.helical_coupling.profile",
                )
            ),
            opening_per_axial_position=_optional_number(
                coupling_data, "opening_per_axial_position", default=-1.0
            ),
            opening_offset=_optional_number(
                coupling_data, "opening_offset_m", default=0.0
            ),
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
            "radial_displacement_profile": _encode_piecewise_ramp(
                spec.radial_displacement_profile
            ),
        }
    if isinstance(force_law, FixedPivotFlyweightForce):
        mechanism_map = force_law.spec.mechanism_map
        if not isinstance(mechanism_map, PivotedRollerFollowerFlyweightMap):
            raise UnsupportedDesignDocumentError(
                "Only PivotedRollerFollowerFlyweightMap is serializable for "
                "the fixed-pivot flyweight force law."
            )
        geometry = mechanism_map.geometry_spec
        mass = mechanism_map.mass_geometry
        return {
            "kind": "fixed_pivot_roller_flyweight",
            "geometry": {
                "pivot_axial_position_m": geometry.pivot_axial_position,
                "pivot_radius_m": geometry.pivot_radius,
                "arm_length_m": geometry.arm_length,
                "roller_radius_m": geometry.roller_radius,
                "ramp_reference_axial_position_m": (
                    geometry.ramp_reference_axial_position
                ),
                "ramp_reference_radius_m": geometry.ramp_reference_radius,
                "ramp_profile": _encode_piecewise_ramp(geometry.ramp_profile),
                "ramp_axial_direction": geometry.ramp_axial_direction,
                "axial_position_min_m": geometry.axial_position_min,
                "axial_position_max_m": geometry.axial_position_max,
                "roller_side_sign": geometry.roller_side_sign,
                "root_scan_points": geometry.root_scan_points,
                "validation_positions": geometry.validation_positions,
                "root_residual_tolerance_m2": geometry.root_residual_tolerance,
                "coordinate_tolerance_m": geometry.coordinate_tolerance,
                "compilation_points": mechanism_map.compilation_points,
            },
            "mass_geometry": {
                "number_of_flyweights": mass.number_of_flyweights,
                "mass_per_flyweight_kg": mass.mass_per_flyweight,
                "first_moment_u_kg_m": mass.first_moment_u,
                "first_moment_v_kg_m": mass.first_moment_v,
                "second_moment_u_kg_m2": mass.second_moment_u,
                "second_moment_v_kg_m2": mass.second_moment_v,
                "product_moment_uv_kg_m2": mass.product_moment_uv,
                "second_moment_z_kg_m2": mass.second_moment_z,
            },
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
                compression_per_axial_position=_number(
                    payload, "compression_per_axial_position"
                ),
            )
        )
    if kind == "centrifugal_ramp":
        return CentrifugalRampForce(
            CentrifugalRampForceSpec(
                flyweight_mass=_number(payload, "flyweight_mass_kg"),
                radius_at_zero_position=_number(payload, "radius_at_zero_position_m"),
                radial_displacement_profile=_decode_piecewise_ramp(
                    _mapping(
                        _require(payload, "radial_displacement_profile"),
                        "radial_displacement_profile",
                    )
                ),
            )
        )
    if kind == "fixed_pivot_roller_flyweight":
        geometry = _mapping(_require(payload, "geometry"), "geometry")
        mass = _mapping(_require(payload, "mass_geometry"), "mass_geometry")
        geometry_spec = PivotedRollerFollowerGeometrySpec(
            pivot_axial_position=_number(geometry, "pivot_axial_position_m"),
            pivot_radius=_number(geometry, "pivot_radius_m"),
            arm_length=_number(geometry, "arm_length_m"),
            roller_radius=_number(geometry, "roller_radius_m"),
            ramp_reference_axial_position=_number(
                geometry, "ramp_reference_axial_position_m"
            ),
            ramp_reference_radius=_number(geometry, "ramp_reference_radius_m"),
            ramp_profile=_decode_piecewise_ramp(
                _mapping(_require(geometry, "ramp_profile"), "geometry.ramp_profile")
            ),
            ramp_axial_direction=(
                _integer(geometry, "ramp_axial_direction")
                if "ramp_axial_direction" in geometry
                else 1
            ),
            axial_position_min=_number(geometry, "axial_position_min_m"),
            axial_position_max=_number(geometry, "axial_position_max_m"),
            roller_side_sign=_integer(geometry, "roller_side_sign"),
            root_scan_points=(
                _integer(geometry, "root_scan_points")
                if "root_scan_points" in geometry
                else 257
            ),
            validation_positions=(
                _integer(geometry, "validation_positions")
                if "validation_positions" in geometry
                else 33
            ),
            root_residual_tolerance=_optional_number(
                geometry, "root_residual_tolerance_m2", default=1.0e-14
            ),
            coordinate_tolerance=_optional_number(
                geometry, "coordinate_tolerance_m", default=1.0e-10
            ),
        )
        mass_geometry = FlyweightMassGeometry(
            number_of_flyweights=_integer(mass, "number_of_flyweights"),
            mass_per_flyweight=_number(mass, "mass_per_flyweight_kg"),
            first_moment_u=_number(mass, "first_moment_u_kg_m"),
            first_moment_v=_number(mass, "first_moment_v_kg_m"),
            second_moment_u=_number(mass, "second_moment_u_kg_m2"),
            second_moment_v=_number(mass, "second_moment_v_kg_m2"),
            product_moment_uv=_optional_number(
                mass, "product_moment_uv_kg_m2", default=0.0
            ),
            second_moment_z=_optional_number(
                mass, "second_moment_z_kg_m2", default=0.0
            ),
        )
        return FixedPivotFlyweightForce(
            FixedPivotFlyweightForceSpec(
                mechanism_map=PivotedRollerFollowerFlyweightMap(
                    geometry_spec=geometry_spec,
                    mass_geometry=mass_geometry,
                    compilation_points=(
                        _integer(geometry, "compilation_points")
                        if "compilation_points" in geometry
                        else 257
                    ),
                )
            )
        )
    if kind == "helical_torque_reaction":
        return HelicalTorqueReactionForce(
            spec=HelicalTorqueReactionSpec(
                torsional_stiffness=_number(payload, "torsional_stiffness_Nm_per_rad"),
                initial_twist=_number(payload, "initial_twist_rad"),
                movable_member_torque_fraction=_optional_number(
                    payload, "movable_member_torque_fraction", default=0.5
                ),
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
        raise UnsupportedDesignDocumentError(
            "Only kind='piecewise_ramp' is supported here."
        )
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
            "angle_rad": radians(segment.angle_degrees),
        }
    if isinstance(segment, C3TransitionSegment):
        return {
            "kind": "c3_transition_segment",
            "length_m": segment.length,
            "slope_start": segment.slope_start,
            "curvature_start_per_m": segment.curvature_start,
            "third_derivative_start_per_m2": segment.third_derivative_start,
            "slope_end": segment.slope_end,
            "curvature_end_per_m": segment.curvature_end,
            "third_derivative_end_per_m2": segment.third_derivative_end,
        }
    if isinstance(segment, CircularSegment):
        return {
            "kind": "circular_segment",
            "length_m": segment.length,
            "angle_start_rad": radians(segment.angle_start_degrees),
            "angle_end_rad": radians(segment.angle_end_degrees),
            "quadrant": segment.quadrant,
        }
    raise UnsupportedDesignDocumentError(
        f"Unsupported ramp segment {type(segment).__name__}."
    )


def _decode_ramp_segment(payload: Mapping[str, Any]) -> LinearSegment | CircularSegment | C3TransitionSegment:
    kind = _string(payload, "kind")
    if kind == "linear_segment":
        return LinearSegment(
            length=_number(payload, "length_m"),
            angle_degrees=degrees(_number(payload, "angle_rad")),
        )
    if kind == "c3_transition_segment":
        return C3TransitionSegment(
            length=_number(payload, "length_m"),
            slope_start=_number(payload, "slope_start"),
            curvature_start=_number(payload, "curvature_start_per_m"),
            third_derivative_start=_number(
                payload, "third_derivative_start_per_m2"
            ),
            slope_end=_number(payload, "slope_end"),
            curvature_end=_number(payload, "curvature_end_per_m"),
            third_derivative_end=_number(
                payload, "third_derivative_end_per_m2"
            ),
        )
    if kind == "circular_segment":
        quadrant = _integer(payload, "quadrant")
        return CircularSegment(
            length=_number(payload, "length_m"),
            angle_start_degrees=degrees(_number(payload, "angle_start_rad")),
            angle_end_degrees=degrees(_number(payload, "angle_end_rad")),
            quadrant=quadrant,
        )
    raise UnsupportedDesignDocumentError(f"Unsupported ramp segment kind {kind!r}.")


def _encode_helix_profile(profile: HelixProfile) -> dict[str, Any]:
    return {
        "kind": "helix_profile",
        "circumferential_profile": _encode_piecewise_ramp(
            profile.circumferential_profile
        ),
        "radius_m": profile.radius,
    }


def _decode_helix_profile(payload: Mapping[str, Any]) -> HelixProfile:
    if _string(payload, "kind") != "helix_profile":
        raise UnsupportedDesignDocumentError(
            "Only kind='helix_profile' is supported here."
        )
    return HelixProfile(
        circumferential_profile=_decode_piecewise_ramp(
            _mapping(
                _require(payload, "circumferential_profile"),
                "helix_profile.circumferential_profile",
            )
        ),
        radius=_number(payload, "radius_m"),
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
