"""Persistence helpers for the temporary single-workspace validation UX."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ValidationRun, ValidationWorkspace

JsonDict = dict[str, Any]


def get_workspace(session: Session, *, account_id: str) -> ValidationWorkspace | None:
    return session.scalar(
        select(ValidationWorkspace).where(ValidationWorkspace.account_id == account_id)
    )


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
