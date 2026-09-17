"""Persistence helpers for the temporary single-workspace validation UX."""

from __future__ import annotations

import copy
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


def get_workspace(session: Session, *, account_id: str) -> ValidationWorkspace | None:
    return session.scalar(
        select(ValidationWorkspace).where(ValidationWorkspace.account_id == account_id)
    )


def _default_controller_templates() -> list[JsonDict]:
    return [
        {
            "kind": "speed_tracking_shaft",
            "label": "Torque-limited shaft speed tracker",
            "proportional_gain_Nm_s_per_rad": None,
            "torque_limit_Nm": None,
            "equivalent_inertia_kg_m2": 0.0,
            "feedforward_inertia_kg_m2": 0.0,
        },
        {
            "kind": "axial_motion_tracking",
            "label": "Force-limited axial motion tracker",
            "position_gain_N_per_m": None,
            "speed_gain_N_s_per_m": 0.0,
            "force_limit_N": None,
        },
    ]


def _default_workflow(resolved: JsonDict) -> JsonDict:
    initial = copy.deepcopy(resolved["scenario"]["initial_cvt_state"])
    return {
        "primaryMode": "physical",
        "secondaryMode": "physical",
        "axialMode": "physical",
        "speedTracking": {
            "proportionalGainNmSPerRad": None,
            "torqueLimitNm": None,
            "equivalentInertiaKgM2": 0.0,
            "feedforwardInertiaKgM2": 0.0,
        },
        "axialTracking": {
            "positionGainNPerM": None,
            "speedGainNSPerM": 0.0,
            "forceLimitN": None,
        },
        "manualInitialState": {
            "primaryAngularSpeedRadPerS": initial["primary_angular_speed_rad_per_s"],
            "secondaryAngularSpeedRadPerS": initial["secondary_angular_speed_rad_per_s"],
            "beltSpeedMPerS": initial["belt_speed_m_per_s"],
            "shiftPositionM": initial["shift_position_m"],
            "shiftSpeedMPerS": initial["shift_speed_m_per_s"],
        },
    }


def ensure_workspace(session: Session, *, account_id: str) -> ValidationWorkspace:
    """Return the autosaved workspace, lazily creating it from account defaults.

    Existing databases may already contain the account/library seed rows while
    missing the validation-workspace seed added later.  The validation page
    should still work after migration without requiring a manual reseed, so the
    first GET can bootstrap the singleton from the account's default released
    vehicle assembly and normal default run choices.
    """

    workspace = get_workspace(session, account_id=account_id)
    if workspace is not None:
        return workspace

    assembly = session.scalar(
        select(VehicleAssembly)
        .where(
            VehicleAssembly.account_id == account_id,
            VehicleAssembly.deleted_at.is_(None),
            VehicleAssembly.released_version_id.is_not(None),
        )
        .order_by(VehicleAssembly.is_default.desc(), VehicleAssembly.catalog_priority.desc())
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
    workspace = get_workspace(session, account_id=account_id)
    if workspace is None:
        workspace = ValidationWorkspace(
            account_id=account_id,
            setup_document=copy.deepcopy(setup_document),
            metrology=copy.deepcopy(metrology),
            controller_templates=copy.deepcopy(controller_templates),
            workflow_defaults=copy.deepcopy(workflow_defaults),
        )
        session.add(workspace)
    else:
        workspace.setup_document = copy.deepcopy(setup_document)
        workspace.metrology = copy.deepcopy(metrology)
        workspace.controller_templates = copy.deepcopy(controller_templates)
        workspace.workflow_defaults = copy.deepcopy(workflow_defaults)
    session.flush()
    return workspace



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
