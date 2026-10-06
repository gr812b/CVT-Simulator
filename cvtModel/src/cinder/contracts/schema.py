"""JSON Schemas for CINDER-owned public simulation contracts.

The schemas in this module mirror CINDER's stable serialized boundaries rather
than its internal mechanics objects.  Extension slots such as composed-system
hosts and shaft-boundary implementations remain intentionally opaque: CINDER
owns the slots, but not every implementation that may occupy them.
"""

from __future__ import annotations

from typing import Any

from .document import ASSEMBLY_DOCUMENT_TYPE
from .simulation_document import SIMULATION_CASE_DOCUMENT_TYPE
from .versions import (
    ASSEMBLY_DOCUMENT_SCHEMA_VERSION,
    CONVENTIONS_CONTRACT_VERSION,
    SIMULATION_CASE_SCHEMA_VERSION,
    SIMULATION_RESULT_CONTRACT_VERSION,
)


def _number() -> dict[str, Any]:
    return {"type": "number"}


def _nullable_number() -> dict[str, Any]:
    return {"type": ["number", "null"]}


def _nonnegative() -> dict[str, Any]:
    return {"type": "number", "minimum": 0.0}


def _positive() -> dict[str, Any]:
    return {"type": "number", "exclusiveMinimum": 0.0}


def _json_value_schema() -> dict[str, Any]:
    # Deliberately unconstrained JSON. Used only where the public contract itself
    # promises arbitrary metadata rather than a CINDER-owned structure.
    return {}


