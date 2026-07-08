"""Public editable-field schema for CINDER simulation-case documents.

The schema deliberately describes the JSON document, not internal dataclasses.
A backend can expose it directly and a frontend can render generic quantity
inputs, lists, and discriminated variants without owning a second parameter
map.  Layout, product wording, and beginner/advanced presentation remain
application concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .catalog import component_catalog_document
from .conventions import PUBLIC_CONTRACT_VERSION, describe_public_field
from .simulation_document import SIMULATION_CASE_DOCUMENT_TYPE

ValueKind = Literal["number", "integer", "boolean", "string", "enum", "object", "array"]
Exposure = Literal["design", "scenario", "advanced_execution"]


@dataclass(frozen=True, slots=True)
class EditableFieldDescriptor:
    """One path-addressable editable document field.

    ``path_template`` is a JSON Pointer template. ``*`` denotes one repeated
    array item, for example ``/input_boundary/points/*/torque_Nm``.  Callers
    substitute a numeric index before patching a concrete document.
    """

    path_template: str
    label: str
    value_kind: ValueKind
    section: str
    description: str = ""
    exposure: Exposure | None = None
    dimension: str | None = None
    canonical_unit: str | None = None
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    enum_values: tuple[str, ...] = ()
    when: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.exposure is None:
            object.__setattr__(self, "exposure", _default_exposure(self.section))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path_template": self.path_template,
            "label": self.label,
            "value_kind": self.value_kind,
            "section": self.section,
            "exposure": self.exposure,
            "description": self.description,
            "required": self.required,
        }
        if self.dimension is not None:
            payload["dimension"] = self.dimension
        if self.canonical_unit is not None:
            payload["canonical_unit"] = self.canonical_unit
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.enum_values:
            payload["enum_values"] = list(self.enum_values)
        if self.when is not None:
            payload["when"] = dict(self.when)
        return payload


def _default_exposure(section: str) -> Exposure:
    """Classify schema fields without turning sections into UI layout rules."""

    if section.startswith("Execution"):
        return "advanced_execution"
    if section in {"Input boundary", "Output boundary", "Scenario"}:
        return "scenario"
    return "design"


def _quantity(
    path_template: str,
    key: str,
    *,
    section: str,
    required: bool = True,
    minimum: float | None = None,
    maximum: float | None = None,
    description: str | None = None,
    when: Mapping[str, str] | None = None,
) -> EditableFieldDescriptor:
    descriptor = describe_public_field(key)
    return EditableFieldDescriptor(
        path_template=path_template,
        label=descriptor.label,
        value_kind="number",
        section=section,
        description=description if description is not None else descriptor.description,
        dimension=descriptor.dimension,
        canonical_unit=descriptor.unit,
        required=required,
        minimum=minimum,
        maximum=maximum,
        when=when,
    )


def editable_simulation_case_schema() -> dict[str, Any]:
    """Return JSON-safe metadata for all built-in Phase-1 document fields.

    It covers the scalar fields in the current version-one simulation document
    plus the list/object discriminators needed to render torque curves, pulley
    components, ramp segments, and supported output boundaries.  It is not a
    product form layout and does not attempt to recommend CVT settings.
    """

    fields = _fields()
    return {
        "contract_version": PUBLIC_CONTRACT_VERSION,
        "document_type": "cinder_editable_document_schema",
        "target_document_type": SIMULATION_CASE_DOCUMENT_TYPE,
        "pointer_syntax": "RFC 6901 JSON Pointer; '*' in a template denotes one array item.",
        "supported_discriminators": {
            "/input_boundary/kind": ["full_throttle_torque_curve"],
            "/output_boundary/kind": [
                "fixed_output_load",
                "locked_final_drive_vehicle",
            ],
            "/output_boundary/road_profile/kind": ["constant_grade"],
            "/execution/reporting/grid/kind": [
                "native",
                "uniform_count",
                "uniform_time_step",
            ],
            "/assembly/pulleys/input/components/*/kind": [
                "axial_spring",
                "centrifugal_ramp",
            ],
            "/assembly/pulleys/output/components/*/kind": [
                "axial_spring",
                "helical_torque_reaction",
            ],
            "/assembly/pulleys/*/components/*/radial_displacement_profile/segments/*/kind": [
                "linear_segment",
                "circular_segment",
            ],
        },
        "fields": [field.as_dict() for field in fields],
        "field_exposures": ["design", "scenario", "advanced_execution"],
        "component_catalog": component_catalog_document(),
    }


