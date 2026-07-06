"""Standard JSON Schema exports for CINDER's public version-one documents.

The schemas describe only the stable, JSON-facing contracts in
:mod:`cinder.contracts`.  They intentionally do not reflect or import CINDER's
internal dataclasses.  HTTP adapters and frontend build tools can consume these
schemas for validation and type generation while mechanics/execution remain
independent of transport concerns.
"""

from __future__ import annotations

from typing import Any

from .conventions import PUBLIC_CONTRACT_VERSION
from .document import ASSEMBLY_DOCUMENT_TYPE
from .simulation_document import SIMULATION_CASE_DOCUMENT_TYPE

_JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def simulation_case_document_json_schema() -> dict[str, Any]:
    """Return the complete JSON Schema for CINDER's v1 simulation document.

    The result is a new ordinary dictionary on each call so external callers
    may serialize or annotate it without mutating CINDER module state.
    """

    return {
        "$schema": _JSON_SCHEMA_DRAFT,
        "$id": "https://cinder-cvt.dev/schemas/cinder_simulation_case.v1.json",
        "title": "CINDER simulation case document",
        "description": (
            "Version-one executable CINDER simulation case. All physical values "
            "use canonical SI units."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "document_type",
            "assembly",
            "input_boundary",
            "output_boundary",
            "scenario",
            "execution",
        ],
        "properties": {
            "schema_version": {"const": PUBLIC_CONTRACT_VERSION},
            "document_type": {"const": SIMULATION_CASE_DOCUMENT_TYPE},
            "assembly": {"$ref": "#/$defs/assembly"},
            "input_boundary": {"$ref": "#/$defs/inputBoundary"},
            "output_boundary": {"$ref": "#/$defs/outputBoundary"},
            "scenario": {"$ref": "#/$defs/scenario"},
            "execution": {"$ref": "#/$defs/execution"},
        },
        "$defs": _definitions(),
    }


