"""Resolve versioned database objects into a frozen CINDER simulation case.

The database deliberately stores engine/CVT/output/load/execution objects
separately. This module is the translation boundary that resolves those V1
library objects into CINDER's current public composed-simulation contract.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.database.hashing import canonical_json_hash
from app.database.models import (
    CVTDesignVersion,
    EngineVersion,
    ExecutionPreset,
    LoadCase,
    OutputSystemVersion,
    Tune,
    VehicleAssemblyVersion,
)

JsonDict = dict[str, Any]

CURRENT_SIMULATION_DOCUMENT_TYPE = "cinder_composed_simulation_case"
CURRENT_ASSEMBLY_DOCUMENT_TYPE = "cinder_cvt_assembly"

# The Run cache still hashes these compatibility aliases in V1. Keep them on
# the resolved document until the database/run-cache contract is revised.
V1_EXECUTABLE_HASH_KEYS = (
    "schema_version",
    "document_type",
    "assembly",
    "input_boundary",
    "output_boundary",
    "scenario",
    "execution",
)


def resolve_simulation_case(
    session: Session,
    *,
    vehicle_assembly_version_id: str,
    tune_id: str | None = None,
    load_case_id: str | None = None,
    execution_preset_id: str | None = None,
) -> JsonDict:
    """Build one immutable current-format CINDER case from V1 library objects."""

    assembly_version = session.get(VehicleAssemblyVersion, vehicle_assembly_version_id)
    if assembly_version is None:
        raise ValueError(f"Unknown vehicle assembly version {vehicle_assembly_version_id!r}.")

    engine_version = session.get(EngineVersion, assembly_version.engine_version_id)
    cvt_version = session.get(CVTDesignVersion, assembly_version.cvt_design_version_id)
    output_version = session.get(OutputSystemVersion, assembly_version.output_system_version_id)
    if engine_version is None or cvt_version is None or output_version is None:
        raise ValueError(
            "Vehicle assembly version references a missing released component version."
        )

    version_warnings = _collect_version_warnings(
        engine_version=engine_version,
        cvt_version=cvt_version,
        output_version=output_version,
        assembly_version=assembly_version,
    )

    # Tune values are intentionally applied to the stored V1 CVT payload before
    # translating it. The existing tuning-schema JSON pointers therefore remain
    # valid and the frontend tuning surface does not need to change.
    stored_assembly = copy.deepcopy(cvt_version.cinder_assembly)
    tune_snapshot: JsonDict = {}
    if tune_id is not None:
        tune = session.get(Tune, tune_id)
        if tune is None:
            raise ValueError(f"Unknown tune {tune_id!r}.")
        tune_snapshot = copy.deepcopy(tune.values)
        apply_tune(stored_assembly, cvt_version.tuning_schema, tune_snapshot)

    stored_secondary_boundary = copy.deepcopy(output_version.output_boundary_template)
    stored_scenario: JsonDict = {}
    load_case_snapshot: JsonDict = {}
    if load_case_id is not None:
        load_case = session.get(LoadCase, load_case_id)
        if load_case is None:
            raise ValueError(f"Unknown load case {load_case_id!r}.")
        load_case_snapshot = copy.deepcopy(load_case.payload)
        stored_scenario = copy.deepcopy(load_case.payload.get("scenario", {}))
        _deep_merge(
            stored_secondary_boundary,
            load_case.payload.get("output_boundary_overrides", {}),
        )

    stored_execution: JsonDict = {}
    execution_snapshot: JsonDict = {}
    if execution_preset_id is not None:
        execution_preset = session.get(ExecutionPreset, execution_preset_id)
        if execution_preset is None:
            raise ValueError(f"Unknown execution preset {execution_preset_id!r}.")
        execution_snapshot = copy.deepcopy(execution_preset.payload)
        stored_execution = copy.deepcopy(execution_preset.payload)

    assembly = _current_assembly_document(stored_assembly, stored_execution)
    primary_boundary = _current_primary_boundary(engine_version.input_boundary)
    secondary_boundary = _current_secondary_boundary(stored_secondary_boundary)
    host, scenario = _current_host_and_scenario(stored_scenario)
    execution = _current_execution(stored_execution)

    document: JsonDict = {
        "schema_version": 1,
        "document_type": CURRENT_SIMULATION_DOCUMENT_TYPE,
        "assembly": assembly,
        "shaft_boundaries": {
            "primary": primary_boundary,
            "secondary": secondary_boundary,
        },
        "host": host,
        "scenario": scenario,
        "execution": execution,
        # V1 compatibility aliases used only by the existing run-cache hash.
        # CINDER ignores these extra top-level fields.
        "input_boundary": copy.deepcopy(primary_boundary),
        "output_boundary": copy.deepcopy(secondary_boundary),
        "database_resolution": {
            "engine_version_id": engine_version.id,
            "cvt_design_version_id": cvt_version.id,
            "output_system_version_id": output_version.id,
            "vehicle_assembly_version_id": assembly_version.id,
            "tune_id": tune_id,
            "load_case_id": load_case_id,
            "execution_preset_id": execution_preset_id,
            "tune_snapshot": tune_snapshot,
            "load_case_snapshot": load_case_snapshot,
            "execution_snapshot": execution_snapshot,
            "version_warnings": version_warnings,
        },
    }

    # Match backend.app.database.runs.executable_contract for the current V1
    # database schema/cache implementation. The aliases above ensure engine and
    # output-system differences remain part of the cache key.
    document["contract_hash"] = canonical_json_hash(
        {
            key: copy.deepcopy(document[key])
            for key in V1_EXECUTABLE_HASH_KEYS
            if key in document
        }
    )
    return document


def _current_assembly_document(
    stored_assembly: JsonDict,
    stored_execution: JsonDict,
) -> JsonDict:
    """Translate the V1 stored CVT payload to the current assembly contract."""

    assembly = copy.deepcopy(stored_assembly)
    assembly["schema_version"] = 1
    assembly["document_type"] = CURRENT_ASSEMBLY_DOCUMENT_TYPE

    pulleys = assembly.setdefault("pulleys", {})
    if "primary" not in pulleys and "input" in pulleys:
        pulleys["primary"] = pulleys.pop("input")
    if "secondary" not in pulleys and "output" in pulleys:
        pulleys["secondary"] = pulleys.pop("output")

    if "primary" not in pulleys or "secondary" not in pulleys:
        raise ValueError(
            "CVT design must define both primary and secondary pulley payloads."
        )

    _normalize_contact(assembly, stored_execution)
    _normalize_inertias(assembly)
    return assembly


def _normalize_contact(assembly: JsonDict, stored_execution: JsonDict) -> None:
    contact = assembly.setdefault("contact", {})
    traction = stored_execution.get("traction_law", {})
    if not isinstance(traction, dict):
        traction = {}

    legacy_friction = contact.get("friction_coefficient")
    fallback = (
        float(legacy_friction)
        if isinstance(legacy_friction, (int, float)) and not isinstance(legacy_friction, bool)
        else None
    )

    static = _shared_traction_limit(
        traction,
        "primary_static_lambda_limit",
        "secondary_static_lambda_limit",
        fallback=fallback,
        label="static",
    )
    kinetic = _shared_traction_limit(
        traction,
        "primary_kinetic_lambda_magnitude",
        "secondary_kinetic_lambda_magnitude",
        fallback=static,
        label="kinetic",
    )

    contact.clear()
    contact["static_friction_coefficient"] = static
    contact["kinetic_friction_coefficient"] = kinetic


def _shared_traction_limit(
    traction: JsonDict,
    primary_key: str,
    secondary_key: str,
    *,
    fallback: float | None,
    label: str,
) -> float:
    primary = traction.get(primary_key)
    secondary = traction.get(secondary_key)

    if primary is None and secondary is None:
        if fallback is None:
            raise ValueError(
                f"Cannot resolve {label} belt-contact coefficient from the V1 payload."
            )
        return float(fallback)

    if primary is None:
        primary = secondary
    if secondary is None:
        secondary = primary

    if (
        isinstance(primary, bool)
        or isinstance(secondary, bool)
        or not isinstance(primary, (int, float))
        or not isinstance(secondary, (int, float))
    ):
        raise ValueError(f"{label.capitalize()} traction limits must be numeric.")

    primary_value = float(primary)
    secondary_value = float(secondary)
    if abs(primary_value - secondary_value) > 1e-12:
        raise ValueError(
            "The current CINDER public contract uses one belt-contact "
            f"{label} coefficient, but the V1 primary/secondary limits differ "
            f"({primary_value} vs {secondary_value})."
        )
    return primary_value


def _normalize_inertias(assembly: JsonDict) -> None:
    inertias = assembly.get("inertias")
    if not isinstance(inertias, dict):
        raise ValueError("CVT design is missing inertias.")

    primary = inertias.get("primary")
    secondary = inertias.get("secondary")
    if not isinstance(primary, dict) or not isinstance(secondary, dict):
        raise ValueError("CVT design must define primary and secondary inertias.")

    _rename_first_present(
        primary,
        "fixed_rotating_hardware_inertia_kg_m2",
        (
            "rotating_hardware_inertia_kg_m2",
            "cvt_rotational_inertia_kg_m2",
        ),
    )
    primary.setdefault("movable_sheave_rotational_inertia_kg_m2", 0.0)
    primary.pop("engine_rotational_inertia_kg_m2", None)

    _rename_first_present(
        secondary,
        "fixed_rotating_hardware_inertia_kg_m2",
        (
            "fixed_rotational_inertia_kg_m2",
            "rotating_hardware_inertia_kg_m2",
        ),
    )
    secondary.setdefault("movable_sheave_rotational_inertia_kg_m2", 0.0)
    secondary.pop("gearbox_input_rotational_inertia_kg_m2", None)

    required_primary = (
        "fixed_rotating_hardware_inertia_kg_m2",
        "movable_sheave_rotational_inertia_kg_m2",
        "moving_sheave_mass_kg",
    )
    required_secondary = required_primary
    for key in required_primary:
        if key not in primary:
            raise ValueError(f"Primary inertia payload is missing {key!r}.")
    for key in required_secondary:
        if key not in secondary:
            raise ValueError(f"Secondary inertia payload is missing {key!r}.")


def _rename_first_present(
    payload: JsonDict,
    target_key: str,
    source_keys: tuple[str, ...],
) -> None:
    if target_key in payload:
        for source_key in source_keys:
            payload.pop(source_key, None)
        return

    for source_key in source_keys:
        if source_key in payload:
            payload[target_key] = payload.pop(source_key)
            break

    for source_key in source_keys:
        payload.pop(source_key, None)


def _current_primary_boundary(stored_boundary: JsonDict) -> JsonDict:
    boundary = copy.deepcopy(stored_boundary)
    kind = boundary.get("kind")
    if kind == "full_throttle_torque_curve":
        boundary["kind"] = "full_throttle_engine"
    elif kind != "full_throttle_engine":
        raise ValueError(f"Unsupported V1 engine boundary kind {kind!r}.")
    return boundary


def _current_secondary_boundary(stored_boundary: JsonDict) -> JsonDict:
    boundary = copy.deepcopy(stored_boundary)
    kind = boundary.get("kind")
    if kind == "locked_final_drive_vehicle":
        boundary["kind"] = "locked_final_drive"
    elif kind != "locked_final_drive":
        raise ValueError(f"Unsupported V1 output boundary kind {kind!r}.")

    # This belonged to the old boundary layer and is not part of the current
    # composed CINDER public contract.
    boundary.pop("drivetrain_loss_model", None)
    return boundary


def _current_host_and_scenario(stored_scenario: JsonDict) -> tuple[JsonDict, JsonDict]:
    if not stored_scenario:
        raise ValueError("Load case does not define a scenario.")

    span = copy.deepcopy(stored_scenario.get("time_span_s"))
    if not isinstance(span, list) or len(span) != 2:
        raise ValueError("scenario.time_span_s must contain exactly two values.")

    legacy_initial = stored_scenario.get("initial_state")
    current_initial = stored_scenario.get("initial_cvt_state")
    if isinstance(current_initial, dict):
        initial = copy.deepcopy(current_initial)
        legacy_host_source = stored_scenario.get("initial_host_state", {})
    elif isinstance(legacy_initial, dict):
        initial = copy.deepcopy(legacy_initial)
        legacy_host_source = legacy_initial
    else:
        raise ValueError(
            "Scenario must define initial_state or initial_cvt_state."
        )

    cvt_keys = (
        "primary_angular_speed_rad_per_s",
        "secondary_angular_speed_rad_per_s",
        "belt_speed_m_per_s",
        "shift_position_m",
        "shift_speed_m_per_s",
    )
    missing = [key for key in cvt_keys if key not in initial]
    if missing:
        raise ValueError(
            "Scenario initial state is missing required CVT values: "
            + ", ".join(missing)
        )

    initial_cvt_state = {key: copy.deepcopy(initial[key]) for key in cvt_keys}

    shaft_angle = 0.0
    if isinstance(legacy_host_source, dict):
        shaft_angle = legacy_host_source.get("secondary_shaft_angle_rad", 0.0)

    has_vehicle_state = isinstance(legacy_host_source, dict) and (
        "vehicle_position_m" in legacy_host_source
        or "vehicle_speed_m_per_s" in legacy_host_source
    )
    if has_vehicle_state:
        host = {
            "kind": "tire_vehicle",
            "initial_state": {
                "secondary_shaft_angle_rad": shaft_angle,
                "vehicle_position_m": legacy_host_source.get("vehicle_position_m", 0.0),
                "vehicle_speed_m_per_s": legacy_host_source.get("vehicle_speed_m_per_s", 0.0),
            },
        }
    else:
        host = {
            "kind": "secondary_shaft_angle",
            "initial_state": {
                "secondary_shaft_angle_rad": shaft_angle,
            },
        }

    scenario = {
        "time_span_s": span,
        "initial_cvt_state": initial_cvt_state,
    }
    return host, scenario


def _current_execution(stored_execution: JsonDict) -> JsonDict:
    if not stored_execution:
        raise ValueError("Execution preset payload is empty.")

    integrator = stored_execution.get("integrator")
    reporting = stored_execution.get("reporting")
    if not isinstance(integrator, dict):
        raise ValueError("Execution preset is missing integrator settings.")
    if not isinstance(reporting, dict):
        raise ValueError("Execution preset is missing reporting settings.")

    current_integrator = copy.deepcopy(integrator)
    _rename_key_if_needed(current_integrator, "max_step", "max_step_s")
    _rename_key_if_needed(current_integrator, "first_step", "first_step_s")
    _rename_key_if_needed(
        current_integrator,
        "event_time_tolerance",
        "event_time_tolerance_s",
    )

    required = (
        "relative_tolerance",
        "absolute_tolerance",
        "method",
        "max_step",
        "first_step",
        "maximum_transitions",
        "event_time_tolerance",
        "retain_dense_output",
    )
    missing = [key for key in required if key not in current_integrator]
    if missing:
        raise ValueError(
            "Execution integrator is missing required values: " + ", ".join(missing)
        )

    # Only the current public execution contract is emitted. Legacy traction,
    # closure, operating-limit, and switching dictionaries were internal to the
    # previous execution layer; the belt traction coefficients are translated
    # into assembly.contact above.
    return {
        "integrator": current_integrator,
        "reporting": copy.deepcopy(reporting),
    }


def _rename_key_if_needed(payload: JsonDict, current_key: str, legacy_key: str) -> None:
    if current_key not in payload and legacy_key in payload:
        payload[current_key] = payload.pop(legacy_key)
    else:
        payload.pop(legacy_key, None)


def _collect_version_warnings(
    *,
    engine_version: EngineVersion,
    cvt_version: CVTDesignVersion,
    output_version: OutputSystemVersion,
    assembly_version: VehicleAssemblyVersion,
) -> list[JsonDict]:
    warnings: list[JsonDict] = []
    for object_type, version in (
        ("engine", engine_version),
        ("cvt_design", cvt_version),
        ("output_system", output_version),
        ("vehicle_assembly", assembly_version),
    ):
        status = version.validation_status
        if status in {"invalid", "unsupported"}:
            raise ValueError(
                f"{object_type} version {version.id} has validation_status={status!r} "
                "and cannot be resolved."
            )
        if status in {"deprecated", "needs_migration"}:
            warnings.append(
                {
                    "object_type": object_type,
                    "version_id": version.id,
                    "validation_status": status,
                    "superseded_by_version_id": version.superseded_by_version_id,
                    "messages": copy.deepcopy(version.validation_messages),
                }
            )
    return warnings


def apply_tune(cinder_assembly: JsonDict, tuning_schema: JsonDict, values: JsonDict) -> None:
    """Apply tune values to the stored V1 assembly using its JSON-pointer schema."""

    params = tuning_schema.get("parameters", [])
    path_by_key = {
        str(param["key"]): str(param["path"])
        for param in params
        if isinstance(param, dict) and "key" in param and "path" in param
    }
    for key, value in values.items():
        path = path_by_key.get(key)
        if path is not None:
            _set_json_pointer(cinder_assembly, path, value)


def _set_json_pointer(document: JsonDict, pointer: str, value: Any) -> None:
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer!r}.")
    current: Any = document
    parts = [_unescape_json_pointer(part) for part in pointer.split("/")[1:]]
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
    else:
        current[last] = value


def _unescape_json_pointer(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _deep_merge(target: JsonDict, overrides: JsonDict) -> JsonDict:
    for key, value in overrides.items():
        existing = target.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            # Discriminated sub-documents must be replaced when their kind
            # changes. Otherwise a constant-grade profile changed to a
            # piecewise route would keep stale legacy fields.
            if (
                "kind" in value
                and "kind" in existing
                and value["kind"] != existing["kind"]
            ):
                target[key] = copy.deepcopy(value)
            else:
                _deep_merge(existing, value)
        else:
            target[key] = copy.deepcopy(value)
    return target