def _fields() -> tuple[EditableFieldDescriptor, ...]:
    geometry = "Assembly / geometry"
    inertia = "Assembly / inertia"
    contact = "Assembly / contact"
    input_boundary = "Input boundary"
    output_boundary = "Output boundary"
    scenario = "Scenario"
    execution = "Execution"
    reporting = "Execution / reporting"

    return (
        # Assembly geometry -------------------------------------------------
        _quantity(
            "/assembly/geometry/belt/height_m",
            "belt_height_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/belt/outer_width_m",
            "belt_outer_width_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/belt/inner_width_m",
            "belt_inner_width_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/belt/cord_depth_from_outer_m",
            "belt_cord_depth_from_outer_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/belt_outer_length_m",
            "belt_outer_length_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/primary_outer_radius_at_zero_shift_m",
            "primary_outer_radius_at_zero_shift_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/secondary_outer_radius_at_zero_shift_m",
            "secondary_outer_radius_at_zero_shift_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/sheave_half_angle_rad",
            "sheave_half_angle_rad",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/deadzone_shift_m",
            "deadzone_shift_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/geometry/max_shift_m",
            "max_shift_m",
            section=geometry,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/contact/friction_coefficient",
            "friction_coefficient",
            section=contact,
            minimum=0.0,
        ),
        # Inertia -----------------------------------------------------------
        _quantity(
            "/assembly/inertias/primary/rotating_hardware_inertia_kg_m2",
            "primary_rotating_hardware_inertia_kg_m2",
            section=inertia,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/inertias/primary/moving_sheave_mass_kg",
            "primary_moving_sheave_mass_kg",
            section=inertia,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/inertias/secondary/fixed_rotating_hardware_inertia_kg_m2",
            "secondary_fixed_rotating_hardware_inertia_kg_m2",
            section=inertia,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/inertias/secondary/movable_sheave_rotational_inertia_kg_m2",
            "secondary_movable_sheave_rotational_inertia_kg_m2",
            section=inertia,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/inertias/secondary/moving_sheave_mass_kg",
            "secondary_moving_sheave_mass_kg",
            section=inertia,
            minimum=0.0,
        ),
        _quantity(
            "/assembly/inertias/belt_density_kg_per_m3",
            "belt_density_kg_per_m3",
            section=inertia,
            minimum=0.0,
        ),
        # Input boundary ----------------------------------------------------
        _quantity(
            "/input_boundary/points/*/angular_speed_rad_per_s",
            "angular_speed_rad_per_s",
            section=input_boundary,
            minimum=0.0,
        ),
        _quantity(
            "/input_boundary/points/*/torque_Nm", "torque_Nm", section=input_boundary
        ),
        _quantity(
            "/input_boundary/low_speed_braking_torque_Nm",
            "low_speed_braking_torque_Nm",
            section=input_boundary,
            maximum=0.0,
        ),
        _quantity(
            "/input_boundary/low_speed_braking_peak_speed_rad_per_s",
            "low_speed_braking_peak_speed_rad_per_s",
            section=input_boundary,
            minimum=0.0,
        ),
        _quantity(
            "/input_boundary/high_speed_braking_torque_Nm",
            "high_speed_braking_torque_Nm",
            section=input_boundary,
            maximum=0.0,
        ),
        _quantity(
            "/input_boundary/high_speed_braking_transition_width_rad_per_s",
            "high_speed_braking_transition_width_rad_per_s",
            section=input_boundary,
            minimum=0.0,
        ),
        _quantity(
            "/input_boundary/equivalent_rotational_inertia_kg_m2",
            "input_equivalent_rotational_inertia_kg_m2",
            section=input_boundary,
            minimum=0.0,
        ),
        # Fixed output boundary --------------------------------------------
        _quantity(
            "/output_boundary/load_torque_Nm",
            "load_torque_Nm",
            section=output_boundary,
            when={"/output_boundary/kind": "fixed_output_load"},
        ),
        _quantity(
            "/output_boundary/equivalent_rotational_inertia_kg_m2",
            "output_equivalent_rotational_inertia_kg_m2",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "fixed_output_load"},
        ),
        # Locked vehicle boundary ------------------------------------------
        _quantity(
            "/output_boundary/vehicle/mass_kg",
            "vehicle_mass_kg",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/vehicle/wheel_rotational_inertia_kg_m2",
            "wheel_rotational_inertia_kg_m2",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/final_drive/reduction_ratio",
            "reduction_ratio",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/final_drive/wheel_radius_m",
            "wheel_radius_m",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_load/rolling_resistance_coefficient",
            "rolling_resistance_coefficient",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_load/drag_coefficient",
            "drag_coefficient",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_load/frontal_area_m2",
            "frontal_area_m2",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_load/air_density_kg_per_m3",
            "air_density_kg_per_m3",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_load/gravity_m_per_s2",
            "gravity_m_per_s2",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_load/rolling_speed_regularization_m_per_s",
            "rolling_speed_regularization_m_per_s",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/road_profile/grade_angle_rad",
            "grade_angle_rad",
            section=output_boundary,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        _quantity(
            "/output_boundary/direct_secondary_shaft_inertia_kg_m2",
            "direct_secondary_shaft_inertia_kg_m2",
            section=output_boundary,
            minimum=0.0,
            when={"/output_boundary/kind": "locked_final_drive_vehicle"},
        ),
        # Scenario ----------------------------------------------------------
        _quantity("/scenario/time_span_s/0", "start_time_s", section=scenario),
        _quantity("/scenario/time_span_s/1", "end_time_s", section=scenario),
        _quantity(
            "/scenario/initial_state/primary_angular_speed_rad_per_s",
            "primary_angular_speed_rad_per_s",
            section=scenario,
        ),
        _quantity(
            "/scenario/initial_state/secondary_angular_speed_rad_per_s",
            "secondary_angular_speed_rad_per_s",
            section=scenario,
        ),
        _quantity(
            "/scenario/initial_state/belt_speed_m_per_s",
            "belt_speed_m_per_s",
            section=scenario,
        ),
        _quantity(
            "/scenario/initial_state/shift_position_m",
            "shift_position_m",
            section=scenario,
        ),
        _quantity(
            "/scenario/initial_state/shift_speed_m_per_s",
            "shift_speed_m_per_s",
            section=scenario,
        ),
        _quantity(
            "/scenario/initial_state/secondary_shaft_angle_rad",
            "secondary_shaft_angle_rad",
            section=scenario,
        ),
        # Execution ---------------------------------------------------------
        _quantity(
            "/execution/traction_law/primary_static_lambda_limit",
            "primary_static_lambda_limit",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/traction_law/secondary_static_lambda_limit",
            "secondary_static_lambda_limit",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/traction_law/primary_kinetic_lambda_magnitude",
            "primary_kinetic_lambda_magnitude",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/traction_law/secondary_kinetic_lambda_magnitude",
            "secondary_kinetic_lambda_magnitude",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/solve_settings/lambda_search_bounds/primary_lower",
            "primary_lambda_lower",
            section=execution,
        ),
        _quantity(
            "/execution/solve_settings/lambda_search_bounds/primary_upper",
            "primary_lambda_upper",
            section=execution,
        ),
        _quantity(
            "/execution/solve_settings/lambda_search_bounds/secondary_lower",
            "secondary_lambda_lower",
            section=execution,
        ),
        _quantity(
            "/execution/solve_settings/lambda_search_bounds/secondary_upper",
            "secondary_lambda_upper",
            section=execution,
        ),
        _quantity(
            "/execution/solve_settings/initial_guess/primary_lambda",
            "primary_lambda",
            section=execution,
        ),
        _quantity(
            "/execution/solve_settings/initial_guess/secondary_lambda",
            "secondary_lambda",
            section=execution,
        ),
        _quantity(
            "/execution/solve_settings/contact_tolerances/relative_speed_tolerance_m_per_s",
            "relative_speed_tolerance_m_per_s",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/solve_settings/contact_tolerances/relative_acceleration_tolerance_m_per_s2",
            "relative_acceleration_tolerance_m_per_s2",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/solve_settings/contact_tolerances/stick_acceleration_tolerance_m_per_s2",
            "stick_acceleration_tolerance_m_per_s2",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/solve_settings/optimizer_tolerance",
            "optimizer_tolerance",
            section=execution,
            minimum=0.0,
        ),
        EditableFieldDescriptor(
            "/execution/solve_settings/maximum_function_evaluations",
            "Maximum function evaluations",
            "integer",
            execution,
            minimum=1.0,
        ),
        _quantity(
            "/execution/solve_settings/maximum_closure_condition_number",
            "maximum_closure_condition_number",
            section=execution,
            required=False,
            minimum=0.0,
        ),
        _quantity(
            "/execution/operating_limits/lower_stop_shift_m",
            "lower_stop_shift_m",
            section=execution,
        ),
        _quantity(
            "/execution/operating_limits/engagement_shift_m",
            "engagement_shift_m",
            section=execution,
        ),
        _quantity(
            "/execution/operating_limits/upper_stop_shift_m",
            "upper_stop_shift_m",
            section=execution,
        ),
        _quantity(
            "/execution/switching_settings/stick_exit_static_margin",
            "stick_exit_static_margin",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/switching_settings/restick_static_margin",
            "restick_static_margin",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/switching_settings/normal_resultant_floor_N",
            "normal_resultant_floor_N",
            section=execution,
            minimum=0.0,
        ),
        # Integrator and report --------------------------------------------
        _quantity(
            "/execution/integrator/relative_tolerance",
            "relative_tolerance",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/integrator/absolute_tolerance",
            "absolute_tolerance",
            section=execution,
            minimum=0.0,
        ),
        EditableFieldDescriptor(
            "/execution/integrator/method", "Integration method", "string", execution
        ),
        _quantity(
            "/execution/integrator/max_step_s",
            "max_step_s",
            section=execution,
            minimum=0.0,
        ),
        _quantity(
            "/execution/integrator/first_step_s",
            "first_step_s",
            section=execution,
            required=False,
            minimum=0.0,
        ),
        EditableFieldDescriptor(
            "/execution/integrator/maximum_transitions",
            "Maximum transitions",
            "integer",
            execution,
            minimum=1.0,
        ),
        _quantity(
            "/execution/integrator/event_time_tolerance_s",
            "event_time_tolerance_s",
            section=execution,
            minimum=0.0,
        ),
        EditableFieldDescriptor(
            "/execution/integrator/retain_dense_output",
            "Retain dense output",
            "boolean",
            execution,
        ),
        EditableFieldDescriptor(
            "/execution/reporting/include_contact",
            "Include contact signals",
            "boolean",
            reporting,
        ),
        EditableFieldDescriptor(
            "/execution/reporting/include_actuation",
            "Include actuation signals",
            "boolean",
            reporting,
        ),
        EditableFieldDescriptor(
            "/execution/reporting/include_closure_audit",
            "Include closure audit",
            "boolean",
            reporting,
        ),
        EditableFieldDescriptor(
            "/execution/reporting/include_integrated_observers",
            "Include integrated observers",
            "boolean",
            reporting,
        ),
        EditableFieldDescriptor(
            "/execution/reporting/grid/count",
            "Report sample count",
            "integer",
            reporting,
            required=False,
            minimum=2.0,
            when={"/execution/reporting/grid/kind": "uniform_count"},
        ),
        _quantity(
            "/execution/reporting/grid/step_seconds",
            "report_step_s",
            section=reporting,
            required=False,
            minimum=0.0,
            when={"/execution/reporting/grid/kind": "uniform_time_step"},
        ),
    )
