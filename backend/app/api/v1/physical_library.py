"""User-facing Save, Duplicate, History, Restore and component-update workflows."""

from typing import Literal

from app.api.v1.dependencies import (
    get_current_principal,
    get_database_session,
    get_public_reader,
)
from app.application import access
from app.application import physical_library as service
from app.application.auth import Principal
from app.application.physical_contracts import (
    cvt_fields,
    import_engine_curve,
    resolve_belt_section,
    validate_physical,
)
from app.core.errors import ApiProblem
from app.schemas.physical_library import (
    BeltSection,
    BeltSectionSolveRequest,
    CurveImportRequest,
    CurveImportResponse,
    PhysicalArchiveRequest,
    PhysicalCompareResponse,
    PhysicalCopyRequest,
    PhysicalDetail,
    PhysicalItem,
    PhysicalKind,
    PhysicalListResponse,
    PhysicalMetadataResponse,
    PhysicalRestoreRequest,
    PhysicalSaveRequest,
    PhysicalSaveResponse,
    PhysicalTemplateResponse,
    PhysicalUpdatePreview,
    PhysicalValidateRequest,
    PhysicalValidationResponse,
)
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/physical-library", tags=["physical library"])


@router.get("/metadata", response_model=PhysicalMetadataResponse)
def metadata():
    return PhysicalMetadataResponse(cvt_fields=cvt_fields())


@router.get("/templates/{kind}", response_model=PhysicalTemplateResponse)
def template(
    kind: PhysicalKind,
    principal=Depends(get_public_reader),
    session: Session = Depends(get_database_session),
):
    return PhysicalTemplateResponse(document=service.template_for_library(session, principal, kind))


@router.post(
    "/engine-curve/import",
    response_model=CurveImportResponse,
    dependencies=[Depends(get_current_principal)],
)
def import_curve(request: CurveImportRequest):
    return CurveImportResponse(points=import_engine_curve(request))


@router.post(
    "/belt-section/resolve",
    response_model=BeltSection,
    dependencies=[Depends(get_current_principal)],
)
def belt_section(request: BeltSectionSolveRequest):
    return resolve_belt_section(request)


@router.post(
    "/validate",
    response_model=PhysicalValidationResponse,
    dependencies=[Depends(get_current_principal)],
)
def validate(request: PhysicalValidateRequest):
    validation, resolved = validate_physical(request.document)
    return PhysicalValidationResponse(validation=validation, resolved_simulation_case=resolved)


@router.get("/items/{kind}", response_model=PhysicalListResponse)
def list_items(
    kind: PhysicalKind,
    scope: Literal["own", "samples", "all"] = "own",
    include_archived: bool = False,
    author_id: str | None = None,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_public_reader),
):
    return PhysicalListResponse(
        items=service.list_items(session, principal, kind, scope, include_archived, author_id)
    )


@router.post("/items/{kind}", response_model=PhysicalSaveResponse, status_code=201)
def create(
    kind: PhysicalKind,
    request: PhysicalSaveRequest,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_current_principal),
):
    _check_kind(kind, request)
    obj, changed = service.save_document(
        session,
        principal,
        request.document,
        expected=request.expected_revision_id,
        note=request.change_note,
    )
    return PhysicalSaveResponse(
        detail=service.detail(session, principal, kind, obj.id), changed=changed
    )


@router.get("/items/{kind}/{object_id}", response_model=PhysicalDetail)
def get_item(
    kind: PhysicalKind,
    object_id: str,
    revision_id: str | None = None,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_public_reader),
):
    return service.detail(session, principal, kind, object_id, revision_id)


@router.put("/items/{kind}/{object_id}", response_model=PhysicalSaveResponse)
def save(
    kind: PhysicalKind,
    object_id: str,
    request: PhysicalSaveRequest,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_current_principal),
):
    _check_kind(kind, request)
    obj, changed = service.save_document(
        session,
        principal,
        request.document,
        object_id=object_id,
        expected=request.expected_revision_id,
        note=request.change_note,
    )
    return PhysicalSaveResponse(
        detail=service.detail(session, principal, kind, obj.id), changed=changed
    )


@router.post(
    "/revisions/{kind}/{revision_id}/copy",
    response_model=PhysicalDetail,
    status_code=201,
)
def copy_revision(
    kind: PhysicalKind,
    revision_id: str,
    request: PhysicalCopyRequest,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_current_principal),
):
    obj = service.duplicate_revision(session, principal, kind, revision_id, request.name)
    return service.detail(session, principal, kind, obj.id)


@router.post("/items/{kind}/{object_id}/restore", response_model=PhysicalSaveResponse)
def restore(
    kind: PhysicalKind,
    object_id: str,
    request: PhysicalRestoreRequest,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_current_principal),
):
    access.library_object(session, principal, service.RESOURCES[kind], object_id, write=True)
    old = service.detail(session, principal, kind, object_id, request.revision_id)
    obj, changed = service.save_document(
        session,
        principal,
        old.document,
        object_id=object_id,
        expected=request.expected_revision_id,
        note=f"Restored saved revision {request.revision_id}.",
    )
    return PhysicalSaveResponse(
        detail=service.detail(session, principal, kind, obj.id), changed=changed
    )


@router.get("/items/{kind}/{object_id}/compare", response_model=PhysicalCompareResponse)
def compare(
    kind: PhysicalKind,
    object_id: str,
    from_revision_id: str,
    to_revision_id: str,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_public_reader),
):
    left = service.detail(session, principal, kind, object_id, from_revision_id)
    right = service.detail(session, principal, kind, object_id, to_revision_id)
    return PhysicalCompareResponse(
        differences=service.differences(left.document.model_dump(), right.document.model_dump())
    )


@router.get("/items/{kind}/{object_id}/update-preview", response_model=PhysicalUpdatePreview)
def update_preview(
    kind: PhysicalKind,
    object_id: str,
    component: Literal["engine", "cvt", "belt"],
    revision_id: str = Query(),
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_current_principal),
):
    expected, document, changes, validation = service.update_preview(
        session, principal, kind, object_id, component, revision_id
    )
    return PhysicalUpdatePreview(
        expected_revision_id=expected,
        document=document,
        differences=changes,
        validation=validation,
    )


@router.post("/items/{kind}/{object_id}/archive", response_model=PhysicalItem)
def archive(
    kind: PhysicalKind,
    object_id: str,
    request: PhysicalArchiveRequest,
    session: Session = Depends(get_database_session),
    principal: Principal = Depends(get_current_principal),
):
    return service.archive(session, principal, kind, object_id, request)


def _check_kind(kind, request):
    if request.document.kind != kind:
        raise ApiProblem(422, "physical_kind_mismatch", "The document kind must match its library.")
