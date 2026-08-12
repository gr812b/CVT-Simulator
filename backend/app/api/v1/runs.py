"""Simulation-run lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_container, get_database_session
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem, RunNotFoundError
from app.database import runs as db_runs
from app.database.runs import LibraryRunError
from app.schemas.runs import (
    CreateLibraryRunRequest,
    CreateRunRequest,
    RunInputResponse,
    RunListResponse,
    RunPreviewResponse,
    RunResultResponse,
    RunStatusResponse,
    RerunStoredRunRequest,
)
from app.storage.run_store import RunRecord

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    request: CreateRunRequest,
    container: ApplicationContainer = Depends(get_container),
) -> RunStatusResponse:
    """Submit a complete CINDER simulation-case document directly.

    This remains the debug/contract endpoint. Database-backed product flows
    should use ``POST /runs/from-library`` so the resolved input contract and
    result artifacts are persisted.
    """

    record = container.runs.submit(
        request.simulation_case,
        include_reported_segments=request.include_reported_segments,
        include_raw_trace=request.include_raw_trace,
    )
    return _direct_status(record)


@router.post(
    "/from-library",
    response_model=RunStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_run_from_library(
    request: CreateLibraryRunRequest,
    container: ApplicationContainer = Depends(get_container),
    session: Session = Depends(get_database_session),
) -> RunStatusResponse:
    """Resolve released database objects into a frozen CINDER case and run it."""

    try:
        submitted = db_runs.submit_library_run(
            session,
            gateway=container.gateway,
            account_id=request.account_id,
            vehicle_assembly_version_id=request.vehicle_assembly_version_id,
            tune_id=request.tune_id,
            load_case_id=request.load_case_id,
            execution_preset_id=request.execution_preset_id,
            created_by_user_id=request.created_by_user_id,
            include_reported_segments=request.include_reported_segments,
            include_raw_trace=request.include_raw_trace,
        )
    except LibraryRunError as exc:
        raise ApiProblem(exc.status_code, exc.code, str(exc)) from exc
    return _database_status(submitted.run, cache_hit=submitted.cache_hit)


@router.get("", response_model=RunListResponse)
def list_runs(
    account_id: str | None = Query(default=None),
    vehicle_assembly_version_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=250),
    session: Session = Depends(get_database_session),
) -> RunListResponse:
    """List persisted database-backed runs.

    Direct in-memory debug runs are intentionally not listed because they are
    process-local and not part of durable history.
    """

    return RunListResponse(
        items=[
            _database_status(run)
            for run in db_runs.list_database_runs(
                session,
                account_id=account_id,
                vehicle_assembly_version_id=vehicle_assembly_version_id,
                limit=limit,
            )
        ]
    )


@router.post(
    "/{run_id}/rerun",
    response_model=RunStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def rerun_stored_run(
    run_id: str,
    request: RerunStoredRunRequest | None = None,
    container: ApplicationContainer = Depends(get_container),
    session: Session = Depends(get_database_session),
) -> RunStatusResponse:
    """Rerun a persisted library run from its frozen stored input.

    This is the product-facing path for old runs whose full-result artifact was
    evicted. It does not re-resolve current library objects, so archived,
    deprecated, or edited source objects cannot change the rerun semantics.
    """

    request = request or RerunStoredRunRequest()
    try:
        submitted = db_runs.submit_rerun_from_database_run(
            session,
            gateway=container.gateway,
            source_run_id=run_id,
            created_by_user_id=request.created_by_user_id,
            include_reported_segments=request.include_reported_segments,
            include_raw_trace=request.include_raw_trace,
        )
    except RunNotFoundError:
        raise
    return _database_status(submitted.run, cache_hit=submitted.cache_hit)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
    session: Session = Depends(get_database_session),
) -> RunStatusResponse:
    try:
        return _direct_status(container.runs.status(run_id))
    except RunNotFoundError:
        return _database_status(db_runs.get_database_run(session, run_id))


@router.get("/{run_id}/input", response_model=RunInputResponse)
def get_run_input(
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
    session: Session = Depends(get_database_session),
) -> RunInputResponse:
    """Return the frozen simulation input document for inspection/debugging.

    This remains available even when a persisted library run's full-result
    artifact has been evicted. Product reruns should use ``POST
    /runs/{run_id}/rerun`` so the regenerated result is persisted.
    """

    try:
        record = container.runs.status(run_id)
    except RunNotFoundError:
        run = db_runs.get_database_run(session, run_id)
        return RunInputResponse(
            run=_database_status(run),
            input_document_snapshot=db_runs.get_database_run_input_contract(session, run_id),
        )
    return RunInputResponse(
        run=_direct_status(record),
        input_document_snapshot=record.input_document_snapshot,
    )


@router.get("/{run_id}/preview", response_model=RunPreviewResponse)
def get_run_preview(
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
    session: Session = Depends(get_database_session),
) -> RunPreviewResponse:
    """Return the durable lightweight preview for charts and run browsing."""

    try:
        record = container.runs.completed_result(run_id)
    except RunNotFoundError:
        run = db_runs.get_database_run(session, run_id)
        return RunPreviewResponse(
            run=_database_status(run),
            preview=db_runs.get_database_run_preview(session, run_id),
        )
    assert record.result_snapshot is not None
    return RunPreviewResponse(
        run=_direct_status(record),
        preview=db_runs.build_preview_from_result(record.result_snapshot),
    )


@router.get("/{run_id}/result", response_model=RunResultResponse)
def get_run_result(
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
    session: Session = Depends(get_database_session),
) -> RunResultResponse:
    try:
        record = container.runs.completed_result(run_id)
    except RunNotFoundError:
        run = db_runs.get_database_run(session, run_id)
        return RunResultResponse(
            run=_database_status(run),
            input_document_snapshot=run.input_contract,
            result=db_runs.get_database_run_result(session, run_id),
        )
    assert record.result_snapshot is not None
    return RunResultResponse(
        run=_direct_status(record),
        input_document_snapshot=record.input_document_snapshot,
        result=record.result_snapshot,
    )


def _direct_status(record: RunRecord) -> RunStatusResponse:
    return RunStatusResponse(
        id=record.id,
        status=record.status,
        submitted_at=record.submitted_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error=record.error,
        source="direct",
        contract_hash=record.input_fingerprint,
    )


def _database_status(run: object, *, cache_hit: bool | None = None) -> RunStatusResponse:
    return RunStatusResponse(
        id=run.id,
        status=run.status,
        submitted_at=run.submitted_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error=run.error,
        source="library",
        contract_hash=run.contract_hash,
        cache_entry_id=run.cache_entry_id,
        cache_hit=cache_hit,
        vehicle_assembly_version_id=run.vehicle_assembly_version_id,
        summary_scalars=run.summary_scalars or {},
    )