def _definitions() -> dict[str, Any]:
    number = {"type": "number"}
    nonnegative = {"type": "number", "minimum": 0.0}
    positive = {"type": "number", "exclusiveMinimum": 0.0}
    integer_nonnegative = {"type": "integer", "minimum": 0}

    def object_schema(
        properties: dict[str, Any],
        required: list[str],
        *,
        additional: bool = False,
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": additional,
            "properties": properties,
            "required": required,
        }

    ramp_segment = {
        "oneOf": [
            object_schema(
                {
                    "kind": {"const": "linear_segment"},
                    "length_m": positive,
                    "angle_rad": number,
                },
                ["kind", "length_m", "angle_rad"],
            ),
            object_schema(
                {
                    "kind": {"const": "circular_segment"},
                    "length_m": positive,
                    "angle_start_rad": number,
                    "angle_end_rad": number,
                    "quadrant": {"type": "integer", "enum": [-1, 1]},
                },
                [
                    "kind",
                    "length_m",
                    "angle_start_rad",
                    "angle_end_rad",
                    "quadrant",
                ],
            ),
        ]
    }

    piecewise_ramp = object_schema(
        {
            "kind": {"const": "piecewise_ramp"},
            "segments": {
                "type": "array",
                "minItems": 1,
                "items": ramp_segment,
            },
        },
        ["kind", "segments"],
    )

    helix_profile = object_schema(
        {
            "kind": {"const": "helix_profile"},
            "circumferential_profile": piecewise_ramp,
            "radius_m": positive,
            "theta_offset_rad": number,
        },
        ["kind", "circumferential_profile", "radius_m", "theta_offset_rad"],
    )

    pulley_component = {
        "oneOf": [
            object_schema(
                {
                    "kind": {"const": "axial_spring"},
                    "stiffness_N_per_m": positive,
                    "initial_compression_m": number,
                    "compression_per_axial_position": number,
                },
                [
                    "kind",
                    "stiffness_N_per_m",
                    "initial_compression_m",
                    "compression_per_axial_position",
                ],
            ),
            object_schema(
                {
                    "kind": {"const": "centrifugal_ramp"},
                    "flyweight_mass_kg": positive,
                    "radius_at_zero_position_m": nonnegative,
                    "radial_displacement_profile": piecewise_ramp,
                },
                [
                    "kind",
                    "flyweight_mass_kg",
                    "radius_at_zero_position_m",
                    "radial_displacement_profile",
                ],
            ),
            object_schema(
                {
                    "kind": {"const": "helical_torque_reaction"},
                    "torsional_stiffness_Nm_per_rad": positive,
                    "initial_twist_rad": number,
                    "movable_member_torque_fraction": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
                [
                    "kind",
                    "torsional_stiffness_Nm_per_rad",
                    "initial_twist_rad",
                    "movable_member_torque_fraction",
                ],
            ),
        ]
    }

    pulley = object_schema(
        {
            "components": {
                "type": "array",
                "minItems": 1,
                "items": pulley_component,
            },
            "helical_coupling": {
                "anyOf": [
                    {"type": "null"},
                    object_schema(
                        {
                            "opening_per_axial_position": number,
                            "opening_offset_m": number,
                            "profile": helix_profile,
                        },
                        [
                            "opening_per_axial_position",
                            "opening_offset_m",
                            "profile",
                        ],
                    ),
                ]
            },
        },
        ["components"],
    )

    belt = object_schema(
        {
            "height_m": positive,
            "outer_width_m": positive,
            "inner_width_m": positive,
            "cord_depth_from_outer_m": nonnegative,
        },
        ["height_m", "outer_width_m", "inner_width_m", "cord_depth_from_outer_m"],
    )

    geometry = object_schema(
        {
            "belt": belt,
            "belt_outer_length_m": positive,
            "primary_outer_radius_at_zero_shift_m": positive,
            "secondary_outer_radius_at_zero_shift_m": positive,
            "sheave_half_angle_rad": {
                "type": "number",
                "exclusiveMinimum": 0.0,
                "exclusiveMaximum": 1.5707963267948966,
            },
            "deadzone_shift_m": nonnegative,
            "max_shift_m": nonnegative,
        },
        [
            "belt",
            "belt_outer_length_m",
            "primary_outer_radius_at_zero_shift_m",
            "secondary_outer_radius_at_zero_shift_m",
            "sheave_half_angle_rad",
            "deadzone_shift_m",
            "max_shift_m",
        ],
    )

    assembly = object_schema(
        {
            "schema_version": {"const": PUBLIC_CONTRACT_VERSION},
            "document_type": {"const": ASSEMBLY_DOCUMENT_TYPE},
            "geometry": geometry,
            "contact": object_schema(
                {"friction_coefficient": nonnegative}, ["friction_coefficient"]
            ),
            "inertias": object_schema(
                {
                    "primary": object_schema(
                        {
                            "engine_rotational_inertia_kg_m2": nonnegative,
                            "cvt_rotational_inertia_kg_m2": nonnegative,
                            "moving_sheave_mass_kg": nonnegative,
                        },
                        [
                            "engine_rotational_inertia_kg_m2",
                            "cvt_rotational_inertia_kg_m2",
                            "moving_sheave_mass_kg",
                        ],
                    ),
                    "secondary": object_schema(
                        {
                            "fixed_rotational_inertia_kg_m2": nonnegative,
                            "gearbox_input_rotational_inertia_kg_m2": nonnegative,
                            "movable_sheave_rotational_inertia_kg_m2": nonnegative,
                            "moving_sheave_mass_kg": nonnegative,
                        },
                        [
                            "fixed_rotational_inertia_kg_m2",
                            "gearbox_input_rotational_inertia_kg_m2",
                            "movable_sheave_rotational_inertia_kg_m2",
                            "moving_sheave_mass_kg",
                        ],
                    ),
                    "belt_density_kg_per_m3": positive,
                },
                ["primary", "secondary", "belt_density_kg_per_m3"],
            ),
            "pulleys": object_schema(
                {"input": pulley, "output": pulley}, ["input", "output"]
            ),
        },
        [
            "schema_version",
            "document_type",
            "geometry",
            "contact",
            "inertias",
            "pulleys",
        ],
    )

    input_boundary = object_schema(
        {
            "kind": {"const": "full_throttle_torque_curve"},
            "points": {
                "type": "array",
                "minItems": 2,
                "items": object_schema(
                    {"angular_speed_rad_per_s": nonnegative, "torque_Nm": number},
                    ["angular_speed_rad_per_s", "torque_Nm"],
                ),
            },
            "low_speed_braking_torque_Nm": number,
            "low_speed_braking_peak_speed_rad_per_s": nonnegative,
            "high_speed_braking_torque_Nm": number,
            "high_speed_braking_transition_width_rad_per_s": nonnegative,
        },
        [
            "kind",
            "points",
            "low_speed_braking_torque_Nm",
            "low_speed_braking_peak_speed_rad_per_s",
            "high_speed_braking_torque_Nm",
            "high_speed_braking_transition_width_rad_per_s",
        ],
    )

    fixed_output = object_schema(
        {
            "kind": {"const": "fixed_output_load"},
            "external_torque_Nm": number,
            "added_rotational_inertia_kg_m2": nonnegative,
        },
        ["kind", "external_torque_Nm", "added_rotational_inertia_kg_m2"],
    )
    vehicle_output = object_schema(
        {
            "kind": {"const": "locked_final_drive_vehicle"},
            "vehicle": object_schema(
                {
                    "mass_kg": positive,
                    "wheel_rotational_inertia_kg_m2": nonnegative,
                },
                ["mass_kg", "wheel_rotational_inertia_kg_m2"],
            ),
            "final_drive": object_schema(
                {"reduction_ratio": positive, "wheel_radius_m": positive},
                ["reduction_ratio", "wheel_radius_m"],
            ),
            "road_load": object_schema(
                {
                    "rolling_resistance_coefficient": nonnegative,
                    "drag_coefficient": nonnegative,
                    "frontal_area_m2": nonnegative,
                    "air_density_kg_per_m3": nonnegative,
                    "gravity_m_per_s2": positive,
                    "rolling_speed_regularization_m_per_s": positive,
                },
                [
                    "rolling_resistance_coefficient",
                    "drag_coefficient",
                    "frontal_area_m2",
                    "air_density_kg_per_m3",
                    "gravity_m_per_s2",
                    "rolling_speed_regularization_m_per_s",
                ],
            ),
            "road_profile": object_schema(
                {"kind": {"const": "constant_grade"}, "grade_angle_rad": number},
                ["kind", "grade_angle_rad"],
            ),
        },
        ["kind", "vehicle", "final_drive", "road_load", "road_profile"],
    )

    initial_state = object_schema(
        {
            "primary_angular_speed_rad_per_s": number,
            "secondary_angular_speed_rad_per_s": number,
            "belt_speed_m_per_s": number,
            "shift_position_m": number,
            "shift_speed_m_per_s": number,
            "secondary_shaft_angle_rad": number,
        },
        [
            "primary_angular_speed_rad_per_s",
            "secondary_angular_speed_rad_per_s",
            "belt_speed_m_per_s",
            "shift_position_m",
            "shift_speed_m_per_s",
            "secondary_shaft_angle_rad",
        ],
    )
    slip_direction = {
        "anyOf": [
            {"type": "null"},
            {
                "enum": [
                    "belt_leads_pulley",
                    "pulley_leads_belt",
                    "indeterminate",
                ]
            },
        ]
    }
    contact_regime = {
        "anyOf": [
            {"type": "null"},
            object_schema(
                {
                    "mode": {
                        "enum": [
                            "stick_stick",
                            "primary_slip_secondary_stick",
                            "primary_stick_secondary_slip",
                            "both_slip",
                        ]
                    },
                    "primary_slip_direction": slip_direction,
                    "secondary_slip_direction": slip_direction,
                },
                [
                    "mode",
                    "primary_slip_direction",
                    "secondary_slip_direction",
                ],
            ),
        ]
    }
    initial_mode = {
        "anyOf": [
            {"type": "null"},
            object_schema(
                {
                    "engagement": {"enum": ["deadzone", "engaged"]},
                    "shift_constraint": {
                        "enum": ["free", "lower_stop", "low_ratio_seat", "upper_stop"]
                    },
                    "contact_regime": contact_regime,
                },
                ["engagement", "shift_constraint", "contact_regime"],
            ),
        ]
    }
    scenario = object_schema(
        {
            "time_span_s": {
                "type": "array",
                "prefixItems": [number, number],
                "items": False,
                "minItems": 2,
                "maxItems": 2,
            },
            "initial_state": initial_state,
            "initial_mode": initial_mode,
        },
        ["time_span_s", "initial_state", "initial_mode"],
    )

    execution = object_schema(
        {
            "traction_law": object_schema(
                {
                    "primary_static_lambda_limit": nonnegative,
                    "secondary_static_lambda_limit": nonnegative,
                    "primary_kinetic_lambda_magnitude": nonnegative,
                    "secondary_kinetic_lambda_magnitude": nonnegative,
                },
                [
                    "primary_static_lambda_limit",
                    "secondary_static_lambda_limit",
                    "primary_kinetic_lambda_magnitude",
                    "secondary_kinetic_lambda_magnitude",
                ],
            ),
            "solve_settings": object_schema(
                {
                    "lambda_search_bounds": object_schema(
                        {
                            "primary_lower": number,
                            "primary_upper": number,
                            "secondary_lower": number,
                            "secondary_upper": number,
                        },
                        [
                            "primary_lower",
                            "primary_upper",
                            "secondary_lower",
                            "secondary_upper",
                        ],
                    ),
                    "initial_guess": object_schema(
                        {"primary_lambda": number, "secondary_lambda": number},
                        ["primary_lambda", "secondary_lambda"],
                    ),
                    "contact_tolerances": object_schema(
                        {
                            "relative_speed_tolerance_m_per_s": nonnegative,
                            "relative_acceleration_tolerance_m_per_s2": nonnegative,
                            "stick_acceleration_tolerance_m_per_s2": nonnegative,
                        },
                        [
                            "relative_speed_tolerance_m_per_s",
                            "relative_acceleration_tolerance_m_per_s2",
                            "stick_acceleration_tolerance_m_per_s2",
                        ],
                    ),
                    "optimizer_tolerance": positive,
                    "maximum_function_evaluations": integer_nonnegative,
                    "maximum_closure_condition_number": positive,
                },
                [
                    "lambda_search_bounds",
                    "initial_guess",
                    "contact_tolerances",
                    "optimizer_tolerance",
                    "maximum_function_evaluations",
                    "maximum_closure_condition_number",
                ],
            ),
            "operating_limits": object_schema(
                {
                    "lower_stop_shift_m": number,
                    "engagement_shift_m": number,
                    "upper_stop_shift_m": number,
                },
                ["lower_stop_shift_m", "engagement_shift_m", "upper_stop_shift_m"],
            ),
            "switching_settings": object_schema(
                {
                    "stick_exit_static_margin": nonnegative,
                    "restick_static_margin": nonnegative,
                    "normal_resultant_floor_N": nonnegative,
                },
                [
                    "stick_exit_static_margin",
                    "restick_static_margin",
                    "normal_resultant_floor_N",
                ],
            ),
            "integrator": object_schema(
                {
                    "relative_tolerance": positive,
                    "absolute_tolerance": positive,
                    "method": {"type": "string", "minLength": 1},
                    "max_step_s": positive,
                    "first_step_s": {"anyOf": [{"type": "null"}, positive]},
                    "maximum_transitions": integer_nonnegative,
                    "event_time_tolerance_s": positive,
                    "retain_dense_output": {"type": "boolean"},
                },
                [
                    "relative_tolerance",
                    "absolute_tolerance",
                    "method",
                    "max_step_s",
                    "first_step_s",
                    "maximum_transitions",
                    "event_time_tolerance_s",
                    "retain_dense_output",
                ],
            ),
            "reporting": object_schema(
                {
                    "grid": {
                        "oneOf": [
                            object_schema(
                                {
                                    "kind": {"const": "native"},
                                    "count": {"type": "null"},
                                    "step_seconds": {"type": "null"},
                                },
                                ["kind", "count", "step_seconds"],
                            ),
                            object_schema(
                                {
                                    "kind": {"const": "uniform_count"},
                                    "count": {"type": "integer", "minimum": 2},
                                    "step_seconds": {"type": "null"},
                                },
                                ["kind", "count", "step_seconds"],
                            ),
                            object_schema(
                                {
                                    "kind": {"const": "uniform_time_step"},
                                    "count": {"type": "null"},
                                    "step_seconds": positive,
                                },
                                ["kind", "count", "step_seconds"],
                            ),
                        ]
                    },
                    "include_contact": {"type": "boolean"},
                    "include_actuation": {"type": "boolean"},
                    "include_closure_audit": {"type": "boolean"},
                    "include_integrated_observers": {"type": "boolean"},
                },
                [
                    "grid",
                    "include_contact",
                    "include_actuation",
                    "include_closure_audit",
                    "include_integrated_observers",
                ],
            ),
        },
        [
            "traction_law",
            "solve_settings",
            "operating_limits",
            "switching_settings",
            "integrator",
            "reporting",
        ],
    )

    return {
        "assembly": assembly,
        "inputBoundary": input_boundary,
        "outputBoundary": {"oneOf": [fixed_output, vehicle_output]},
        "scenario": scenario,
        "execution": execution,
    }
