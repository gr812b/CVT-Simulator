"""Typed scenario/tune intent and immutable revision operations."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import (
    get_container,
    get_current_principal,
    get_database_session,
)
from app.api.v1.run_admission import submission_attempt
from app.application import access, jobs, roads
from app.application import experiments as service
from app.application.auth import Principal
from app.application.container import ApplicationContainer
from app.application.experiment_tuning import tune_surface
from app.application.physical_library import differences
from app.database.models import Run
from app.schemas.experiments import (
    ExperimentArchive,
    ExperimentCompare,
    ExperimentCopy,
    ExperimentDetail,
    ExperimentItem,
    ExperimentKind,
    ExperimentList,
    ExperimentMetadata,
    ExperimentPreview,
    ExperimentRestore,
    ExperimentSave,
    ExperimentSaved,
    ExperimentSelection,
    RoadResolution,
    SpatialRoad,
    SubmitExperiment,
    TuneSurface,
)
from app.schemas.runs import RunStatusResponse

router = APIRouter(prefix="/experiments", tags=["experiments"])
PrincipalDep = Depends(get_current_principal)
SessionDep = Depends(get_database_session)
ContainerDep = Depends(get_container)


@router.get("/metadata", response_model=ExperimentMetadata)
def metadata(container: ApplicationContainer = ContainerDep):
    return roads.metadata(container.settings)


@router.post("/road/resolve", response_model=RoadResolution)
def resolve_road(request: SpatialRoad, container: ApplicationContainer = ContainerDep):
    return roads.resolve_road(request, container.settings)


@router.get("/tuning/{setup_revision_id}", response_model=TuneSurface)
def tuning(
    setup_revision_id: str,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    return tune_surface(session, principal, setup_revision_id)


@router.post("/preview", response_model=ExperimentPreview)
def preview(
    request: ExperimentSelection,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
    container: ApplicationContainer = ContainerDep,
):
    return service.resolve(session, principal, container.settings, request)


@router.post("/runs", response_model=RunStatusResponse, status_code=202)
def submit(
    request: SubmitExperiment,
    http: Request,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
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
    if request.parent_run_id:
        access.owned(session.get(Run, request.parent_run_id), principal)
    resolved = service.resolve(session, principal, container.settings, request)
    return jobs.status(
        jobs.submit(
            session,
            principal,
            container.settings,
            container.gateway,
            request_key=request.request_key,
            request_payload=request.model_dump(),
            name=request.name,
            source="experiment",
            case=resolved.simulation_case,
            provenance=resolved.provenance,
            parent_run_id=request.parent_run_id,
        )
    )


@router.get("/items/{kind}", response_model=ExperimentList)
def list_items(
    kind: ExperimentKind,
    include_archived: bool = False,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    return ExperimentList(
        items=service.list_items(session, principal, kind, include_archived)
    )


@router.post("/items", response_model=ExperimentSaved, status_code=201)
def create(
    request: ExperimentSave,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
    container: ApplicationContainer = ContainerDep,
):
    obj, changed = service.save(
        session,
        principal,
        container.settings,
        request.document,
        expected=request.expected_revision_id,
        note=request.change_note,
    )
    return ExperimentSaved(
        detail=service.detail(session, principal, obj.id), changed=changed
    )


@router.get("/items/{object_id}/detail", response_model=ExperimentDetail)
def detail(
    object_id: str,
    revision_id: str | None = None,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    return service.detail(session, principal, object_id, revision_id)


@router.put("/items/{object_id}", response_model=ExperimentSaved)
def save(
    object_id: str,
    request: ExperimentSave,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
    container: ApplicationContainer = ContainerDep,
):
    obj, changed = service.save(
        session,
        principal,
        container.settings,
        request.document,
        object_id=object_id,
        expected=request.expected_revision_id,
        note=request.change_note,
    )
    return ExperimentSaved(
        detail=service.detail(session, principal, obj.id), changed=changed
    )


@router.post("/copy", response_model=ExperimentDetail, status_code=201)
def copy(
    request: ExperimentCopy,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
    container: ApplicationContainer = ContainerDep,
):
    revision = service.get_revision(session, principal, request.revision_id)
    document = service.DOCUMENT.validate_python(revision.document)
    document.name = request.name or f"{document.name[:230]} (copy)"
    obj, _ = service.save(
        session,
        principal,
        container.settings,
        document,
        note=f"Copied revision {revision.number}.",
    )
    return service.detail(session, principal, obj.id)


@router.post("/items/{object_id}/archive", response_model=ExperimentItem)
def archive(
    object_id: str,
    request: ExperimentArchive,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    return service.archive(
        session, principal, object_id, request.expected_revision_id, request.archived
    )


@router.post("/items/{object_id}/restore", response_model=ExperimentSaved)
def restore(
    object_id: str,
    request: ExperimentRestore,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
    container: ApplicationContainer = ContainerDep,
):
    revision = service.get_revision(session, principal, request.revision_id)
    if revision.experiment_id != object_id:
        raise access.unavailable()
    obj, changed = service.save(
        session,
        principal,
        container.settings,
        service.DOCUMENT.validate_python(revision.document),
        object_id=object_id,
        expected=request.expected_revision_id,
        note=f"Restored revision {revision.number} as a new revision.",
    )
    return ExperimentSaved(
        detail=service.detail(session, principal, obj.id), changed=changed
    )


@router.get("/compare", response_model=ExperimentCompare)
def compare(
    before: str,
    after: str,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    left, right = [
        service.get_revision(session, principal, rev) for rev in (before, after)
    ]
    if left.experiment_id != right.experiment_id:
        raise access.unavailable()
    return ExperimentCompare(differences=differences(left.document, right.document))
