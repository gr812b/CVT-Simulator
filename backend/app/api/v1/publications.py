"""Public snapshot reads; session/CSRF protected publishing and copying."""

from app.api.v1.dependencies import get_current_principal, get_database_session
from app.application import access, physical_library
from app.application import publications as service
from app.application.auth import Principal, aware
from app.application.physical_contracts import cvt_fields
from app.database.publication_models import ConfigurationCopy, PhysicalPublication
from app.schemas.physical_library import PhysicalKind, PhysicalMetadataResponse
from app.schemas.publications import (
    ManagedPublications,
    PublicationComparison,
    PublicationDetail,
    PublicationKind,
    PublicationPage,
)
from app.schemas.results import ConfigurationCopyResult, CopyConfiguration, CopyOrigin
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/publications", tags=["public library"])
SessionDep = Depends(get_database_session)
PrincipalDep = Depends(get_current_principal)


@router.get("/metadata", response_model=PhysicalMetadataResponse)
def metadata():
    return PhysicalMetadataResponse(cvt_fields=cvt_fields())


@router.get("", response_model=PublicationPage)
def browse(
    kind: PublicationKind | None = None,
    q: str = Query(default="", max_length=240),
    limit: int = Query(default=24, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session: Session = SessionDep,
):
    return service.browse(session, kind=kind, query=q, limit=limit, offset=offset)


@router.get("/manage/{kind}/{object_id}", response_model=ManagedPublications)
def manage(
    kind: PublicationKind,
    object_id: str,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    access.library_object(
        session, principal, physical_library.RESOURCES[kind], object_id, write=True
    )
    rows = session.scalars(
        select(PhysicalPublication)
        .where(
            PhysicalPublication.kind == kind,
            PhysicalPublication.source_object_id == object_id,
            PhysicalPublication.account_id == principal.account_id,
        )
        .order_by(PhysicalPublication.publication_number.desc())
    )
    return ManagedPublications(items=[service.managed(row) for row in rows])


@router.get("/origin/{kind}/{object_id}", response_model=CopyOrigin | None)
def origin(
    kind: PhysicalKind,
    object_id: str,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    obj = access.library_object(session, principal, physical_library.RESOURCES[kind], object_id)
    access.owned(obj, principal)
    row = session.scalar(
        select(ConfigurationCopy).where(
            ConfigurationCopy.account_id == principal.account_id,
            ConfigurationCopy.object_id == object_id,
            ConfigurationCopy.kind == kind,
        )
    )
    return (
        CopyOrigin(
            publication_id=row.publication_id,
            run_id=row.run_id,
            copied_at=aware(row.copied_at),
        )
        if row
        else None
    )


@router.get("/compare", response_model=PublicationComparison)
def compare(before: str, after: str, session: Session = SessionDep):
    left, right = service.readable(session, before), service.readable(session, after)
    if left.kind != right.kind or left.source_object_id != right.source_object_id:
        raise access.unavailable()
    return PublicationComparison(
        before=service.item(left),
        after=service.item(right),
        differences=physical_library.differences(left.document, right.document),
    )


@router.get("/{publication_id}", response_model=PublicationDetail)
def detail(publication_id: str, session: Session = SessionDep):
    return service.detail(session, publication_id)


@router.post("/{publication_id}/copy", response_model=ConfigurationCopyResult, status_code=201)
def copy(
    publication_id: str,
    request: CopyConfiguration,
    session: Session = SessionDep,
    principal: Principal = PrincipalDep,
):
    return service.copy_publication(session, principal, publication_id, request)
