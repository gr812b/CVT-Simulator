"""Versioned, JSON-safe documents for executable CINDER simulation cases.

This module is a public adapter only.  Decoding builds the ordinary CINDER
construction objects used by Python callers; no core mechanics or execution
module depends on these document helpers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cinder.execution.hybrid.cvt_contact_switching import CVTContactSwitchSettings
from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingSystemConfig
from cinder.execution.hybrid.cvt_operating_limits import CVTShiftOperatingLimits
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTOperatingRegime,
    CVTShiftConstraint,
)
from cinder.execution.hybrid.hybrid import HybridIntegratorSettings
from cinder.model.boundaries.input import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)
from cinder.model.boundaries.output import FixedOutputLoad, LockedFinalDriveVehicle
from cinder.model.boundaries.output.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    PiecewiseConstantGradeRoadProfile,
    PiecewiseConstantGradeSegment,
    RoadLoadModel,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from cinder.model.cvt.contact import (
    ContactKinematicTolerances,
    ContactRegime,
    ContactTractionLaw,
    ContactTractionUtilization,
    EngagedContactMode,
    SlipDirection,
)
from cinder.model.cvt.dynamics import EngagedContactSolveSettings, LambdaSearchBounds
from cinder.model.system import CVTDynamicState, CVTSimulationCase, OperatingScenario
from cinder.results import ReportingGrid, ReportingSettings

from .conventions import PUBLIC_CONTRACT_VERSION
from ._decode import (
    require as _require,
    require_boolean as _boolean,
    require_finite_number as _finite_number,
    require_integer as _integer,
    require_mapping as _mapping,
    require_number as _number,
    require_number_or_infinity as _number_or_infinity,
    require_sequence as _sequence,
    require_string as _string,
)
from .document import (
    DesignDocumentError,
    UnsupportedDesignDocumentError,
    decode_assembly_document,
    encode_assembly_document,
)

SIMULATION_CASE_DOCUMENT_TYPE = "cinder_simulation_case"


class UnsupportedSimulationDocumentError(UnsupportedDesignDocumentError):
    """Raised when a valid-looking simulation document uses an unsupported variant."""


@dataclass(frozen=True, slots=True)
class DecodedSimulationCase:
    """Executable CINDER objects reconstructed from one public document."""

    case: CVTSimulationCase
    operating_system_config: CVTOperatingSystemConfig
    integrator_settings: HybridIntegratorSettings
    reporting_settings: ReportingSettings

    def build_system(self):
        """Build the ordinary hybrid runtime from the decoded public case."""

        return self.operating_system_config.build(self.case)


def encode_simulation_case_document(
    case: CVTSimulationCase,
    *,
    operating_system_config: CVTOperatingSystemConfig,
    integrator_settings: HybridIntegratorSettings = HybridIntegratorSettings(),
    reporting_settings: ReportingSettings | None = None,
) -> dict[str, Any]:
    """Encode an executable CINDER case and numerical settings.

    Only concrete built-ins already supported by CINDER's public document
    contract are serialized: ``FullThrottleTorqueCurve``, ``FixedOutputLoad``,
    and ``LockedFinalDriveVehicle`` with versioned road-profile documents.
    Custom callables remain Python extension points rather than being silently
    serialized as lossy pseudo-documents.
    """

    if not isinstance(case, CVTSimulationCase):
        raise TypeError("case must be a CVTSimulationCase.")
    if not isinstance(operating_system_config, CVTOperatingSystemConfig):
        raise TypeError("operating_system_config must be a CVTOperatingSystemConfig.")
    if not isinstance(integrator_settings, HybridIntegratorSettings):
        raise TypeError("integrator_settings must be a HybridIntegratorSettings.")
    if reporting_settings is None:
        reporting_settings = ReportingSettings.standard()
    if not isinstance(reporting_settings, ReportingSettings):
        raise TypeError("reporting_settings must be a ReportingSettings when supplied.")

    return {
        "schema_version": PUBLIC_CONTRACT_VERSION,
        "document_type": SIMULATION_CASE_DOCUMENT_TYPE,
        "assembly": encode_assembly_document(case.cvt),
        "input_boundary": _encode_input_boundary(case.input_boundary),
        "output_boundary": _encode_output_boundary(case.output_boundary),
        "scenario": _encode_scenario(case.scenario),
        "execution": {
            "traction_law": _encode_traction_law(operating_system_config.traction_law),
            "solve_settings": _encode_solve_settings(
                operating_system_config.solve_settings
            ),
            "operating_limits": _encode_operating_limits(
                operating_system_config.operating_limits
            ),
            "switching_settings": _encode_switching_settings(
                operating_system_config.switching_settings
            ),
            "integrator": _encode_integrator_settings(integrator_settings),
            "reporting": _encode_reporting_settings(reporting_settings),
        },
    }


def decode_simulation_case_document(
    document: Mapping[str, Any],
) -> DecodedSimulationCase:
    """Decode one version-one full simulation-case document.

    The return value contains actual CINDER types.  It can be run directly:

    .. code-block:: python

       decoded = decode_simulation_case_document(document)
       system = decoded.build_system()
       result = system.run(
           time_span=decoded.case.scenario.time_span,
           initial_state=decoded.case.scenario.initial_state,
           initial_regime=decoded.case.scenario.initial_mode,
           settings=decoded.integrator_settings,
           reporting_settings=decoded.reporting_settings,
       )
    """

    root = _mapping(document, "document")
    _require_document_header(root)
    assembly = decode_assembly_document(
        _mapping(_require(root, "assembly"), "assembly")
    )
    input_boundary = _decode_input_boundary(
        _mapping(_require(root, "input_boundary"), "input_boundary")
    )
    output_boundary = _decode_output_boundary(
        _mapping(_require(root, "output_boundary"), "output_boundary")
    )
    scenario = _decode_scenario(_mapping(_require(root, "scenario"), "scenario"))
    execution = _mapping(_require(root, "execution"), "execution")

    operating_system_config = CVTOperatingSystemConfig(
        traction_law=_decode_traction_law(
            _mapping(_require(execution, "traction_law"), "execution.traction_law")
        ),
        solve_settings=_decode_solve_settings(
            _mapping(_require(execution, "solve_settings"), "execution.solve_settings")
        ),
        operating_limits=_decode_operating_limits(
            _mapping(
                _require(execution, "operating_limits"), "execution.operating_limits"
            )
        ),
        switching_settings=_decode_switching_settings(
            _mapping(
                _require(execution, "switching_settings"),
                "execution.switching_settings",
            )
        ),
    )
    integrator_settings = _decode_integrator_settings(
        _mapping(_require(execution, "integrator"), "execution.integrator")
    )
    reporting_settings = _decode_reporting_settings(
        _mapping(_require(execution, "reporting"), "execution.reporting")
    )

    return DecodedSimulationCase(
        case=CVTSimulationCase(
            cvt=assembly,
            input_boundary=input_boundary,
            output_boundary=output_boundary,
            scenario=scenario,
        ),
        operating_system_config=operating_system_config,
        integrator_settings=integrator_settings,
        reporting_settings=reporting_settings,
    )


def _encode_input_boundary(boundary: object) -> dict[str, Any]:
    if not isinstance(boundary, FullThrottleTorqueCurve):
        raise UnsupportedSimulationDocumentError(
            "Only FullThrottleTorqueCurve is serializable as an input boundary."
        )
    spec = boundary.spec
    return {
        "kind": "full_throttle_torque_curve",
        "points": [
            {
                "angular_speed_rad_per_s": point.angular_speed,
                "torque_Nm": point.torque,
            }
            for point in spec.points
        ],
        "low_speed_braking_torque_Nm": spec.low_speed_braking_torque,
        "low_speed_braking_peak_speed_rad_per_s": spec.low_speed_braking_peak_speed,
        "high_speed_braking_torque_Nm": spec.high_speed_braking_torque,
        "high_speed_braking_transition_width_rad_per_s": spec.high_speed_braking_transition_width,
        "equivalent_rotational_inertia_kg_m2": boundary.equivalent_rotational_inertia,
    }


def _decode_input_boundary(payload: Mapping[str, Any]) -> FullThrottleTorqueCurve:
    kind = _string(payload, "kind")
    if kind != "full_throttle_torque_curve":
        raise UnsupportedSimulationDocumentError(
            f"Unsupported input_boundary kind {kind!r}."
        )
    points = _sequence(_require(payload, "points"), "input_boundary.points")
    if not points:
        raise DesignDocumentError("input_boundary.points must not be empty.")
    return FullThrottleTorqueCurve(
        TorqueCurveSpec(
            points=tuple(
                EngineTorquePoint(
                    angular_speed=_number(
                        _mapping(point, f"input_boundary.points[{index}]"),
                        "angular_speed_rad_per_s",
                    ),
                    torque=_number(
                        _mapping(point, f"input_boundary.points[{index}]"), "torque_Nm"
                    ),
                )
                for index, point in enumerate(points)
            ),
            low_speed_braking_torque=_number(payload, "low_speed_braking_torque_Nm"),
            low_speed_braking_peak_speed=_number(
                payload, "low_speed_braking_peak_speed_rad_per_s"
            ),
            high_speed_braking_torque=_number(payload, "high_speed_braking_torque_Nm"),
            high_speed_braking_transition_width=_number(
                payload, "high_speed_braking_transition_width_rad_per_s"
            ),
        ),
        equivalent_rotational_inertia=_number(
            payload, "equivalent_rotational_inertia_kg_m2"
        ),
    )


def _encode_output_boundary(boundary: object) -> dict[str, Any]:
    if isinstance(boundary, FixedOutputLoad):
        return {
            "kind": "fixed_output_load",
            "load_torque_Nm": boundary.load_torque,
            "equivalent_rotational_inertia_kg_m2": boundary.equivalent_rotational_inertia,
        }
    if isinstance(boundary, LockedFinalDriveVehicle):
        spec = boundary.road_load.spec
        vehicle = boundary.vehicle
        final_drive = boundary.final_drive
        return {
            "kind": "locked_final_drive_vehicle",
            "vehicle": {
                "mass_kg": vehicle.mass,
                "wheel_rotational_inertia_kg_m2": vehicle.wheel_rotational_inertia,
            },
            "final_drive": {
                "reduction_ratio": final_drive.reduction_ratio,
                "wheel_radius_m": final_drive.wheel_radius,
            },
            "road_load": {
                "rolling_resistance_coefficient": spec.rolling_resistance_coefficient,
                "drag_coefficient": spec.drag_coefficient,
                "frontal_area_m2": spec.frontal_area,
                "air_density_kg_per_m3": spec.air_density,
                "gravity_m_per_s2": spec.gravity,
                "rolling_speed_regularization_m_per_s": spec.rolling_speed_regularization,
            },
            "road_profile": _encode_road_profile(boundary.road_profile),
            "direct_secondary_shaft_inertia_kg_m2": boundary.direct_secondary_shaft_inertia,
        }
    raise UnsupportedSimulationDocumentError(
        f"Cannot encode unsupported output boundary {type(boundary).__name__}."
    )


def _encode_road_profile(profile: object) -> dict[str, Any]:
    if isinstance(profile, ConstantGradeRoadProfile):
        return {
            "kind": "constant_grade",
            "grade_angle_rad": profile.grade_angle,
        }
    if isinstance(profile, PiecewiseConstantGradeRoadProfile):
        return {
            "kind": "piecewise_constant_grade",
            "segments": [
                {
                    "start_distance_m": segment.start_distance,
                    "grade_angle_rad": segment.grade_angle,
                }
                for segment in profile.segments
            ],
        }
    raise UnsupportedSimulationDocumentError(
        f"Cannot encode unsupported road profile {type(profile).__name__}."
    )


def _decode_road_profile(payload: Mapping[str, Any]) -> ConstantGradeRoadProfile | PiecewiseConstantGradeRoadProfile:
    profile_kind = _string(payload, "kind")
    if profile_kind == "constant_grade":
        return ConstantGradeRoadProfile(grade_angle=_number(payload, "grade_angle_rad"))
    if profile_kind == "piecewise_constant_grade":
        segments_payload = _sequence(_require(payload, "segments"), "road_profile.segments")
        segments = tuple(
            PiecewiseConstantGradeSegment(
                start_distance=_number(
                    _mapping(segment_payload, f"road_profile.segments[{index}]"),
                    "start_distance_m",
                ),
                grade_angle=_number(
                    _mapping(segment_payload, f"road_profile.segments[{index}]"),
                    "grade_angle_rad",
                ),
            )
            for index, segment_payload in enumerate(segments_payload)
        )
        return PiecewiseConstantGradeRoadProfile(segments=segments)
    raise UnsupportedSimulationDocumentError(
        f"Unsupported output_boundary.road_profile kind {profile_kind!r}."
    )



def _decode_output_boundary(
    payload: Mapping[str, Any],
) -> FixedOutputLoad | LockedFinalDriveVehicle:
    kind = _string(payload, "kind")
    if kind == "fixed_output_load":
        return FixedOutputLoad(
            load_torque=_number(payload, "load_torque_Nm"),
            equivalent_rotational_inertia=_number(
                payload, "equivalent_rotational_inertia_kg_m2"
            ),
        )
    if kind != "locked_final_drive_vehicle":
        raise UnsupportedSimulationDocumentError(
            f"Unsupported output_boundary kind {kind!r}."
        )
    vehicle_doc = _mapping(_require(payload, "vehicle"), "output_boundary.vehicle")
    final_drive_doc = _mapping(
        _require(payload, "final_drive"), "output_boundary.final_drive"
    )
    road_load_doc = _mapping(
        _require(payload, "road_load"), "output_boundary.road_load"
    )
    road_profile_doc = _mapping(
        _require(payload, "road_profile"), "output_boundary.road_profile"
    )
    road_profile = _decode_road_profile(road_profile_doc)
    road_load = RoadLoadModel(
        spec=VehicleRoadLoadSpec(
            rolling_resistance_coefficient=_number(
                road_load_doc, "rolling_resistance_coefficient"
            ),
            drag_coefficient=_number(road_load_doc, "drag_coefficient"),
            frontal_area=_number(road_load_doc, "frontal_area_m2"),
            air_density=_number(road_load_doc, "air_density_kg_per_m3"),
            gravity=_number(road_load_doc, "gravity_m_per_s2"),
            rolling_speed_regularization=_number(
                road_load_doc, "rolling_speed_regularization_m_per_s"
            ),
        ),
        vehicle=VehicleInertia(
            mass=_number(vehicle_doc, "mass_kg"),
            wheel_rotational_inertia=_number(
                vehicle_doc, "wheel_rotational_inertia_kg_m2"
            ),
        ),
        final_drive=FixedFinalDrive(
            reduction_ratio=_number(final_drive_doc, "reduction_ratio"),
            wheel_radius=_number(final_drive_doc, "wheel_radius_m"),
        ),
    )
    return LockedFinalDriveVehicle(
        road_load=road_load,
        road_profile=road_profile,
        direct_secondary_shaft_inertia=_number(
            payload, "direct_secondary_shaft_inertia_kg_m2"
        ),
    )


def _encode_scenario(scenario: OperatingScenario) -> dict[str, Any]:
    state = scenario.initial_state
    return {
        "time_span_s": [scenario.time_span[0], scenario.time_span[1]],
        "initial_state": {
            "primary_angular_speed_rad_per_s": state.primary_angular_speed,
            "secondary_angular_speed_rad_per_s": state.secondary_angular_speed,
            "belt_speed_m_per_s": state.belt_speed,
            "shift_position_m": state.shift_position,
            "shift_speed_m_per_s": state.shift_speed,
            "secondary_shaft_angle_rad": state.secondary_shaft_angle,
        },
        "initial_mode": _encode_initial_mode(scenario.initial_mode),
    }


def _decode_scenario(payload: Mapping[str, Any]) -> OperatingScenario:
    time_span_values = _sequence(
        _require(payload, "time_span_s"), "scenario.time_span_s"
    )
    if len(time_span_values) != 2:
        raise DesignDocumentError(
            "scenario.time_span_s must contain exactly two values."
        )
    state_doc = _mapping(_require(payload, "initial_state"), "scenario.initial_state")
    return OperatingScenario(
        time_span=(
            _finite_number(time_span_values[0], "scenario.time_span_s[0]"),
            _finite_number(time_span_values[1], "scenario.time_span_s[1]"),
        ),
        initial_state=CVTDynamicState(
            primary_angular_speed=_number(state_doc, "primary_angular_speed_rad_per_s"),
            secondary_angular_speed=_number(
                state_doc, "secondary_angular_speed_rad_per_s"
            ),
            belt_speed=_number(state_doc, "belt_speed_m_per_s"),
            shift_position=_number(state_doc, "shift_position_m"),
            shift_speed=_number(state_doc, "shift_speed_m_per_s"),
            secondary_shaft_angle=_number(state_doc, "secondary_shaft_angle_rad"),
        ),
        initial_mode=_decode_initial_mode(payload.get("initial_mode")),
    )


def _encode_initial_mode(mode: object) -> dict[str, Any] | None:
    if mode is None:
        return None
    if not isinstance(mode, CVTOperatingRegime):
        raise UnsupportedSimulationDocumentError(
            "Only CVTOperatingRegime can be encoded as scenario.initial_mode."
        )
    contact = mode.contact_regime
    return {
        "engagement": mode.engagement.value,
        "shift_constraint": mode.shift_constraint.value,
        "contact_regime": (
            None
            if contact is None
            else {
                "mode": contact.mode.value,
                "primary_slip_direction": (
                    None
                    if contact.primary_slip_direction is None
                    else contact.primary_slip_direction.value
                ),
                "secondary_slip_direction": (
                    None
                    if contact.secondary_slip_direction is None
                    else contact.secondary_slip_direction.value
                ),
            }
        ),
    }


def _decode_initial_mode(value: object) -> CVTOperatingRegime | None:
    if value is None:
        return None
    payload = _mapping(value, "scenario.initial_mode")
    try:
        engagement = CVTEngagementState(_string(payload, "engagement"))
        shift_constraint = CVTShiftConstraint(_string(payload, "shift_constraint"))
    except ValueError as error:
        raise DesignDocumentError(
            "scenario.initial_mode contains an unknown regime value."
        ) from error
    contact_value = payload.get("contact_regime")
    contact_regime = None
    if contact_value is not None:
        contact_doc = _mapping(contact_value, "scenario.initial_mode.contact_regime")
        try:
            contact_regime = ContactRegime(
                mode=EngagedContactMode(_string(contact_doc, "mode")),
                primary_slip_direction=_optional_enum(
                    contact_doc, "primary_slip_direction", SlipDirection
                ),
                secondary_slip_direction=_optional_enum(
                    contact_doc, "secondary_slip_direction", SlipDirection
                ),
            )
        except ValueError as error:
            raise DesignDocumentError(
                "scenario.initial_mode.contact_regime contains an unknown contact value."
            ) from error
    return CVTOperatingRegime(
        engagement=engagement,
        shift_constraint=shift_constraint,
        contact_regime=contact_regime,
    )


def _encode_traction_law(law: ContactTractionLaw) -> dict[str, Any]:
    return {
        "primary_static_lambda_limit": law.primary_static_interval.upper,
        "secondary_static_lambda_limit": law.secondary_static_interval.upper,
        "primary_kinetic_lambda_magnitude": law.primary_kinetic_lambda_magnitude,
        "secondary_kinetic_lambda_magnitude": law.secondary_kinetic_lambda_magnitude,
    }


def _decode_traction_law(payload: Mapping[str, Any]) -> ContactTractionLaw:
    return ContactTractionLaw.symmetric(
        primary_static_lambda_limit=_number(payload, "primary_static_lambda_limit"),
        secondary_static_lambda_limit=_number(payload, "secondary_static_lambda_limit"),
        primary_kinetic_lambda_magnitude=_number(
            payload, "primary_kinetic_lambda_magnitude"
        ),
        secondary_kinetic_lambda_magnitude=_number(
            payload, "secondary_kinetic_lambda_magnitude"
        ),
    )


def _encode_solve_settings(settings: EngagedContactSolveSettings) -> dict[str, Any]:
    bounds = settings.lambda_search_bounds
    tolerance = settings.contact_tolerances
    return {
        "lambda_search_bounds": {
            "primary_lower": bounds.primary_lower,
            "primary_upper": bounds.primary_upper,
            "secondary_lower": bounds.secondary_lower,
            "secondary_upper": bounds.secondary_upper,
        },
        "initial_guess": {
            "primary_lambda": settings.initial_guess.primary_lambda,
            "secondary_lambda": settings.initial_guess.secondary_lambda,
        },
        "contact_tolerances": {
            "relative_speed_tolerance_m_per_s": tolerance.relative_speed_tolerance,
            "relative_acceleration_tolerance_m_per_s2": tolerance.relative_acceleration_tolerance,
            "stick_acceleration_tolerance_m_per_s2": tolerance.stick_acceleration_tolerance,
        },
        "optimizer_tolerance": settings.optimizer_tolerance,
        "maximum_function_evaluations": settings.maximum_function_evaluations,
        "maximum_closure_condition_number": settings.maximum_closure_condition_number,
    }


def _decode_solve_settings(payload: Mapping[str, Any]) -> EngagedContactSolveSettings:
    bounds = _mapping(
        _require(payload, "lambda_search_bounds"),
        "execution.solve_settings.lambda_search_bounds",
    )
    initial = _mapping(
        _require(payload, "initial_guess"), "execution.solve_settings.initial_guess"
    )
    tolerances = _mapping(
        _require(payload, "contact_tolerances"),
        "execution.solve_settings.contact_tolerances",
    )
    condition_number = payload.get("maximum_closure_condition_number")
    return EngagedContactSolveSettings(
        lambda_search_bounds=LambdaSearchBounds(
            primary_lower=_number(bounds, "primary_lower"),
            primary_upper=_number(bounds, "primary_upper"),
            secondary_lower=_number(bounds, "secondary_lower"),
            secondary_upper=_number(bounds, "secondary_upper"),
        ),
        initial_guess=ContactTractionUtilization(
            primary_lambda=_number(initial, "primary_lambda"),
            secondary_lambda=_number(initial, "secondary_lambda"),
        ),
        contact_tolerances=ContactKinematicTolerances(
            relative_speed_tolerance=_number(
                tolerances, "relative_speed_tolerance_m_per_s"
            ),
            relative_acceleration_tolerance=_number(
                tolerances, "relative_acceleration_tolerance_m_per_s2"
            ),
            stick_acceleration_tolerance=_number(
                tolerances, "stick_acceleration_tolerance_m_per_s2"
            ),
        ),
        optimizer_tolerance=_number(payload, "optimizer_tolerance"),
        maximum_function_evaluations=_integer(payload, "maximum_function_evaluations"),
        maximum_closure_condition_number=(
            None
            if condition_number is None
            else _finite_number(
                condition_number,
                "execution.solve_settings.maximum_closure_condition_number",
            )
        ),
    )


def _encode_operating_limits(limits: CVTShiftOperatingLimits) -> dict[str, Any]:
    return {
        "lower_stop_shift_m": limits.lower_stop_shift,
        "engagement_shift_m": limits.engagement_shift,
        "upper_stop_shift_m": limits.upper_stop_shift,
    }


def _decode_operating_limits(payload: Mapping[str, Any]) -> CVTShiftOperatingLimits:
    return CVTShiftOperatingLimits(
        lower_stop_shift=_number(payload, "lower_stop_shift_m"),
        engagement_shift=_number(payload, "engagement_shift_m"),
        upper_stop_shift=_number(payload, "upper_stop_shift_m"),
    )


def _encode_switching_settings(settings: CVTContactSwitchSettings) -> dict[str, Any]:
    return {
        "stick_exit_static_margin": settings.stick_exit_static_margin,
        "restick_static_margin": settings.restick_static_margin,
        "normal_resultant_floor_N": settings.normal_resultant_floor,
    }


def _decode_switching_settings(payload: Mapping[str, Any]) -> CVTContactSwitchSettings:
    return CVTContactSwitchSettings(
        stick_exit_static_margin=_number(payload, "stick_exit_static_margin"),
        restick_static_margin=_number(payload, "restick_static_margin"),
        normal_resultant_floor=_number(payload, "normal_resultant_floor_N"),
    )


def _encode_integrator_settings(settings: HybridIntegratorSettings) -> dict[str, Any]:
    return {
        "relative_tolerance": settings.relative_tolerance,
        "absolute_tolerance": settings.absolute_tolerance,
        "method": settings.method,
        "max_step_s": (
            "infinity" if settings.max_step == float("inf") else settings.max_step
        ),
        "first_step_s": settings.first_step,
        "maximum_transitions": settings.maximum_transitions,
        "event_time_tolerance_s": settings.event_time_tolerance,
        "retain_dense_output": settings.retain_dense_output,
    }


def _decode_integrator_settings(payload: Mapping[str, Any]) -> HybridIntegratorSettings:
    max_step = _number_or_infinity(payload, "max_step_s")
    first_step = payload.get("first_step_s")
    return HybridIntegratorSettings(
        relative_tolerance=_number(payload, "relative_tolerance"),
        absolute_tolerance=_number(payload, "absolute_tolerance"),
        method=_string(payload, "method"),
        max_step=max_step,
        first_step=(
            None
            if first_step is None
            else _finite_number(first_step, "execution.integrator.first_step_s")
        ),
        maximum_transitions=_integer(payload, "maximum_transitions"),
        event_time_tolerance=_number(payload, "event_time_tolerance_s"),
        retain_dense_output=_boolean(payload, "retain_dense_output"),
    )


def _encode_reporting_settings(settings: ReportingSettings) -> dict[str, Any]:
    grid = settings.grid
    return {
        "grid": {
            "kind": grid.kind,
            "count": grid.count,
            "step_seconds": grid.step_seconds,
        },
        "include_contact": settings.include_contact,
        "include_actuation": settings.include_actuation,
        "include_closure_audit": settings.include_closure_audit,
        "include_integrated_observers": settings.include_integrated_observers,
    }


def _decode_reporting_settings(payload: Mapping[str, Any]) -> ReportingSettings:
    grid_doc = _mapping(_require(payload, "grid"), "execution.reporting.grid")
    kind = _string(grid_doc, "kind")
    if kind == "native":
        grid = ReportingGrid.native()
    elif kind == "uniform_count":
        grid = ReportingGrid.uniform_count(_integer(grid_doc, "count"))
    elif kind == "uniform_time_step":
        grid = ReportingGrid.uniform_time_step(_number(grid_doc, "step_seconds"))
    else:
        raise UnsupportedSimulationDocumentError(
            f"Unsupported execution.reporting.grid kind {kind!r}."
        )
    return ReportingSettings(
        grid=grid,
        include_contact=_boolean(payload, "include_contact"),
        include_actuation=_boolean(payload, "include_actuation"),
        include_closure_audit=_boolean(payload, "include_closure_audit"),
        include_integrated_observers=_boolean(payload, "include_integrated_observers"),
    )


def _require_document_header(document: Mapping[str, Any]) -> None:
    if _integer(document, "schema_version") != PUBLIC_CONTRACT_VERSION:
        raise UnsupportedSimulationDocumentError(
            f"Unsupported simulation-document schema_version; expected {PUBLIC_CONTRACT_VERSION}."
        )
    if _string(document, "document_type") != SIMULATION_CASE_DOCUMENT_TYPE:
        raise UnsupportedSimulationDocumentError(
            f"document_type must be {SIMULATION_CASE_DOCUMENT_TYPE!r}."
        )


def _optional_enum(
    mapping: Mapping[str, Any], key: str, enum_type: type[SlipDirection]
) -> SlipDirection | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DesignDocumentError(f"{key} must be a string or null.")
    return enum_type(value)
