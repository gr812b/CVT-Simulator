"""Experimental validation workspace and immutable validation-run snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_database_session
from app.core.errors import ApiProblem
from app.database.validation import (
    create_validation_run,
    ensure_workspace,
    get_validation_run,
    upsert_workspace,
)
from app.schemas.validation import (
    ValidationRunCreate,
    ValidationRunResponse,
    ValidationWorkspaceResponse,
    ValidationWorkspaceUpdate,
)

router = APIRouter(prefix="/validation", tags=["validation"])


def _workspace_response(workspace) -> ValidationWorkspaceResponse:
    return ValidationWorkspaceResponse(
        id=workspace.id,
        account_id=workspace.account_id,
        setup_document=workspace.setup_document,
        metrology=workspace.metrology,
        controller_templates=workspace.controller_templates,
        workflow_defaults=workspace.workflow_defaults,
        updated_at=workspace.updated_at,
    )


def _run_response(run) -> ValidationRunResponse:
    return ValidationRunResponse(
        id=run.id,
        account_id=run.account_id,
        source_filename=run.source_filename,
        raw_csv=run.raw_csv,
        crop_start_s=run.crop_start_s,
        crop_end_s=run.crop_end_s,
        channel_config=run.channel_config,
        initial_state_config=run.initial_state_config,
        workspace_snapshot=run.workspace_snapshot,
        resolved_document=run.resolved_document,
        simulation_run_id=run.simulation_run_id,
        result_snapshot=run.result_snapshot,
        metrics=run.metrics,
        created_at=run.created_at,
    )


@router.get("/workspace", response_model=ValidationWorkspaceResponse)
def validation_workspace(
    account_id: str,
    session: Session = Depends(get_database_session),
) -> ValidationWorkspaceResponse:
    try:
        workspace = ensure_workspace(session, account_id=account_id)
    except ValueError as error:
        raise ApiProblem(422, "validation_workspace_unavailable", str(error)) from error
    return _workspace_response(workspace)


@router.put("/workspace", response_model=ValidationWorkspaceResponse)
def save_validation_workspace(
    request: ValidationWorkspaceUpdate,
    session: Session = Depends(get_database_session),
) -> ValidationWorkspaceResponse:
    # This is intentionally last-write-wins for the current two-user workflow.
    # Named/revisioned validation setups can replace this temporary singleton
    # without changing immutable run snapshots.
    workspace = upsert_workspace(
        session,
        account_id=request.account_id,
        setup_document=request.setup_document,
        metrology=request.metrology,
        controller_templates=request.controller_templates,
        workflow_defaults=request.workflow_defaults,
    )
    return _workspace_response(workspace)


@router.post("/runs", response_model=ValidationRunResponse)
def save_validation_run(
    request: ValidationRunCreate,
    session: Session = Depends(get_database_session),
) -> ValidationRunResponse:
    if request.crop_end_s <= request.crop_start_s:
        raise ApiProblem(422, "validation_crop_invalid", "crop_end_s must be greater than crop_start_s.")
    run = create_validation_run(session, **request.model_dump())
    return _run_response(run)


@router.get("/runs/{run_id}", response_model=ValidationRunResponse)
def validation_run(
    run_id: str,
    session: Session = Depends(get_database_session),
) -> ValidationRunResponse:
    run = get_validation_run(session, run_id=run_id)
    if run is None:
        raise ApiProblem(404, "validation_run_not_found", f"Validation run {run_id!r} was not found.")
    return _run_response(run)
