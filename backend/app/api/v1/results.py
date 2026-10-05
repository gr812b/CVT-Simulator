"""Search, inspect, export and reuse public durable run evidence."""

from typing import Literal

from app.api.v1.dependencies import (
    get_container,
    get_current_principal,
    get_database_session,
    get_public_reader,
)
from app.application import run_results as service
from app.application.auth import Principal
from app.application.container import ApplicationContainer
from app.schemas.results import (
    RenameRun,
    RunExperimentDraft,
    RunHistoryPage,
    RunInspection,
    RunSeries,
)
from app.schemas.runs import RunSource, RunStatus, RunStatusResponse
from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

router = APIRouter(tags=["results"])
SessionDep = Depends(get_database_session)
PrincipalDep = Depends(get_current_principal)
ContainerDep = Depends(get_container)


@router.get("/run-history", response_model=RunHistoryPage)
def history(
    q: str = Query(default="", max_length=240),
    status: RunStatus | None = None,
    source: RunSource | None = None,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    limit: int = Query(default=24, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    oldest_first: bool = False,
    scope: Literal["own", "all"] = "own",
    author_id: str | None = None,
    session: Session = SessionDep,
    principal=Depends(get_public_reader),
    container: ApplicationContainer = ContainerDep,
):
    return service.history(
        session,
        principal,
        container.settings,
        query=q,
        status=status,
        source=source,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        oldest_first=oldest_first,
        scope=scope,
        author_id=author_id,
    )


@router.get("/runs/{run_id}/inspection", response_model=RunInspection)
def inspection(
    run_id: str,
    session: Session = SessionDep,
    principal=Depends(get_public_reader),
    container: ApplicationContainer = ContainerDep,
):
    return service.inspect_run(session, principal, container.settings, run_id)


@router.get("/runs/{run_id}/series", response_model=RunSeries)
def series(
    run_id: str,
    resolution: Literal["preview", "full"] = "preview",
    session: Session = SessionDep,
    principal=Depends(get_public_reader),
):
    return service.series(session, principal, run_id, resolution)


@router.patch("/runs/{run_id}/name", response_model=RunStatusResponse)
def rename(
    run_id: str,
    request: RenameRun,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    return service.rename(session, principal, run_id, request)


@router.get("/runs/{run_id}/experiment", response_model=RunExperimentDraft)
def experiment(
    run_id: str,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
    container: ApplicationContainer = ContainerDep,
):
    return service.experiment_draft(session, principal, container.settings, run_id)


@router.get(
    "/runs/{run_id}/exports/{kind}",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
def export(
    run_id: str,
    kind: Literal["input", "summary", "result", "csv"],
    session: Session = SessionDep,
    principal=Depends(get_public_reader),
):
    content, media, extension = service.export(session, principal, run_id, kind)
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="cinder-{run_id}-{kind}.{extension}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
