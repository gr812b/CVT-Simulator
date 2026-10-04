"""Every simulation entry point uses the durable, account-limited queue."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import (
    get_container,
    get_current_principal,
    get_database_session,
)
from app.api.v1.run_admission import submission_attempt
from app.application import access, jobs
from app.application.auth import Principal
from app.application.container import ApplicationContainer
from app.core.errors import ApiProblem
from app.database import runs as artifacts
from app.database.base import utc_now
from app.database.experiment_models import RunNotification
from app.database.models import Run
from app.database.resolver import resolve_simulation_case
from app.schemas.runs import (
    CreateLibraryRunRequest,
    CreateRunRequest,
    RerunStoredRunRequest,
    RunActivity,
    RunInputResponse,
    RunListResponse,
    RunPreviewResponse,
    RunResultResponse,
    RunStatusResponse,
)

router = APIRouter(prefix="/runs", tags=["runs"])
PrincipalDep = Depends(get_current_principal)
SessionDep = Depends(get_database_session)
ContainerDep = Depends(get_container)


def submit_direct(
    request, session, principal, container, http, execution_profile="default"
):
    previous = submission_attempt(
        http,
        session,
        principal,
        container.settings,
        request.request_key,
        {**request.model_dump(), "execution_profile": execution_profile},
    )
    if previous:
        return jobs.status(previous)
    return jobs.status(
        jobs.submit(
            session,
            principal,
            container.settings,
            container.gateway,
            request_key=request.request_key,
            request_payload={
                **request.model_dump(),
                "execution_profile": execution_profile,
            },
            case=request.simulation_case,
            options={
                "include_reported_segments": request.include_reported_segments,
                "include_raw_trace": request.include_raw_trace,
                "execution_profile": execution_profile,
            },
        )
    )


@router.post("", response_model=RunStatusResponse, status_code=202)
def create_run(
    request: CreateRunRequest,
    http: Request,
    principal: Principal = PrincipalDep,
    session: Session = SessionDep,
    container: ApplicationContainer = ContainerDep,
):
    return submit_direct(request, session, principal, container, http)


@router.post("/from-library", response_model=RunStatusResponse, status_code=202)
def create_library_run(
    request: CreateLibraryRunRequest,
    http: Request,
    principal: Principal = PrincipalDep,
    session: Session = SessionDep,
    container: ApplicationContainer = ContainerDep,
):
    principal.require_write()
    previous = submission_attempt(
        http,
        session,
        principal,
        container.settings,
        request.request_key,
        request.model_dump(),
    )
    if previous:
        return jobs.status(previous)
    access.run_selection(session, principal, request)
    try:
        case = resolve_simulation_case(
            session,
            **request.model_dump(
                exclude={
                    "request_key",
                    "include_reported_segments",
                    "include_raw_trace",
                }
            ),
        )
    except ValueError as exc:
        raise ApiProblem(422, "library_run_resolution_failed", str(exc)) from exc
    resolution = case["database_resolution"]
    provenance = {
        "setup_revision_id": resolution["vehicle_assembly_version_id"],
        "engine_revision_id": resolution["engine_version_id"],
        "cvt_revision_id": resolution["cvt_design_version_id"],
        "output_revision_id": resolution["output_system_version_id"],
        "legacy_selection": request.model_dump(),
        "tune_values": resolution["tune_snapshot"],
        "scenario": resolution["load_case_snapshot"],
    }
    return jobs.status(
        jobs.submit(
            session,
            principal,
            container.settings,
            container.gateway,
            request_key=request.request_key,
            request_payload=request.model_dump(),
            case=case,
            provenance=provenance,
            source="library",
            options={
                "include_reported_segments": request.include_reported_segments,
                "include_raw_trace": request.include_raw_trace,
                "execution_profile": "default",
            },
        )
    )


@router.get("", response_model=RunListResponse)
def list_runs(
    principal: Principal = PrincipalDep,
    session: Session = SessionDep,
    vehicle_assembly_version_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
):
    return RunListResponse(
        items=[
            jobs.status(run, include_provenance=False)
            for run in artifacts.list_database_runs(
                session,
                account_id=principal.account_id,
                vehicle_assembly_version_id=vehicle_assembly_version_id,
                limit=limit,
            )
        ]
    )


@router.get("/activity", response_model=RunActivity)
def activity(
    principal: Principal = PrincipalDep,
    session: Session = SessionDep,
    container: ApplicationContainer = ContainerDep,
):
    return jobs.activity(session, principal, container.settings)


@router.post("/notices/{notice_id}/read", status_code=204)
def read_notice(
    notice_id: str, principal: Principal = PrincipalDep, session: Session = SessionDep
):
    notice = access.owned(session.get(RunNotification, notice_id), principal)
    if notice.user_id != principal.user_id:
        raise access.unavailable()
    notice.read_at = notice.read_at or utc_now()


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(
    run_id: str,
    principal: Principal = PrincipalDep,
    session: Session = SessionDep,
    container: ApplicationContainer = ContainerDep,
):
    access.owned(session.get(Run, run_id), principal)
    jobs.recover(session, container.settings, principal.account_id)
    return jobs.status(session.get(Run, run_id))


@router.post("/{run_id}/cancel", response_model=RunStatusResponse)
def cancel(
    run_id: str, principal: Principal = PrincipalDep, session: Session = SessionDep
):
    return jobs.status(jobs.cancel(session, principal, run_id))


@router.post("/{run_id}/rerun", response_model=RunStatusResponse, status_code=202)
def rerun(
    run_id: str,
    request: RerunStoredRunRequest,
    http: Request,
    principal: Principal = PrincipalDep,
    session: Session = SessionDep,
    container: ApplicationContainer = ContainerDep,
):
    source = access.owned(session.get(Run, run_id), principal)
    previous = submission_attempt(
        http,
        session,
        principal,
        container.settings,
        request.request_key,
        {"parent_run_id": run_id, **request.model_dump()},
    )
    if previous:
        return jobs.status(previous)
    return jobs.status(
        jobs.submit(
            session,
            principal,
            container.settings,
            container.gateway,
            request_key=request.request_key,
            request_payload={"parent_run_id": run_id, **request.model_dump()},
            case=source.input_contract,
            provenance=source.provenance,
            name=f"{source.name[:230]} (rerun)",
            source=source.source,
            parent_run_id=source.id,
            options={
                **(source.execution_options or {}),
                "include_reported_segments": request.include_reported_segments,
                "include_raw_trace": request.include_raw_trace,
                "execution_profile": (source.execution_options or {}).get(
                    "execution_profile", "default"
                ),
            },
        )
    )


@router.get("/{run_id}/input", response_model=RunInputResponse)
def input_document(
    run_id: str, principal: Principal = PrincipalDep, session: Session = SessionDep
):
    run = access.owned(session.get(Run, run_id), principal)
    return RunInputResponse(
        run=jobs.status(run), input_document_snapshot=run.input_contract
    )


@router.get("/{run_id}/preview", response_model=RunPreviewResponse)
def preview(
    run_id: str, principal: Principal = PrincipalDep, session: Session = SessionDep
):
    run = access.owned(session.get(Run, run_id), principal)
    return RunPreviewResponse(
        run=jobs.status(run),
        preview=artifacts.get_database_run_preview(session, run_id),
    )


@router.get("/{run_id}/result", response_model=RunResultResponse)
def result(
    run_id: str, principal: Principal = PrincipalDep, session: Session = SessionDep
):
    run = access.owned(session.get(Run, run_id), principal)
    return RunResultResponse(
        run=jobs.status(run),
        input_document_snapshot=run.input_contract,
        result=artifacts.get_database_run_result(session, run_id),
    )
