"""The backend's single direct dependency on CINDER.

Routes, stores, Pydantic schemas, and worker orchestration stay CINDER-free.
This module converts explicit transport primitives into the stable public
CINDER contracts and study requests, then returns JSON-safe public projections.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from cinder.contracts import (
    component_catalog_document,
    decode_assembly_document,
    decode_simulation_case_document,
    editable_simulation_case_schema,
    project_clamping_force_response,
    project_geometry_feasibility,
    project_geometry_path,
    project_geometry_summary,
    project_radius_plane,
    project_ratio_sensitivity_field,
    project_simulation_result,
    public_conventions,
    simulation_case_document_json_schema,
    validate_simulation_case_document,
)
from cinder.model.cvt.closure import ClosureUnknown, ClosureUnknowns
from cinder.model.cvt.geometry import BeltSectionSpec
from cinder.studies import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    ActuationStateCoordinate,
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    TargetRatioDesignRequest,
    evaluate_geometry_feasibility,
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
    sample_geometry_path,
    sample_pulley_clamping_force,
    solve_geometry_from_endpoint_radii,
    solve_geometry_from_target_ratios,
    summarize_geometry_design,
)


class CinderGateway:
    """Small application-facing façade over CINDER's public API."""

    def conventions(self) -> dict[str, Any]:
        return public_conventions().as_dict()

    def component_catalog(self) -> dict[str, Any]:
        return component_catalog_document()

    def editor_schema(self) -> dict[str, Any]:
        return editable_simulation_case_schema()

    def simulation_case_json_schema(self) -> dict[str, Any]:
        return simulation_case_document_json_schema()

    def validate_simulation_case(self, document: Mapping[str, Any]) -> dict[str, Any]:
        return validate_simulation_case_document(document).as_dict()

    def run_simulation(
        self,
        document: Mapping[str, Any],
        *,
        include_reported_segments: bool = False,
        include_raw_trace: bool = False,
    ) -> dict[str, Any]:
        """Run one complete CINDER document and return its public projection."""

        decoded = decode_simulation_case_document(document)
        system = decoded.build_system()
        result = system.run(
            time_span=decoded.time_span,
            initial_state=decoded.initial_state,
            initial_mode=decoded.initial_mode,
            settings=decoded.integrator_settings,
            reporting_settings=decoded.reporting_settings,
        )
        return project_simulation_result(
            result,
            include_reported_segments=include_reported_segments,
            include_raw_trace=include_raw_trace,
        )

    def geometry_from_endpoint_radii(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        context = self._geometry_context(_mapping(payload.get("context"), "context"))
        design = solve_geometry_from_endpoint_radii(
            EndpointRadiiDesignRequest(
                context=context,
                primary_outer_radius_at_zero_shift=_number(
                    payload, "primary_outer_radius_at_zero_shift_m"
                ),
                secondary_outer_radius_at_zero_shift=_number(
                    payload, "secondary_outer_radius_at_zero_shift_m"
                ),
            )
        )
        return self._project_geometry_design(design, payload)

    def geometry_from_target_ratios(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        context = self._geometry_context(_mapping(payload.get("context"), "context"))
        design = solve_geometry_from_target_ratios(
            TargetRatioDesignRequest(
                context=context,
                maximum_ratio=_number(payload, "maximum_ratio"),
                minimum_ratio=_number(payload, "minimum_ratio"),
            )
        )
        return self._project_geometry_design(design, payload)

    def clamping_response(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        assembly = decode_assembly_document(
            _mapping(payload.get("assembly_document"), "assembly_document")
        )
        closure = _mapping(payload.get("closure_unknowns", {}), "closure_unknowns")
        axes_payload = payload.get("axes")
        if not isinstance(axes_payload, list):
            raise ValueError("axes must be an array.")

        request = PulleyClampingForceStudyRequest(
            cvt=assembly,
            pulley=PulleyLocation(str(payload["pulley"])),
            point=ActuationOperatingPoint(
                # This API remains a static clamping map; time is therefore
                # explicitly fixed rather than hidden behind a context default.
                time=0.0,
                shift_position=_number(payload, "shift_position_m"),
                shaft_speed=_number(payload, "shaft_speed_rad_per_s"),
                shift_speed=_number(payload, "shift_speed_m_per_s"),
                closure_unknowns=ClosureUnknowns.from_components(
                    primary_angular_acceleration=_number(
                        closure, "primary_angular_acceleration_rad_per_s2", default=0.0
                    ),
                    secondary_angular_acceleration=_number(
                        closure, "secondary_angular_acceleration_rad_per_s2", default=0.0
                    ),
                    belt_acceleration=_number(closure, "belt_acceleration_m_per_s2", default=0.0),
                    shift_acceleration=_number(closure, "shift_acceleration_m_per_s2", default=0.0),
                    primary_torque=_number(closure, "primary_torque_Nm", default=0.0),
                    secondary_torque=_number(closure, "secondary_torque_Nm", default=0.0),
                    primary_normal_resultant=_number(
                        closure, "primary_normal_resultant_N", default=0.0
                    ),
                    secondary_normal_resultant=_number(
                        closure, "secondary_normal_resultant_N", default=0.0
                    ),
                ),
            ),
            axes=tuple(
                ActuationResponseAxis(
                    coordinate=_actuation_coordinate(_string(axis, "coordinate")),
                    values=_number_list(axis, "values"),
                )
                for axis in axes_payload
                if isinstance(axis, Mapping)
            ),
        )
        if len(request.axes) != len(axes_payload):
            raise ValueError("Each actuation axis must be an object.")
        return project_clamping_force_response(sample_pulley_clamping_force(request))

    @staticmethod
    def _geometry_context(payload: Mapping[str, Any]) -> GeometryDesignContext:
        belt_payload = _mapping(payload.get("belt"), "context.belt")
        return GeometryDesignContext(
            belt=BeltSectionSpec(
                height=_number(belt_payload, "height_m"),
                outer_width=_number(belt_payload, "outer_width_m"),
                inner_width=_number(belt_payload, "inner_width_m"),
                cord_depth_from_outer=_number(belt_payload, "cord_depth_from_outer_m"),
            ),
            belt_outer_length=_number(payload, "belt_outer_length_m"),
            sheave_half_angle=_number(payload, "sheave_half_angle_rad"),
            deadzone_shift=_number(payload, "deadzone_shift_m"),
            max_shift=_number(payload, "max_shift_m"),
        )

    @staticmethod
    def _project_geometry_design(design: object, payload: Mapping[str, Any]) -> dict[str, Any]:
        sample_count = int(payload.get("sample_count", 301))
        result: dict[str, Any] = {
            "contract_version": 1,
            "kind": "geometry_design_response",
            "summary": project_geometry_summary(summarize_geometry_design(design)),
            "path": project_geometry_path(sample_geometry_path(design, sample_count=sample_count)),
            "feasibility": project_geometry_feasibility(
                evaluate_geometry_feasibility(
                    design,
                    minimum_primary_wrap_angle=_optional_number(
                        payload, "minimum_primary_wrap_angle_rad"
                    ),
                    minimum_secondary_wrap_angle=_optional_number(
                        payload, "minimum_secondary_wrap_angle_rad"
                    ),
                )
            ),
        }
        sampling = payload.get("field_sampling")
        if sampling is not None:
            field = _mapping(sampling, "field_sampling")
            primary_axis = np.asarray(_number_list(field, "primary_outer_radius_m"), dtype=float)
            secondary_axis = np.asarray(
                _number_list(field, "secondary_outer_radius_m"), dtype=float
            )
            geometry_spec = design.geometry_spec
            result["radius_plane"] = project_radius_plane(
                evaluate_radius_plane(
                    belt=geometry_spec.belt,
                    center_distance=design.center_distance,
                    primary_outer_radius=primary_axis,
                    secondary_outer_radius=secondary_axis,
                )
            )
            result["ratio_sensitivity"] = project_ratio_sensitivity_field(
                evaluate_ratio_sensitivity_field(
                    belt=geometry_spec.belt,
                    center_distance=design.center_distance,
                    sheave_half_angle=geometry_spec.sheave_half_angle,
                    primary_outer_radius=primary_axis,
                    secondary_outer_radius=secondary_axis,
                )
            )
        return result


def _actuation_coordinate(value: str) -> ActuationStateCoordinate | ClosureUnknown:
    state_coordinates = {
        "shift_position": ActuationStateCoordinate.SHIFT_POSITION,
        "shaft_speed": ActuationStateCoordinate.SHAFT_SPEED,
        "shift_speed": ActuationStateCoordinate.SHIFT_SPEED,
    }
    closure_coordinates = {
        "primary_angular_acceleration": ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION,
        "secondary_angular_acceleration": ClosureUnknown.SECONDARY_ANGULAR_ACCELERATION,
        "belt_acceleration": ClosureUnknown.BELT_ACCELERATION,
        "shift_acceleration": ClosureUnknown.SHIFT_ACCELERATION,
        "primary_torque": ClosureUnknown.PRIMARY_TORQUE,
        "secondary_torque": ClosureUnknown.SECONDARY_TORQUE,
        "primary_normal_resultant": ClosureUnknown.PRIMARY_NORMAL_RESULTANT,
        "secondary_normal_resultant": ClosureUnknown.SECONDARY_NORMAL_RESULTANT,
    }
    try:
        return state_coordinates[value]
    except KeyError:
        try:
            return closure_coordinates[value]
        except KeyError as error:
            choices = sorted([*state_coordinates, *closure_coordinates])
            raise ValueError(
                f"Unsupported actuation coordinate {value!r}; choose one of {choices}."
            ) from error


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object.")
    return value


def _string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _number(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: float | None = None,
) -> float:
    if key not in payload:
        if default is not None:
            return default
        raise ValueError(f"{key} is required.")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number.")
    return float(value)


def _optional_number(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number or null.")
    return float(value)


def _number_list(payload: Mapping[str, Any], key: str) -> list[float]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array.")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{key} must contain only numbers.")
        numbers.append(float(item))
    return numbers