def _assembly_definitions() -> dict[str, Any]:
    number = _number()
    nonnegative = _nonnegative()
    positive = _positive()

    return {
        "assemblyBeltSection": {
            "type": "object",
            "required": [
                "height_m",
                "outer_width_m",
                "inner_width_m",
                "cord_depth_from_outer_m",
            ],
            "properties": {
                "height_m": positive,
                "outer_width_m": positive,
                "inner_width_m": positive,
                "cord_depth_from_outer_m": nonnegative,
            },
            "additionalProperties": False,
        },
        "assemblyGeometry": {
            "type": "object",
            "required": [
                "belt",
                "belt_outer_length_m",
                "primary_outer_radius_at_zero_shift_m",
                "secondary_outer_radius_at_zero_shift_m",
                "sheave_half_angle_rad",
                "deadzone_shift_m",
                "max_shift_m",
            ],
            "properties": {
                "belt": {"$ref": "#/$defs/assemblyBeltSection"},
                "belt_outer_length_m": positive,
                "primary_outer_radius_at_zero_shift_m": positive,
                "secondary_outer_radius_at_zero_shift_m": positive,
                "sheave_half_angle_rad": positive,
                "deadzone_shift_m": nonnegative,
                "max_shift_m": nonnegative,
            },
            "additionalProperties": False,
        },
        "assemblyContact": {
            "type": "object",
            "required": [
                "static_friction_coefficient",
                "kinetic_friction_coefficient",
            ],
            "properties": {
                "static_friction_coefficient": nonnegative,
                "kinetic_friction_coefficient": {
                    "type": ["number", "null"],
                    "minimum": 0.0,
                },
            },
            "additionalProperties": False,
        },
        "assemblyPulleyInertia": {
            "type": "object",
            "required": [
                "fixed_rotating_hardware_inertia_kg_m2",
                "movable_sheave_rotational_inertia_kg_m2",
                "moving_sheave_mass_kg",
            ],
            "properties": {
                "fixed_rotating_hardware_inertia_kg_m2": nonnegative,
                "movable_sheave_rotational_inertia_kg_m2": nonnegative,
                "moving_sheave_mass_kg": nonnegative,
            },
            "additionalProperties": False,
        },
        "assemblyInertias": {
            "type": "object",
            "required": ["primary", "secondary", "belt_density_kg_per_m3"],
            "properties": {
                "primary": {"$ref": "#/$defs/assemblyPulleyInertia"},
                "secondary": {"$ref": "#/$defs/assemblyPulleyInertia"},
                "belt_density_kg_per_m3": positive,
            },
            "additionalProperties": False,
        },
        "assemblyLinearRampSegment": {
            "type": "object",
            "required": ["kind", "length_m", "angle_rad"],
            "properties": {
                "kind": {"const": "linear_segment"},
                "length_m": positive,
                "angle_rad": number,
            },
            "additionalProperties": False,
        },
        "assemblyC3RampSegment": {
            "type": "object",
            "required": [
                "kind",
                "length_m",
                "slope_start",
                "curvature_start_per_m",
                "third_derivative_start_per_m2",
                "slope_end",
                "curvature_end_per_m",
                "third_derivative_end_per_m2",
            ],
            "properties": {
                "kind": {"const": "c3_transition_segment"},
                "length_m": positive,
                "slope_start": number,
                "curvature_start_per_m": number,
                "third_derivative_start_per_m2": number,
                "slope_end": number,
                "curvature_end_per_m": number,
                "third_derivative_end_per_m2": number,
            },
            "additionalProperties": False,
        },
        "assemblyCircularRampSegment": {
            "type": "object",
            "required": [
                "kind",
                "length_m",
                "angle_start_rad",
                "angle_end_rad",
                "quadrant",
            ],
            "properties": {
                "kind": {"const": "circular_segment"},
                "length_m": positive,
                "angle_start_rad": number,
                "angle_end_rad": number,
                "quadrant": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "assemblyRampSegment": {
            "oneOf": [
                {"$ref": "#/$defs/assemblyLinearRampSegment"},
                {"$ref": "#/$defs/assemblyC3RampSegment"},
                {"$ref": "#/$defs/assemblyCircularRampSegment"},
            ]
        },
        "assemblyPiecewiseRamp": {
            "type": "object",
            "required": ["kind", "segments"],
            "properties": {
                "kind": {"const": "piecewise_ramp"},
                "segments": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/assemblyRampSegment"},
                },
            },
            "additionalProperties": False,
        },
        "assemblyAxialSpring": {
            "type": "object",
            "required": [
                "kind",
                "stiffness_N_per_m",
                "initial_compression_m",
                "compression_per_axial_position",
            ],
            "properties": {
                "kind": {"const": "axial_spring"},
                "stiffness_N_per_m": number,
                "initial_compression_m": number,
                "compression_per_axial_position": number,
            },
            "additionalProperties": False,
        },
        "assemblyCentrifugalRamp": {
            "type": "object",
            "required": [
                "kind",
                "flyweight_mass_kg",
                "radius_at_zero_position_m",
                "radial_displacement_profile",
            ],
            "properties": {
                "kind": {"const": "centrifugal_ramp"},
                "flyweight_mass_kg": nonnegative,
                "radius_at_zero_position_m": number,
                "radial_displacement_profile": {
                    "$ref": "#/$defs/assemblyPiecewiseRamp"
                },
            },
            "additionalProperties": False,
        },
        "assemblyFixedPivotGeometry": {
            "type": "object",
            "required": [
                "pivot_axial_position_m",
                "pivot_radius_m",
                "arm_length_m",
                "roller_radius_m",
                "ramp_reference_axial_position_m",
                "ramp_reference_radius_m",
                "ramp_profile",
                "ramp_axial_direction",
                "axial_position_min_m",
                "axial_position_max_m",
                "roller_side_sign",
                "root_scan_points",
                "validation_positions",
                "root_residual_tolerance_m2",
                "coordinate_tolerance_m",
                "compilation_points",
            ],
            "properties": {
                "pivot_axial_position_m": number,
                "pivot_radius_m": number,
                "arm_length_m": positive,
                "roller_radius_m": positive,
                "ramp_reference_axial_position_m": number,
                "ramp_reference_radius_m": number,
                "ramp_profile": {"$ref": "#/$defs/assemblyPiecewiseRamp"},
                "ramp_axial_direction": {"type": "integer", "enum": [-1, 1]},
                "axial_position_min_m": number,
                "axial_position_max_m": number,
                "roller_side_sign": {"type": "integer", "enum": [-1, 1]},
                "root_scan_points": {"type": "integer", "minimum": 2},
                "validation_positions": {"type": "integer", "minimum": 2},
                "root_residual_tolerance_m2": positive,
                "coordinate_tolerance_m": positive,
                "compilation_points": {"type": "integer", "minimum": 2},
            },
            "additionalProperties": False,
        },
        "assemblyFlyweightMassGeometry": {
            "type": "object",
            "required": [
                "number_of_flyweights",
                "mass_per_flyweight_kg",
                "first_moment_u_kg_m",
                "first_moment_v_kg_m",
                "second_moment_u_kg_m2",
                "second_moment_v_kg_m2",
                "product_moment_uv_kg_m2",
                "second_moment_z_kg_m2",
            ],
            "properties": {
                "number_of_flyweights": {"type": "integer", "minimum": 1},
                "mass_per_flyweight_kg": nonnegative,
                "first_moment_u_kg_m": number,
                "first_moment_v_kg_m": number,
                "second_moment_u_kg_m2": nonnegative,
                "second_moment_v_kg_m2": nonnegative,
                "product_moment_uv_kg_m2": number,
                "second_moment_z_kg_m2": nonnegative,
            },
            "additionalProperties": False,
        },
        "assemblyFixedPivotFlyweight": {
            "type": "object",
            "required": ["kind", "geometry", "mass_geometry"],
            "properties": {
                "kind": {"const": "fixed_pivot_roller_flyweight"},
                "geometry": {"$ref": "#/$defs/assemblyFixedPivotGeometry"},
                "mass_geometry": {"$ref": "#/$defs/assemblyFlyweightMassGeometry"},
            },
            "additionalProperties": False,
        },
        "assemblyHelicalTorqueReaction": {
            "type": "object",
            "required": [
                "kind",
                "torsional_stiffness_Nm_per_rad",
                "initial_twist_rad",
                "movable_member_torque_fraction",
            ],
            "properties": {
                "kind": {"const": "helical_torque_reaction"},
                "torsional_stiffness_Nm_per_rad": number,
                "initial_twist_rad": number,
                "movable_member_torque_fraction": number,
            },
            "additionalProperties": False,
        },
        "assemblyForceLaw": {
            "oneOf": [
                {"$ref": "#/$defs/assemblyAxialSpring"},
                {"$ref": "#/$defs/assemblyCentrifugalRamp"},
                {"$ref": "#/$defs/assemblyFixedPivotFlyweight"},
                {"$ref": "#/$defs/assemblyHelicalTorqueReaction"},
            ]
        },
        "assemblyHelixProfile": {
            "type": "object",
            "required": ["kind", "circumferential_profile", "radius_m"],
            "properties": {
                "kind": {"const": "helix_profile"},
                "circumferential_profile": {"$ref": "#/$defs/assemblyPiecewiseRamp"},
                "radius_m": positive,
            },
            "additionalProperties": False,
        },
        "assemblyHelicalCoupling": {
            "type": "object",
            "required": [
                "profile",
                "opening_per_axial_position",
                "opening_offset_m",
            ],
            "properties": {
                "profile": {"$ref": "#/$defs/assemblyHelixProfile"},
                "opening_per_axial_position": number,
                "opening_offset_m": number,
            },
            "additionalProperties": False,
        },
        "assemblyPulley": {
            "type": "object",
            "required": ["components"],
            "properties": {
                "components": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/assemblyForceLaw"},
                },
                "helical_coupling": {"$ref": "#/$defs/assemblyHelicalCoupling"},
            },
            "additionalProperties": False,
        },
        "assemblyPulleys": {
            "type": "object",
            "required": ["primary", "secondary"],
            "properties": {
                "primary": {"$ref": "#/$defs/assemblyPulley"},
                "secondary": {"$ref": "#/$defs/assemblyPulley"},
            },
            "additionalProperties": False,
        },
    }


