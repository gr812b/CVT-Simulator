"""Persistence helpers for the experimental validation workspace.

The validation layer deliberately owns a few execution/workflow defaults that
are stricter than ordinary interactive simulations.  In particular, measured
shaft-speed replay uses CINDER's public ``speed_replay_shaft`` boundary and the
validation page always resolves runs with the replay-audited integrator
settings below.  These are validation-workflow defaults, not global CINDER
settings.
"""

from __future__ import annotations

import copy
from math import isfinite
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ExecutionPreset,
    LoadCase,
    Tune,
    ValidationRun,
    ValidationWorkspace,
    VehicleAssembly,
)
from .resolver import resolve_simulation_case

JsonDict = dict[str, Any]

DEFAULT_REPLAY_GAIN_NM_S_PER_RAD = 400.0
VALIDATION_RELATIVE_TOLERANCE = 1.0e-4
VALIDATION_ABSOLUTE_TOLERANCE = 1.0e-7
VALIDATION_MAX_STEP_S = 0.05
VALIDATION_MINIMUM_TRANSITIONS = 60
VALIDATION_TRANSITIONS_PER_SECOND = 25.0
DEFAULT_REPLAY_SAMPLE_INTERVAL_S = 0.01


def get_workspace(session: Session, *, account_id: str) -> ValidationWorkspace | None:
    return session.scalar(
        select(ValidationWorkspace).where(ValidationWorkspace.account_id == account_id)
    )


def _default_controller_templates() -> list[JsonDict]:
    """Return only controller/boundary helpers supported by validation now."""

    return [
        {
            "kind": "speed_replay_shaft",
            "label": "Measured RPM replay",
            "tracking_gain_Nm_s_per_rad": DEFAULT_REPLAY_GAIN_NM_S_PER_RAD,
        }
    ]


def _default_rpm_measurement() -> JsonDict:
    return {
        "status": "pending",
        "model": "rpm_tooth_timing",
        "unit": "rpm",
        "replaySampleIntervalS": DEFAULT_REPLAY_SAMPLE_INTERVAL_S,
    }


def _validation_integrator_defaults() -> JsonDict:
    return {
        "relativeTolerance": VALIDATION_RELATIVE_TOLERANCE,
        "absoluteTolerance": VALIDATION_ABSOLUTE_TOLERANCE,
        "maxStepS": VALIDATION_MAX_STEP_S,
        "minimumTransitions": VALIDATION_MINIMUM_TRANSITIONS,
        "transitionsPerSecond": VALIDATION_TRANSITIONS_PER_SECOND,
    }


def _default_workflow(resolved: JsonDict) -> JsonDict:
    initial = copy.deepcopy(resolved["scenario"]["initial_cvt_state"])
    return {
        "primaryMode": "physical",
        "secondaryMode": "physical",
        "speedReplay": {
            "trackingGainNmSPerRad": DEFAULT_REPLAY_GAIN_NM_S_PER_RAD,
        },
        "validationIntegrator": _validation_integrator_defaults(),
        "rpmMeasurementDefaults": {
            "primary": _default_rpm_measurement(),
            "secondary": _default_rpm_measurement(),
        },
        "manualInitialState": {
            "primaryAngularSpeedRadPerS": initial["primary_angular_speed_rad_per_s"],
            "secondaryAngularSpeedRadPerS": initial["secondary_angular_speed_rad_per_s"],
            "beltSpeedMPerS": initial["belt_speed_m_per_s"],
            "shiftPositionM": initial["shift_position_m"],
            "shiftSpeedMPerS": initial["shift_speed_m_per_s"],
        },
    }


def _normalize_mode(value: object) -> str:
    if value in {"replay_measured_speed", "track_measured_speed"}:
        return "replay_measured_speed"
    return "physical"


