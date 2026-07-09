"""Resolve versioned database objects into a frozen CINDER simulation case.

This module is independent from HTTP transport. Routes and smoke tests use it to
turn released library versions plus tune/load/execution choices into the exact
CINDER document stored on a run.
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


def resolve_simulation_case(
    session: Session,
    *,
    vehicle_assembly_version_id: str,
    tune_id: str | None = None,
    load_case_id: str | None = None,
    execution_preset_id: str | None = None,
) -> JsonDict:
    """Build a complete, immutable CINDER case from released versions and options."""

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

    cinder_assembly = copy.deepcopy(cvt_version.cinder_assembly)
    tune_snapshot: JsonDict = {}
    if tune_id is not None:
        tune = session.get(Tune, tune_id)
        if tune is None:
            raise ValueError(f"Unknown tune {tune_id!r}.")
        tune_snapshot = copy.deepcopy(tune.values)
        apply_tune(cinder_assembly, cvt_version.tuning_schema, tune_snapshot)

    output_boundary = copy.deepcopy(output_version.output_boundary_template)
    scenario: JsonDict = {}
    load_case_snapshot: JsonDict = {}
    if load_case_id is not None:
        load_case = session.get(LoadCase, load_case_id)
        if load_case is None:
            raise ValueError(f"Unknown load case {load_case_id!r}.")
        load_case_snapshot = copy.deepcopy(load_case.payload)
        scenario = copy.deepcopy(load_case.payload.get("scenario", {}))
        _deep_merge(output_boundary, load_case.payload.get("output_boundary_overrides", {}))

    execution: JsonDict = {}
    execution_snapshot: JsonDict = {}
    if execution_preset_id is not None:
        execution_preset = session.get(ExecutionPreset, execution_preset_id)
        if execution_preset is None:
            raise ValueError(f"Unknown execution preset {execution_preset_id!r}.")
        execution_snapshot = copy.deepcopy(execution_preset.payload)
        execution = copy.deepcopy(execution_preset.payload)

    document: JsonDict = {
        "schema_version": 1,
        "document_type": "cinder_simulation_case",
        "assembly": cinder_assembly,
        "input_boundary": copy.deepcopy(engine_version.input_boundary),
        "output_boundary": output_boundary,
        "scenario": scenario,
        "execution": execution,
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
    document["contract_hash"] = canonical_json_hash(
        {
            key: copy.deepcopy(document[key])
            for key in (
                "schema_version",
                "document_type",
                "assembly",
                "input_boundary",
                "output_boundary",
                "scenario",
                "execution",
            )
            if key in document
        }
    )
    return document


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
    """Apply tune values to a CINDER assembly using JSON pointer paths.

    Unknown tune keys are ignored deliberately in V1 so old runs remain loadable if
    a design's tuning schema changes. The released version and run snapshot are
    still the source of truth.
    """

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
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target