def _assembly_document_definition() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "schema_version",
            "document_type",
            "geometry",
            "contact",
            "inertias",
            "pulleys",
        ],
        "properties": {
            "schema_version": {"const": ASSEMBLY_DOCUMENT_SCHEMA_VERSION},
            "document_type": {"const": ASSEMBLY_DOCUMENT_TYPE},
            "geometry": {"$ref": "#/$defs/assemblyGeometry"},
            "contact": {"$ref": "#/$defs/assemblyContact"},
            "inertias": {"$ref": "#/$defs/assemblyInertias"},
            "pulleys": {"$ref": "#/$defs/assemblyPulleys"},
        },
        "additionalProperties": False,
    }


def assembly_document_json_schema() -> dict[str, Any]:
    """Return JSON Schema for CINDER's serialized CVT assembly document."""

    schema = _assembly_document_definition()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://cinder-cvt.local/schema/cvt-assembly.json",
        "title": "CINDER CVT assembly",
        **schema,
        "$defs": _assembly_definitions(),
    }


def _simulation_case_definitions() -> dict[str, Any]:
    number = _number()
    positive = _positive()

    return {
        "cvtState": {
            "type": "object",
            "required": [
                "primary_angular_speed_rad_per_s",
                "secondary_angular_speed_rad_per_s",
                "belt_speed_m_per_s",
                "shift_position_m",
                "shift_speed_m_per_s",
            ],
            "properties": {
                "primary_angular_speed_rad_per_s": number,
                "secondary_angular_speed_rad_per_s": number,
                "belt_speed_m_per_s": number,
                "shift_position_m": number,
                "shift_speed_m_per_s": number,
            },
            "additionalProperties": False,
        },
        "integrator": {
            "type": "object",
            "required": [
                "relative_tolerance",
                "absolute_tolerance",
                "method",
                "max_step",
                "first_step",
                "maximum_transitions",
                "event_time_tolerance",
                "retain_dense_output",
            ],
            "properties": {
                "relative_tolerance": positive,
                "absolute_tolerance": positive,
                "method": {"type": "string"},
                "max_step": {"type": ["number", "string"]},
                "first_step": {"type": ["number", "null"]},
                "maximum_transitions": {"type": "integer", "minimum": 1},
                "event_time_tolerance": positive,
                "retain_dense_output": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "reportingGridNative": {
            "type": "object",
            "required": ["kind", "count", "step_seconds"],
            "properties": {
                "kind": {"const": "native"},
                "count": {"type": "null"},
                "step_seconds": {"type": "null"},
            },
            "additionalProperties": False,
        },
        "reportingGridUniformCount": {
            "type": "object",
            "required": ["kind", "count", "step_seconds"],
            "properties": {
                "kind": {"const": "uniform_count"},
                "count": {"type": "integer", "minimum": 2},
                "step_seconds": {"type": "null"},
            },
            "additionalProperties": False,
        },
        "reportingGridUniformTimeStep": {
            "type": "object",
            "required": ["kind", "count", "step_seconds"],
            "properties": {
                "kind": {"const": "uniform_time_step"},
                "count": {"type": "null"},
                "step_seconds": positive,
            },
            "additionalProperties": False,
        },
        "reportingGrid": {
            "oneOf": [
                {"$ref": "#/$defs/reportingGridNative"},
                {"$ref": "#/$defs/reportingGridUniformCount"},
                {"$ref": "#/$defs/reportingGridUniformTimeStep"},
            ]
        },
        "reporting": {
            "type": "object",
            "required": [
                "grid",
                "include_contact",
                "include_actuation",
                "include_closure_audit",
                "include_integrated_observers",
            ],
            "properties": {
                "grid": {"$ref": "#/$defs/reportingGrid"},
                "include_contact": {"type": "boolean"},
                "include_actuation": {"type": "boolean"},
                "include_closure_audit": {"type": "boolean"},
                "include_integrated_observers": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }


def simulation_case_document_json_schema() -> dict[str, Any]:
    """Return JSON Schema for CINDER's composed simulation-case boundary.

    CINDER fully types the portions it owns: the CVT assembly, CVT state,
    integration settings, and reporting settings.  Host and shaft-boundary
    payloads are intentional extension slots, so their implementation-specific
    contents remain opaque here rather than becoming part of CINDER's core type
    contract.
    """

    defs = _assembly_definitions()
    defs.update(_simulation_case_definitions())
    defs["assemblyDocument"] = _assembly_document_definition()

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://cinder-cvt.local/schema/composed-simulation-case.json",
        "title": "CINDER composed CVT simulation case",
        "type": "object",
        "required": [
            "schema_version",
            "document_type",
            "assembly",
            "shaft_boundaries",
            "host",
            "scenario",
            "execution",
        ],
        "properties": {
            "schema_version": {"const": SIMULATION_CASE_SCHEMA_VERSION},
            "document_type": {"const": SIMULATION_CASE_DOCUMENT_TYPE},
            "assembly": {"$ref": "#/$defs/assemblyDocument"},
            "shaft_boundaries": {
                "type": "object",
                "required": ["primary", "secondary"],
                "properties": {
                    "primary": {"type": "object"},
                    "secondary": {"type": "object"},
                },
                "additionalProperties": False,
            },
            "host": {"type": "object"},
            "scenario": {
                "type": "object",
                "required": ["time_span_s", "initial_cvt_state"],
                "properties": {
                    "time_span_s": {
                        "type": "array",
                        "prefixItems": [_number(), _number()],
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "initial_cvt_state": {"$ref": "#/$defs/cvtState"},
                },
                "additionalProperties": False,
            },
            "execution": {
                "type": "object",
                "required": ["integrator", "reporting"],
                "properties": {
                    "integrator": {"$ref": "#/$defs/integrator"},
                    "reporting": {"$ref": "#/$defs/reporting"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
        "$defs": defs,
    }


def _field_expression_definition() -> dict[str, Any]:
    return {
        "oneOf": [
            {
                "type": "object",
                "required": ["op", "value"],
                "properties": {
                    "op": {"const": "literal"},
                    "value": {"type": "number"},
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["op"],
                "properties": {"op": {"const": "coordinate"}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["op", "key"],
                "properties": {
                    "op": {"const": "signal"},
                    "key": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["op", "args"],
                "properties": {
                    "op": {
                        "enum": [
                            "neg",
                            "abs",
                            "exp",
                            "expm1",
                            "sin",
                            "cos",
                            "sqrt",
                        ]
                    },
                    "args": {
                        "type": "array",
                        "prefixItems": [{"$ref": "#/$defs/fieldExpression"}],
                        "minItems": 1,
                        "maxItems": 1,
                    },
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["op", "args"],
                "properties": {
                    "op": {"enum": ["add", "sub", "mul", "div", "lt"]},
                    "args": {
                        "type": "array",
                        "prefixItems": [
                            {"$ref": "#/$defs/fieldExpression"},
                            {"$ref": "#/$defs/fieldExpression"},
                        ],
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["op", "args"],
                "properties": {
                    "op": {"const": "where"},
                    "args": {
                        "type": "array",
                        "prefixItems": [
                            {"$ref": "#/$defs/fieldExpression"},
                            {"$ref": "#/$defs/fieldExpression"},
                            {"$ref": "#/$defs/fieldExpression"},
                        ],
                        "minItems": 3,
                        "maxItems": 3,
                    },
                },
                "additionalProperties": False,
            },
        ]
    }


def _result_definitions() -> dict[str, Any]:
    nullable_number = _nullable_number()

    field_descriptor_properties = {
        "key": {"type": "string"},
        "label": {"type": "string"},
        "unit": {"type": "string"},
        "canonical_unit": {"type": "string"},
        "dimension": {"type": "string"},
        "description": {"type": "string"},
    }
    field_descriptor_required = list(field_descriptor_properties)

    return {
        "fieldExpression": _field_expression_definition(),
        "publicFieldDescriptor": {
            "type": "object",
            "required": field_descriptor_required,
            "properties": field_descriptor_properties,
            "additionalProperties": False,
        },
        "mode": {
            "type": "object",
            "required": ["engagement", "shift_constraint", "contact_mode"],
            "properties": {
                "engagement": {"type": ["string", "null"]},
                "shift_constraint": {"type": ["string", "null"]},
                "contact_mode": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
        "state": {
            "type": "object",
            "required": [
                "primary_angular_speed_rad_per_s",
                "secondary_angular_speed_rad_per_s",
                "belt_speed_m_per_s",
                "shift_position_m",
                "shift_speed_m_per_s",
            ],
            "properties": {
                "primary_angular_speed_rad_per_s": {"type": "number"},
                "secondary_angular_speed_rad_per_s": {"type": "number"},
                "belt_speed_m_per_s": {"type": "number"},
                "shift_position_m": {"type": "number"},
                "shift_speed_m_per_s": {"type": "number"},
            },
            "additionalProperties": False,
        },
        "reportColumn": {
            "type": "object",
            "required": field_descriptor_required + ["group", "values"],
            "properties": {
                **field_descriptor_properties,
                "group": {"type": "string"},
                "values": {
                    "type": "array",
                    "items": {"type": ["number", "null"]},
                },
            },
            "additionalProperties": False,
        },
        "reportSegmentRange": {
            "type": "object",
            "required": ["segment_index", "start_index", "end_index", "mode"],
            "properties": {
                "segment_index": {"type": "integer", "minimum": 0},
                "start_index": {"type": "integer", "minimum": 0},
                "end_index": {"type": "integer", "minimum": -1},
                "mode": {"$ref": "#/$defs/mode"},
            },
            "additionalProperties": False,
        },
        "reportTable": {
            "type": "object",
            "required": [
                "axis_key",
                "row_count",
                "columns",
                "segment_ranges",
                "preserves_duplicate_transition_times",
            ],
            "properties": {
                "axis_key": {"type": "string"},
                "row_count": {"type": "integer", "minimum": 0},
                "columns": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/reportColumn"},
                },
                "segment_ranges": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/reportSegmentRange"},
                },
                "preserves_duplicate_transition_times": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "spatialDomain": {
            "type": "object",
            "required": [
                "key",
                "label",
                "description",
                "periodic",
                "coordinate",
                "embedding",
                "regions",
            ],
            "properties": {
                "key": {"type": "string"},
                "label": {"type": "string"},
                "description": {"type": "string"},
                "periodic": {"type": "boolean"},
                "coordinate": {
                    "type": "object",
                    "required": ["key", "minimum", "maximum", "dimension", "meaning"],
                    "properties": {
                        "key": {"const": "u"},
                        "minimum": {"const": 0.0},
                        "maximum": {"const": 1.0},
                        "dimension": {"const": "dimensionless"},
                        "meaning": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "embedding": {
                    "type": "object",
                    "required": ["dimensions", "canonical_unit"],
                    "properties": {
                        "dimensions": {"const": 2},
                        "canonical_unit": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "regions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["key", "label", "length", "position"],
                        "properties": {
                            "key": {"type": "string"},
                            "label": {"type": "string"},
                            "length": {"$ref": "#/$defs/fieldExpression"},
                            "position": {
                                "type": "object",
                                "required": ["x", "y"],
                                "properties": {
                                    "x": {"$ref": "#/$defs/fieldExpression"},
                                    "y": {"$ref": "#/$defs/fieldExpression"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "spatialField": {
            "type": "object",
            "required": field_descriptor_required
            + ["group", "domain", "representation", "regions"],
            "properties": {
                **field_descriptor_properties,
                "group": {"type": "string"},
                "domain": {"type": "string"},
                "representation": {"const": "expression"},
                "regions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["key", "expression"],
                        "properties": {
                            "key": {"type": "string"},
                            "expression": {"$ref": "#/$defs/fieldExpression"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "metrics": {
            "type": "object",
            "required": [
                "duration_s",
                "completed",
                "termination_reason",
                "transition_count",
                "first_engagement_time_s",
                "primary_slip_duration_s",
                "secondary_slip_duration_s",
                "primary_angular_speed_max_rad_per_s",
                "secondary_angular_speed_max_rad_per_s",
                "vehicle_speed_max_m_per_s",
                "vehicle_distance_final_m",
                "ratio_min",
                "ratio_max",
                "ratio_final",
                "primary_traction_utilization_max",
                "secondary_traction_utilization_max",
                "primary_boundary_work_final_J",
                "secondary_boundary_work_final_J",
                "primary_slip_dissipation_final_J",
                "secondary_slip_dissipation_final_J",
            ],
            "properties": {
                "duration_s": {"type": "number"},
                "completed": {"type": "boolean"},
                "termination_reason": {"type": "string"},
                "transition_count": {"type": "integer", "minimum": 0},
                "first_engagement_time_s": nullable_number,
                "primary_slip_duration_s": {"type": "number"},
                "secondary_slip_duration_s": {"type": "number"},
                "primary_angular_speed_max_rad_per_s": nullable_number,
                "secondary_angular_speed_max_rad_per_s": nullable_number,
                "vehicle_speed_max_m_per_s": nullable_number,
                "vehicle_distance_final_m": nullable_number,
                "ratio_min": nullable_number,
                "ratio_max": nullable_number,
                "ratio_final": nullable_number,
                "primary_traction_utilization_max": nullable_number,
                "secondary_traction_utilization_max": nullable_number,
                "primary_boundary_work_final_J": nullable_number,
                "secondary_boundary_work_final_J": nullable_number,
                "primary_slip_dissipation_final_J": nullable_number,
                "secondary_slip_dissipation_final_J": nullable_number,
            },
            "additionalProperties": False,
        },
        "summary": {
            "type": "object",
            "required": [
                "duration_s",
                "segment_count",
                "transition_count",
                "final_state",
            ],
            "properties": {
                "duration_s": {"type": "number"},
                "segment_count": {"type": "integer", "minimum": 0},
                "transition_count": {"type": "integer", "minimum": 0},
                "final_state": {"$ref": "#/$defs/state"},
            },
            "additionalProperties": False,
        },
        "conventions": {
            "type": "object",
            "required": [
                "contract_version",
                "canonical_unit_system",
                "ratio",
                "shift_coordinate",
                "clamping_force_sign",
                "torque_sign",
                "report_grid",
            ],
            "properties": {
                "contract_version": {"const": CONVENTIONS_CONTRACT_VERSION},
                "canonical_unit_system": {"const": "SI"},
                "ratio": {
                    "type": "object",
                    "required": ["definition", "direction"],
                    "properties": {
                        "definition": {"type": "string"},
                        "direction": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "shift_coordinate": {"type": "string"},
                "clamping_force_sign": {"type": "string"},
                "torque_sign": {"type": "string"},
                "report_grid": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "transition": {
            "type": "object",
            "required": [
                "time_s",
                "previous_mode",
                "fired_event_names",
                "reason",
                "terminates",
                "metadata",
                "post_transition_state",
            ],
            "properties": {
                "time_s": {"type": "number"},
                "previous_mode": {"$ref": "#/$defs/mode"},
                "fired_event_names": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reason": {"type": "string"},
                "terminates": {"type": "boolean"},
                "metadata": _json_value_schema(),
                "post_transition_state": {"$ref": "#/$defs/state"},
            },
            "additionalProperties": False,
        },
        "reportedSignal": {
            "type": "object",
            "required": field_descriptor_required + ["group", "values"],
            "properties": {
                **field_descriptor_properties,
                "group": {"type": "string"},
                "values": {
                    "type": "array",
                    "items": {"type": ["number", "null"]},
                },
            },
            "additionalProperties": False,
        },
        "reportedSegment": {
            "type": "object",
            "required": ["mode", "time_s", "signals"],
            "properties": {
                "mode": {"$ref": "#/$defs/mode"},
                "time_s": {
                    "type": "array",
                    "items": {"type": ["number", "null"]},
                },
                "signals": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/reportedSignal"},
                },
            },
            "additionalProperties": False,
        },
        "rawStateColumn": {
            "type": "object",
            "required": field_descriptor_required + ["values"],
            "properties": {
                **field_descriptor_properties,
                "values": {
                    "type": "array",
                    "items": {"type": ["number", "null"]},
                },
            },
            "additionalProperties": False,
        },
        "rawTraceSegment": {
            "type": "object",
            "required": ["mode", "time_s", "state_columns"],
            "properties": {
                "mode": {"$ref": "#/$defs/mode"},
                "time_s": {
                    "type": "array",
                    "items": {"type": ["number", "null"]},
                },
                "state_columns": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/rawStateColumn"},
                },
            },
            "additionalProperties": False,
        },
        "rawTrace": {
            "type": "object",
            "required": ["kind", "segments"],
            "properties": {
                "kind": {"const": "adaptive_hybrid_trace"},
                "segments": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/rawTraceSegment"},
                },
            },
            "additionalProperties": False,
        },
    }


def simulation_result_json_schema() -> dict[str, Any]:
    """Return JSON Schema for ``project_simulation_result`` contract v2."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://cinder-cvt.local/schema/simulation-result.json",
        "title": "CINDER simulation result",
        "type": "object",
        "required": [
            "contract_version",
            "kind",
            "conventions",
            "metrics",
            "summary",
            "warnings",
            "report_table",
            "domains",
            "fields",
            "transitions",
        ],
        "properties": {
            "contract_version": {"const": SIMULATION_RESULT_CONTRACT_VERSION},
            "kind": {"const": "simulation_result"},
            "conventions": {"$ref": "#/$defs/conventions"},
            "metrics": {"$ref": "#/$defs/metrics"},
            "summary": {"$ref": "#/$defs/summary"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "report_table": {"$ref": "#/$defs/reportTable"},
            "domains": {
                "type": "array",
                "items": {"$ref": "#/$defs/spatialDomain"},
            },
            "fields": {
                "type": "array",
                "items": {"$ref": "#/$defs/spatialField"},
            },
            "transitions": {
                "type": "array",
                "items": {"$ref": "#/$defs/transition"},
            },
            "reported_segments": {
                "type": "array",
                "items": {"$ref": "#/$defs/reportedSegment"},
            },
            "raw_trace": {"$ref": "#/$defs/rawTrace"},
        },
        "additionalProperties": False,
        "$defs": _result_definitions(),
    }