def _positive_number(value: object, fallback: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if isfinite(number) and number > 0.0:
            return number
    return fallback


def _upgrade_workflow(workflow: JsonDict | None, setup_document: JsonDict) -> JsonDict:
    """Migrate an autosaved legacy tracking workspace to shaft replay.

    Old validation workspaces can contain ``speedTracking``, axial tracker
    fields, and the legacy ``track_measured_speed`` mode.  Those values are
    intentionally collapsed into the current, smaller workflow rather than
    retaining dead architecture indefinitely.
    """

    raw = copy.deepcopy(workflow or {})
    initial = copy.deepcopy(setup_document["scenario"]["initial_cvt_state"])
    manual_default = {
        "primaryAngularSpeedRadPerS": initial["primary_angular_speed_rad_per_s"],
        "secondaryAngularSpeedRadPerS": initial["secondary_angular_speed_rad_per_s"],
        "beltSpeedMPerS": initial["belt_speed_m_per_s"],
        "shiftPositionM": initial["shift_position_m"],
        "shiftSpeedMPerS": initial["shift_speed_m_per_s"],
    }
    manual = copy.deepcopy(raw.get("manualInitialState") or manual_default)

    replay = raw.get("speedReplay")
    legacy_tracking = raw.get("speedTracking")
    gain_candidate = None
    if isinstance(replay, dict):
        gain_candidate = replay.get("trackingGainNmSPerRad")
    if gain_candidate is None and isinstance(legacy_tracking, dict):
        gain_candidate = legacy_tracking.get("proportionalGainNmSPerRad")
    replay_gain = _positive_number(
        gain_candidate,
        DEFAULT_REPLAY_GAIN_NM_S_PER_RAD,
    )

    rpm_defaults_raw = raw.get("rpmMeasurementDefaults")
    rpm_defaults = rpm_defaults_raw if isinstance(rpm_defaults_raw, dict) else {}
    active_dataset_raw = raw.get("activeDataset")
    active_dataset = (
        copy.deepcopy(active_dataset_raw) if isinstance(active_dataset_raw, dict) else None
    )

    upgraded = {
        "primaryMode": _normalize_mode(raw.get("primaryMode")),
        "secondaryMode": _normalize_mode(raw.get("secondaryMode")),
        "speedReplay": {"trackingGainNmSPerRad": replay_gain},
        # Always write the verified validation settings.  They are not a user
        # tuning surface and should not drift with a stale workspace.
        "validationIntegrator": _validation_integrator_defaults(),
        "rpmMeasurementDefaults": {
            "primary": {
                **_default_rpm_measurement(),
                **copy.deepcopy(
                    rpm_defaults.get("primary")
                    if isinstance(rpm_defaults.get("primary"), dict)
                    else {}
                ),
            },
            "secondary": {
                **_default_rpm_measurement(),
                **copy.deepcopy(
                    rpm_defaults.get("secondary")
                    if isinstance(rpm_defaults.get("secondary"), dict)
                    else {}
                ),
            },
        },
        "manualInitialState": manual,
    }
    if active_dataset is not None:
        upgraded["activeDataset"] = active_dataset
    return upgraded


def _apply_validation_integrator(document: JsonDict) -> JsonDict:
    result = copy.deepcopy(document)
    execution = result.setdefault("execution", {})
    integrator = execution.setdefault("integrator", {})
    integrator["relative_tolerance"] = VALIDATION_RELATIVE_TOLERANCE
    integrator["absolute_tolerance"] = VALIDATION_ABSOLUTE_TOLERANCE
    integrator["max_step"] = VALIDATION_MAX_STEP_S
    # Crop duration is unknown at workspace creation time. The frontend
    # resolves the final duration-scaled budget for each validation run.
    integrator["maximum_transitions"] = VALIDATION_MINIMUM_TRANSITIONS
    return result


def _upgrade_workspace(workspace: ValidationWorkspace) -> ValidationWorkspace:
    setup_document = _apply_validation_integrator(workspace.setup_document)
    workspace.setup_document = setup_document
    workspace.controller_templates = _default_controller_templates()
    workspace.workflow_defaults = _upgrade_workflow(
        workspace.workflow_defaults,
        setup_document,
    )
    return workspace


def ensure_workspace(session: Session, *, account_id: str) -> ValidationWorkspace:
    """Return the autosaved workspace, creating/upgrading it when necessary."""

    workspace = get_workspace(session, account_id=account_id)
    if workspace is not None:
        _upgrade_workspace(workspace)
        session.flush()
        return workspace

    assembly = session.scalar(
        select(VehicleAssembly)
        .where(
            VehicleAssembly.account_id == account_id,
            VehicleAssembly.deleted_at.is_(None),
            VehicleAssembly.released_version_id.is_not(None),
        )
        .order_by(
            VehicleAssembly.is_default.desc(),
            VehicleAssembly.catalog_priority.desc(),
        )
    )
    if assembly is None or assembly.released_version_id is None:
        raise ValueError("No released vehicle assembly is available to initialize validation.")

    tune = session.scalar(
        select(Tune)
        .where(
            Tune.account_id == account_id,
            Tune.vehicle_assembly_id == assembly.id,
            Tune.deleted_at.is_(None),
        )
        .order_by(Tune.created_at.asc())
    )
    load_case = session.scalar(
        select(LoadCase)
        .where(LoadCase.account_id == account_id, LoadCase.deleted_at.is_(None))
        .order_by(LoadCase.created_at.asc())
    )
    execution = session.scalar(
        select(ExecutionPreset)
        .where(ExecutionPreset.is_system_default.is_(True))
        .order_by(ExecutionPreset.created_at.asc())
    )

    resolved = resolve_simulation_case(
        session,
        vehicle_assembly_version_id=assembly.released_version_id,
        tune_id=tune.id if tune is not None else None,
        load_case_id=load_case.id if load_case is not None else None,
        execution_preset_id=execution.id if execution is not None else None,
    )
    resolved = _apply_validation_integrator(resolved)

    workspace = ValidationWorkspace(
        account_id=account_id,
        setup_document=copy.deepcopy(resolved),
        metrology={},
        controller_templates=_default_controller_templates(),
        workflow_defaults=_default_workflow(resolved),
    )
    session.add(workspace)
    session.flush()
    return workspace


def upsert_workspace(
    session: Session,
    *,
    account_id: str,
    setup_document: JsonDict,
    metrology: JsonDict,
    controller_templates: list[JsonDict],
    workflow_defaults: JsonDict,
) -> ValidationWorkspace:
    del controller_templates  # The validation boundary template is canonical.

    normalized_setup = _apply_validation_integrator(setup_document)
    normalized_workflow = _upgrade_workflow(workflow_defaults, normalized_setup)
    workspace = get_workspace(session, account_id=account_id)
    if workspace is None:
        workspace = ValidationWorkspace(
            account_id=account_id,
            setup_document=normalized_setup,
            metrology=copy.deepcopy(metrology),
            controller_templates=_default_controller_templates(),
            workflow_defaults=normalized_workflow,
        )
        session.add(workspace)
    else:
        workspace.setup_document = normalized_setup
        workspace.metrology = copy.deepcopy(metrology)
        workspace.controller_templates = _default_controller_templates()
        workspace.workflow_defaults = normalized_workflow
    session.flush()
    return workspace


def list_validation_runs(
    session: Session,
    *,
    limit: int = 20,
) -> list[ValidationRun]:
    bounded_limit = max(1, min(int(limit), 100))
    return list(
        session.scalars(
            select(ValidationRun).order_by(ValidationRun.created_at.desc()).limit(bounded_limit)
        )
    )


def get_validation_run(session: Session, *, run_id: str) -> ValidationRun | None:
    """Return one immutable validation run by id."""

    return session.get(ValidationRun, run_id)


def create_validation_run(
    session: Session,
    *,
    account_id: str,
    source_filename: str,
    raw_csv: str,
    crop_start_s: float,
    crop_end_s: float,
    channel_config: JsonDict,
    initial_state_config: JsonDict,
    workspace_snapshot: JsonDict,
    resolved_document: JsonDict,
    simulation_run_id: str | None,
    result_snapshot: JsonDict,
    metrics: JsonDict,
) -> ValidationRun:
    run = ValidationRun(
        account_id=account_id,
        source_filename=source_filename,
        raw_csv=raw_csv,
        crop_start_s=crop_start_s,
        crop_end_s=crop_end_s,
        channel_config=copy.deepcopy(channel_config),
        initial_state_config=copy.deepcopy(initial_state_config),
        workspace_snapshot=copy.deepcopy(workspace_snapshot),
        resolved_document=copy.deepcopy(resolved_document),
        simulation_run_id=simulation_run_id,
        result_snapshot=copy.deepcopy(result_snapshot),
        metrics=copy.deepcopy(metrics),
    )
    session.add(run)
    session.flush()
    return run
