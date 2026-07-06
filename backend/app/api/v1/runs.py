"""Asynchronous simulation-run lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import get_container
from app.application.container import ApplicationContainer
from app.schemas.runs import CreateRunRequest, RunResultResponse, RunStatusResponse
from app.storage.run_store import RunRecord

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    request: CreateRunRequest,
    container: ApplicationContainer = Depends(get_container),
) -> RunStatusResponse:
    record = container.runs.submit(
        request.simulation_case,
        include_reported_segments=request.include_reported_segments,
        include_raw_trace=request.include_raw_trace,
    )
    return _status(record)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> RunStatusResponse:
    return _status(container.runs.status(run_id))


@router.get("/{run_id}/result", response_model=RunResultResponse)
def get_run_result(
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> RunResultResponse:
    record = container.runs.completed_result(run_id)
    assert record.result_snapshot is not None
    return RunResultResponse(
        run=_status(record),
        input_document_snapshot=record.input_document_snapshot,
        result=record.result_snapshot,
    )


def _status(record: RunRecord) -> RunStatusResponse:
    return RunStatusResponse(
        id=record.id,
        status=record.status,
        submitted_at=record.submitted_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error=record.error,
    )
