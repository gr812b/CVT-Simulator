"""JSON Schema for CINDER's composed simulation document contract."""

from __future__ import annotations

from typing import Any

from .conventions import PUBLIC_CONTRACT_VERSION
from .simulation_document import SIMULATION_CASE_DOCUMENT_TYPE


def simulation_case_document_json_schema() -> dict[str, Any]:
    """Return a frontend-neutral JSON Schema for composed simulation documents."""

    number = {"type": "number"}
    nonnegative = {"type": "number", "minimum": 0.0}
    positive = {"type": "number", "exclusiveMinimum": 0.0}

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
            "schema_version": {"const": PUBLIC_CONTRACT_VERSION},
            "document_type": {"const": SIMULATION_CASE_DOCUMENT_TYPE},
            "assembly": {"type": "object"},
            "shaft_boundaries": {
                "type": "object",
                "required": ["primary", "secondary"],
                "properties": {
                    "primary": {"$ref": "#/$defs/shaftBoundary"},
                    "secondary": {"$ref": "#/$defs/shaftBoundary"},
                },
                "additionalProperties": False,
            },
            "host": {"$ref": "#/$defs/host"},
            "scenario": {
                "type": "object",
                "required": ["time_span_s", "initial_cvt_state"],
                "properties": {
                    "time_span_s": {
                        "type": "array",
                        "prefixItems": [number, number],
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
        "$defs": {
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
            "shaftBoundary": {
                "oneOf": [
                    {"$ref": "#/$defs/fixedShaftBoundary"},
                    {"$ref": "#/$defs/fullThrottleEngineBoundary"},
                    {"$ref": "#/$defs/lockedFinalDriveBoundary"},
                ]
            },
            "fixedShaftBoundary": {
                "type": "object",
                "required": ["kind", "external_torque_Nm", "equivalent_inertia_kg_m2"],
                "properties": {
                    "kind": {"const": "fixed_shaft"},
                    "external_torque_Nm": number,
                    "equivalent_inertia_kg_m2": nonnegative,
                },
                "additionalProperties": False,
            },
            "fullThrottleEngineBoundary": {
                "type": "object",
                "required": [
                    "kind",
                    "points",
                    "low_speed_braking_torque_Nm",
                    "low_speed_braking_peak_speed_rad_per_s",
                    "high_speed_braking_torque_Nm",
                    "high_speed_braking_transition_width_rad_per_s",
                    "equivalent_rotational_inertia_kg_m2",
                ],
                "properties": {
                    "kind": {"const": "full_throttle_engine"},
                    "points": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "type": "object",
                            "required": ["angular_speed_rad_per_s", "torque_Nm"],
                            "properties": {
                                "angular_speed_rad_per_s": positive,
                                "torque_Nm": number,
                            },
                            "additionalProperties": False,
                        },
                    },
                    "low_speed_braking_torque_Nm": number,
                    "low_speed_braking_peak_speed_rad_per_s": positive,
                    "high_speed_braking_torque_Nm": number,
                    "high_speed_braking_transition_width_rad_per_s": positive,
                    "equivalent_rotational_inertia_kg_m2": nonnegative,
                },
                "additionalProperties": False,
            },
            "lockedFinalDriveBoundary": {
                "type": "object",
                "required": [
                    "kind",
                    "vehicle",
                    "final_drive",
                    "road_load",
                    "road_profile",
                    "direct_secondary_shaft_inertia_kg_m2",
                ],
                "properties": {
                    "kind": {"const": "locked_final_drive"},
                    "vehicle": {
                        "type": "object",
                        "required": ["mass_kg", "wheel_rotational_inertia_kg_m2"],
                        "properties": {
                            "mass_kg": positive,
                            "wheel_rotational_inertia_kg_m2": nonnegative,
                        },
                        "additionalProperties": False,
                    },
                    "final_drive": {
                        "type": "object",
                        "required": ["reduction_ratio", "wheel_radius_m"],
                        "properties": {
                            "reduction_ratio": positive,
                            "wheel_radius_m": positive,
                        },
                        "additionalProperties": False,
                    },
                    "road_load": {
                        "type": "object",
                        "required": [
                            "rolling_resistance_coefficient",
                            "drag_coefficient",
                            "frontal_area_m2",
                            "air_density_kg_per_m3",
                            "gravity_m_per_s2",
                            "rolling_speed_regularization_m_per_s",
                        ],
                        "properties": {
                            "rolling_resistance_coefficient": nonnegative,
                            "drag_coefficient": nonnegative,
                            "frontal_area_m2": nonnegative,
                            "air_density_kg_per_m3": positive,
                            "gravity_m_per_s2": positive,
                            "rolling_speed_regularization_m_per_s": positive,
                        },
                        "additionalProperties": False,
                    },
                    "road_profile": {"$ref": "#/$defs/roadProfile"},
                    "direct_secondary_shaft_inertia_kg_m2": nonnegative,
                },
                "additionalProperties": False,
            },
            "roadProfile": {
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["kind", "grade_angle_rad"],
                        "properties": {
                            "kind": {"const": "constant_grade"},
                            "grade_angle_rad": number,
                        },
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "required": ["kind", "segments"],
                        "properties": {
                            "kind": {"const": "piecewise_constant_grade"},
                            "segments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["start_distance_m", "grade_angle_rad"],
                                    "properties": {
                                        "start_distance_m": nonnegative,
                                        "grade_angle_rad": number,
                                    },
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "additionalProperties": False,
                    },
                ]
            },
            "host": {
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["kind", "initial_state"],
                        "properties": {
                            "kind": {"const": "secondary_shaft_angle"},
                            "initial_state": {
                                "type": "object",
                                "required": ["secondary_shaft_angle_rad"],
                                "properties": {"secondary_shaft_angle_rad": number},
                                "additionalProperties": False,
                            },
                        },
                        "additionalProperties": False,
                    }
                ]
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
            "reporting": {"type": "object"},
        },
    }
