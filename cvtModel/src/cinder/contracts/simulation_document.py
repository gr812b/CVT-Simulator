"""Versioned JSON-safe documents for composed CINDER simulation cases.

The simulation document stores the mechanical CVT assembly, shaft boundaries,
host state, and numerical/reporting preferences needed to build a composed
plant-host system. The CVT itself remains a five-state plant; vehicle, engine,
and dyno details live in shaft boundaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cinder.execution.hybrid import HybridIntegratorSettings
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import SecondaryShaftAngleHost, TireVehicleHost
from cinder.model.boundaries.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)
from cinder.model.boundaries.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    PiecewiseConstantGradeRoadProfile,
    PiecewiseConstantGradeSegment,
    RoadLoadModel,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from cinder.model.boundaries.shaft import (
    FixedShaftBoundary,
    FullThrottleEngineBoundary,
    LockedFinalDriveShaftBoundary,
)
from cinder.model.system import CVTAssemblySpec, CVTState, MechanicalCVTPlant
from cinder.results import ReportingGrid, ReportingSettings

from ._decode import (
    DesignDocumentError,
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
from .conventions import PUBLIC_CONTRACT_VERSION
from .document import (
    UnsupportedDesignDocumentError,
    decode_assembly_document,
    encode_assembly_document,
)

SIMULATION_CASE_DOCUMENT_TYPE = "cinder_composed_simulation_case"


class UnsupportedSimulationDocumentError(UnsupportedDesignDocumentError):
    """Raised when a valid-looking simulation document uses an unsupported variant."""


@dataclass(frozen=True, slots=True)
class DecodedSimulationCase:
    """Executable objects reconstructed from a public simulation document."""

    assembly: CVTAssemblySpec
    plant: MechanicalCVTPlant
    system: ComposedCVTHybridSystem
    initial_state: Any
    initial_mode: Any
    integrator_settings: HybridIntegratorSettings
    reporting_settings: ReportingSettings
    time_span: tuple[float, float]

    def build_system(self) -> ComposedCVTHybridSystem:
        return self.system


def encode_simulation_case_document(
    *,
    assembly: CVTAssemblySpec,
    primary_boundary: object,
    secondary_boundary: object,
    host: object,
    initial_cvt_state: CVTState,
    initial_host_state,
    time_span: tuple[float, float],
    integrator_settings: HybridIntegratorSettings = HybridIntegratorSettings(),
    reporting_settings: ReportingSettings | None = None,
) -> dict[str, Any]:
    """Encode a composed simulation using built-in serializable pieces."""

    if reporting_settings is None:
        reporting_settings = ReportingSettings.standard()
    return {
        "schema_version": PUBLIC_CONTRACT_VERSION,
        "document_type": SIMULATION_CASE_DOCUMENT_TYPE,
        "assembly": encode_assembly_document(assembly),
        "shaft_boundaries": {
            "primary": _encode_shaft_boundary(primary_boundary),
            "secondary": _encode_shaft_boundary(secondary_boundary),
        },
        "host": _encode_host(host, initial_host_state),
        "scenario": {
            "time_span_s": list(time_span),
            "initial_cvt_state": _encode_cvt_state(initial_cvt_state),
        },
        "execution": {
            "integrator": _encode_integrator_settings(integrator_settings),
            "reporting": _encode_reporting_settings(reporting_settings),
        },
    }


def decode_simulation_case_document(
    document: Mapping[str, Any],
) -> DecodedSimulationCase:
    """Decode one composed simulation-case document into executable objects."""

    root = _mapping(document, "document")
    _require_document_header(root)
    assembly = decode_assembly_document(
        _mapping(_require(root, "assembly"), "assembly")
    )
    plant = MechanicalCVTPlant.from_assembly(assembly)

    boundaries_doc = _mapping(_require(root, "shaft_boundaries"), "shaft_boundaries")
    primary_boundary = _decode_shaft_boundary(
        _mapping(_require(boundaries_doc, "primary"), "shaft_boundaries.primary")
    )
    secondary_boundary = _decode_shaft_boundary(
        _mapping(_require(boundaries_doc, "secondary"), "shaft_boundaries.secondary")
    )

    host_doc = _mapping(_require(root, "host"), "host")
    host, initial_host_state = _decode_host(
        host_doc, secondary_boundary=secondary_boundary
    )

    scenario = _mapping(_require(root, "scenario"), "scenario")
    span = _sequence(_require(scenario, "time_span_s"), "scenario.time_span_s")
    if len(span) != 2:
        raise DesignDocumentError(
            "scenario.time_span_s must contain exactly two numbers."
        )
    time_span = (float(span[0]), float(span[1]))
    initial_cvt_state = _decode_cvt_state(
        _mapping(_require(scenario, "initial_cvt_state"), "scenario.initial_cvt_state")
    )

    execution = _mapping(_require(root, "execution"), "execution")
    integrator_settings = _decode_integrator_settings(
        _mapping(_require(execution, "integrator"), "execution.integrator")
    )
    reporting_settings = _decode_reporting_settings(
        _mapping(_require(execution, "reporting"), "execution.reporting")
    )

    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
        host=host,
    )
    initial_state = system.initial_state(
        cvt_state=initial_cvt_state,
        host_state=initial_host_state,
    )
    initial_mode = system.classify_initial_mode(initial_state)
    # Preserve time_span on the object for callers that want a one-line run.
    (
        object.__setattr__(integrator_settings, "_cinder_time_span", time_span)
        if False
        else None
    )
    decoded = DecodedSimulationCase(
        assembly=assembly,
        plant=plant,
        system=system,
        initial_state=initial_state,
        initial_mode=initial_mode,
        integrator_settings=integrator_settings,
        reporting_settings=reporting_settings,
        time_span=time_span,
    )
    return decoded


def _encode_cvt_state(state: CVTState) -> dict[str, float]:
    return {
        "primary_angular_speed_rad_per_s": state.primary_angular_speed,
        "secondary_angular_speed_rad_per_s": state.secondary_angular_speed,
        "belt_speed_m_per_s": state.belt_speed,
        "shift_position_m": state.shift_position,
        "shift_speed_m_per_s": state.shift_speed,
    }


def _decode_cvt_state(payload: Mapping[str, Any]) -> CVTState:
    return CVTState(
        primary_angular_speed=_number(payload, "primary_angular_speed_rad_per_s"),
        secondary_angular_speed=_number(payload, "secondary_angular_speed_rad_per_s"),
        belt_speed=_number(payload, "belt_speed_m_per_s"),
        shift_position=_number(payload, "shift_position_m"),
        shift_speed=_number(payload, "shift_speed_m_per_s"),
    )


def _encode_shaft_boundary(boundary: object) -> dict[str, Any]:
    if isinstance(boundary, FixedShaftBoundary):
        return {
            "kind": "fixed_shaft",
            "external_torque_Nm": boundary.external_torque,
            "equivalent_inertia_kg_m2": boundary.equivalent_inertia,
        }
    if isinstance(boundary, FullThrottleEngineBoundary):
        spec = boundary.torque_curve.spec
        return {
            "kind": "full_throttle_engine",
            "points": [
                {"angular_speed_rad_per_s": p.angular_speed, "torque_Nm": p.torque}
                for p in spec.points
            ],
            "low_speed_braking_torque_Nm": spec.low_speed_braking_torque,
            "low_speed_braking_peak_speed_rad_per_s": spec.low_speed_braking_peak_speed,
            "high_speed_braking_torque_Nm": spec.high_speed_braking_torque,
            "high_speed_braking_transition_width_rad_per_s": spec.high_speed_braking_transition_width,
            "equivalent_rotational_inertia_kg_m2": boundary.equivalent_rotational_inertia,
        }
    if isinstance(boundary, LockedFinalDriveShaftBoundary):
        return {
            "kind": "locked_final_drive",
            "vehicle": {
                "mass_kg": boundary.road_load.vehicle.mass,
                "wheel_rotational_inertia_kg_m2": boundary.road_load.vehicle.wheel_rotational_inertia,
            },
            "final_drive": {
                "reduction_ratio": boundary.road_load.final_drive.reduction_ratio,
                "wheel_radius_m": boundary.road_load.final_drive.wheel_radius,
            },
            "road_load": {
                "rolling_resistance_coefficient": boundary.road_load.spec.rolling_resistance_coefficient,
                "drag_coefficient": boundary.road_load.spec.drag_coefficient,
                "frontal_area_m2": boundary.road_load.spec.frontal_area,
                "air_density_kg_per_m3": boundary.road_load.spec.air_density,
                "gravity_m_per_s2": boundary.road_load.spec.gravity,
                "rolling_speed_regularization_m_per_s": boundary.road_load.spec.rolling_speed_regularization,
            },
            "road_profile": _encode_road_profile(boundary.road_profile),
            "direct_secondary_shaft_inertia_kg_m2": boundary.direct_secondary_shaft_inertia,
        }
    raise UnsupportedSimulationDocumentError(
        f"Cannot serialize shaft boundary {type(boundary).__name__}."
    )


def _decode_shaft_boundary(payload: Mapping[str, Any]) -> object:
    kind = _string(payload, "kind")
    if kind == "fixed_shaft":
        return FixedShaftBoundary(
            external_torque=_number(payload, "external_torque_Nm"),
            equivalent_inertia=_number(payload, "equivalent_inertia_kg_m2"),
        )
    if kind == "full_throttle_engine":
        points = _sequence(_require(payload, "points"), "shaft_boundary.points")
        curve = FullThrottleTorqueCurve(
            TorqueCurveSpec(
                points=tuple(
                    EngineTorquePoint(
                        angular_speed=_number(
                            _mapping(p, f"points[{i}]"), "angular_speed_rad_per_s"
                        ),
                        torque=_number(_mapping(p, f"points[{i}]"), "torque_Nm"),
                    )
                    for i, p in enumerate(points)
                ),
                low_speed_braking_torque=_number(
                    payload, "low_speed_braking_torque_Nm"
                ),
                low_speed_braking_peak_speed=_number(
                    payload, "low_speed_braking_peak_speed_rad_per_s"
                ),
                high_speed_braking_torque=_number(
                    payload, "high_speed_braking_torque_Nm"
                ),
                high_speed_braking_transition_width=_number(
                    payload, "high_speed_braking_transition_width_rad_per_s"
                ),
            )
        )
        return FullThrottleEngineBoundary(
            curve,
            equivalent_rotational_inertia=_number(
                payload, "equivalent_rotational_inertia_kg_m2"
            ),
        )
    if kind == "locked_final_drive":
        vehicle_doc = _mapping(_require(payload, "vehicle"), "vehicle")
        final_drive_doc = _mapping(_require(payload, "final_drive"), "final_drive")
        road_load_doc = _mapping(_require(payload, "road_load"), "road_load")
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
        return LockedFinalDriveShaftBoundary(
            road_load=road_load,
            road_profile=_decode_road_profile(
                _mapping(_require(payload, "road_profile"), "road_profile")
            ),
            direct_secondary_shaft_inertia=_number(
                payload, "direct_secondary_shaft_inertia_kg_m2"
            ),
        )
    raise UnsupportedSimulationDocumentError(
        f"Unsupported shaft boundary kind {kind!r}."
    )


def _encode_host(host: object, initial_host_state) -> dict[str, Any]:
    values = list(map(float, initial_host_state))
    if isinstance(host, SecondaryShaftAngleHost):
        return {
            "kind": "secondary_shaft_angle",
            "initial_state": {"secondary_shaft_angle_rad": values[0]},
        }
    if isinstance(host, TireVehicleHost):
        return {
            "kind": "tire_vehicle",
            "initial_state": {
                "secondary_shaft_angle_rad": values[0],
                "vehicle_position_m": values[1],
                "vehicle_speed_m_per_s": values[2],
            },
        }
    raise UnsupportedSimulationDocumentError(
        f"Cannot serialize host {type(host).__name__}."
    )


def _decode_host(payload: Mapping[str, Any], *, secondary_boundary: object):
    kind = _string(payload, "kind")
    initial = _mapping(_require(payload, "initial_state"), "host.initial_state")
    if kind == "secondary_shaft_angle":
        host = SecondaryShaftAngleHost()
        return host, host.initial_state(
            secondary_shaft_angle=_number(initial, "secondary_shaft_angle_rad")
        )
    if kind == "tire_vehicle":
        host = TireVehicleHost(tire_boundary=secondary_boundary)
        return host, host.initial_state(
            secondary_shaft_angle=_number(initial, "secondary_shaft_angle_rad"),
            vehicle_position=_number(initial, "vehicle_position_m"),
            vehicle_speed=_number(initial, "vehicle_speed_m_per_s"),
        )
    raise UnsupportedSimulationDocumentError(f"Unsupported host kind {kind!r}.")


def _encode_road_profile(profile: object) -> dict[str, Any]:
    if isinstance(profile, ConstantGradeRoadProfile):
        return {"kind": "constant_grade", "grade_angle_rad": profile.grade_angle}
    if isinstance(profile, PiecewiseConstantGradeRoadProfile):
        return {
            "kind": "piecewise_constant_grade",
            "segments": [
                {"start_distance_m": s.start_distance, "grade_angle_rad": s.grade_angle}
                for s in profile.segments
            ],
        }
    raise UnsupportedSimulationDocumentError(
        f"Cannot serialize road profile {type(profile).__name__}."
    )


def _decode_road_profile(payload: Mapping[str, Any]) -> object:
    kind = _string(payload, "kind")
    if kind == "constant_grade":
        return ConstantGradeRoadProfile(grade_angle=_number(payload, "grade_angle_rad"))
    if kind == "piecewise_constant_grade":
        segments = _sequence(_require(payload, "segments"), "road_profile.segments")
        return PiecewiseConstantGradeRoadProfile(
            tuple(
                PiecewiseConstantGradeSegment(
                    start_distance=_number(
                        _mapping(s, f"segments[{i}]"), "start_distance_m"
                    ),
                    grade_angle=_number(
                        _mapping(s, f"segments[{i}]"), "grade_angle_rad"
                    ),
                )
                for i, s in enumerate(segments)
            )
        )
    raise UnsupportedSimulationDocumentError(f"Unsupported road_profile kind {kind!r}.")


def _encode_integrator_settings(settings: HybridIntegratorSettings) -> dict[str, Any]:
    return {
        "relative_tolerance": settings.relative_tolerance,
        "absolute_tolerance": settings.absolute_tolerance,
        "method": settings.method,
        "max_step": settings.max_step,
        "first_step": settings.first_step,
        "maximum_transitions": settings.maximum_transitions,
        "event_time_tolerance": settings.event_time_tolerance,
        "retain_dense_output": settings.retain_dense_output,
    }


def _decode_integrator_settings(payload: Mapping[str, Any]) -> HybridIntegratorSettings:
    first_step = payload.get("first_step")
    return HybridIntegratorSettings(
        relative_tolerance=_number(payload, "relative_tolerance"),
        absolute_tolerance=_number(payload, "absolute_tolerance"),
        method=_string(payload, "method"),
        max_step=_number_or_infinity(payload, "max_step"),
        first_step=(
            None if first_step is None else _finite_number(payload, "first_step")
        ),
        maximum_transitions=_integer(payload, "maximum_transitions"),
        event_time_tolerance=_number(payload, "event_time_tolerance"),
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
    grid_doc = _mapping(_require(payload, "grid"), "reporting.grid")
    kind = _string(grid_doc, "kind")
    if kind == "native":
        grid = ReportingGrid.native()
    elif kind == "uniform_count":
        grid = ReportingGrid.uniform_count(_integer(grid_doc, "count"))
    elif kind == "uniform_time_step":
        grid = ReportingGrid.uniform_time_step(_number(grid_doc, "step_seconds"))
    else:
        raise UnsupportedSimulationDocumentError(
            f"Unsupported reporting grid kind {kind!r}."
        )
    return ReportingSettings(
        grid=grid,
        include_contact=_boolean(payload, "include_contact"),
        include_actuation=_boolean(payload, "include_actuation"),
        include_closure_audit=_boolean(payload, "include_closure_audit"),
        include_integrated_observers=_boolean(payload, "include_integrated_observers"),
    )


def _require_document_header(root: Mapping[str, Any]) -> None:
    version = _integer(root, "schema_version")
    if version != PUBLIC_CONTRACT_VERSION:
        raise UnsupportedSimulationDocumentError(
            f"Unsupported schema_version {version}; expected {PUBLIC_CONTRACT_VERSION}."
        )
    if _string(root, "document_type") != SIMULATION_CASE_DOCUMENT_TYPE:
        raise UnsupportedSimulationDocumentError(
            f"document_type must be {SIMULATION_CASE_DOCUMENT_TYPE!r}."
        )
