"""Database-backed library object endpoints.

These routes intentionally stop at object lifecycle management. Simulation
submission from released library selections lives in ``app.api.v1.runs`` so
library CRUD/release/fork semantics stay separate from execution concerns.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_database_session
from app.core.errors import ApiProblem
from app.database import library as service
from app.database.library import LibraryError
from app.database.models import ExecutionPreset, LoadCase, Tune
from app.schemas.library import (
    ArchiveLibraryObjectRequest,
    CreateExecutionPresetRequest,
    CreateLoadCaseRequest,
    CreateTuneRequest,
    CreateLibraryObjectRequest,
    DeprecateVersionRequest,
    ForkLibraryVersionRequest,
    ExecutionPresetListResponse,
    ExecutionPresetResponse,
    InstitutionListResponse,
    InstitutionResponse,
    LoadCaseListResponse,
    LoadCaseResponse,
    LibraryObjectDetailResponse,
    LibraryObjectListResponse,
    LibraryObjectResponse,
    LibraryResource,
    LibraryVersionResponse,
    ReleaseLibraryObjectRequest,
    TuneListResponse,
    TuneResponse,
    UpdateExecutionPresetRequest,
    UpdateLibraryDraftRequest,
    UpdateLoadCaseRequest,
    UpdateTuneRequest,
)

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/institutions", response_model=InstitutionListResponse)
def list_institutions(
    query: str | None = Query(default=None),
    session: Session = Depends(get_database_session),
) -> InstitutionListResponse:
    return InstitutionListResponse(
        items=[
            _institution_response(item) for item in service.list_institutions(session, query=query)
        ]
    )


@router.get("/tunes", response_model=TuneListResponse)
def list_tunes(
    account_id: str | None = Query(default=None),
    vehicle_assembly_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    session: Session = Depends(get_database_session),
) -> TuneListResponse:
    stmt = select(Tune)
    if account_id is not None:
        stmt = stmt.where(Tune.account_id == account_id)
    if vehicle_assembly_id is not None:
        stmt = stmt.where(Tune.vehicle_assembly_id == vehicle_assembly_id)
    if not include_deleted:
        stmt = stmt.where(Tune.deleted_at.is_(None))
    stmt = stmt.order_by(Tune.updated_at.desc(), Tune.name.asc())
    return TuneListResponse(items=[_tune_response(item) for item in session.scalars(stmt).all()])


@router.post("/tunes", response_model=TuneResponse, status_code=status.HTTP_201_CREATED)
def create_tune(
    request: CreateTuneRequest,
    session: Session = Depends(get_database_session),
) -> TuneResponse:
    tune = Tune(**request.model_dump())
    session.add(tune)
    session.flush()
    return _tune_response(tune)


@router.patch("/tunes/{tune_id}", response_model=TuneResponse)
def update_tune(
    tune_id: str,
    request: UpdateTuneRequest,
    session: Session = Depends(get_database_session),
) -> TuneResponse:
    tune = session.get(Tune, tune_id)
    if tune is None:
        raise ApiProblem(404, "tune_not_found", f"No tune exists with id {tune_id!r}.")
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(tune, key, value)
    session.flush()
    return _tune_response(tune)


@router.get("/load-cases", response_model=LoadCaseListResponse)
def list_load_cases(
    account_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    session: Session = Depends(get_database_session),
) -> LoadCaseListResponse:
    stmt = select(LoadCase)
    if account_id is not None:
        stmt = stmt.where(LoadCase.account_id == account_id)
    if not include_deleted:
        stmt = stmt.where(LoadCase.deleted_at.is_(None))
    stmt = stmt.order_by(LoadCase.updated_at.desc(), LoadCase.name.asc())
    return LoadCaseListResponse(
        items=[_load_case_response(item) for item in session.scalars(stmt).all()]
    )


@router.post("/load-cases", response_model=LoadCaseResponse, status_code=status.HTTP_201_CREATED)
def create_load_case(
    request: CreateLoadCaseRequest,
    session: Session = Depends(get_database_session),
) -> LoadCaseResponse:
    load_case = LoadCase(**request.model_dump())
    session.add(load_case)
    session.flush()
    return _load_case_response(load_case)


@router.patch("/load-cases/{load_case_id}", response_model=LoadCaseResponse)
def update_load_case(
    load_case_id: str,
    request: UpdateLoadCaseRequest,
    session: Session = Depends(get_database_session),
) -> LoadCaseResponse:
    load_case = session.get(LoadCase, load_case_id)
    if load_case is None:
        raise ApiProblem(
            404, "load_case_not_found", f"No load case exists with id {load_case_id!r}."
        )
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(load_case, key, value)
    session.flush()
    return _load_case_response(load_case)


@router.get("/execution-presets", response_model=ExecutionPresetListResponse)
def list_execution_presets(
    account_id: str | None = Query(default=None),
    include_system: bool = Query(default=True),
    session: Session = Depends(get_database_session),
) -> ExecutionPresetListResponse:
    stmt = select(ExecutionPreset)
    if account_id is not None and include_system:
        stmt = stmt.where(
            (ExecutionPreset.account_id == account_id) | (ExecutionPreset.account_id.is_(None))
        )
    elif account_id is not None:
        stmt = stmt.where(ExecutionPreset.account_id == account_id)
    elif not include_system:
        stmt = stmt.where(ExecutionPreset.account_id.is_not(None))
    stmt = stmt.order_by(
        ExecutionPreset.is_system_default.desc(), ExecutionPreset.updated_at.desc()
    )
    return ExecutionPresetListResponse(
        items=[_execution_preset_response(item) for item in session.scalars(stmt).all()]
    )


@router.post(
    "/execution-presets",
    response_model=ExecutionPresetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_execution_preset(
    request: CreateExecutionPresetRequest,
    session: Session = Depends(get_database_session),
) -> ExecutionPresetResponse:
    preset = ExecutionPreset(**request.model_dump())
    session.add(preset)
    session.flush()
    return _execution_preset_response(preset)


@router.patch("/execution-presets/{preset_id}", response_model=ExecutionPresetResponse)
def update_execution_preset(
    preset_id: str,
    request: UpdateExecutionPresetRequest,
    session: Session = Depends(get_database_session),
) -> ExecutionPresetResponse:
    preset = session.get(ExecutionPreset, preset_id)
    if preset is None:
        raise ApiProblem(
            404, "execution_preset_not_found", f"No execution preset exists with id {preset_id!r}."
        )
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(preset, key, value)
    session.flush()
    return _execution_preset_response(preset)


@router.get("/{resource}", response_model=LibraryObjectListResponse)
def list_library_objects(
    resource: LibraryResource,
    account_id: str | None = Query(default=None),
    public_only: bool = Query(default=False),
    include_archived: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    session: Session = Depends(get_database_session),
) -> LibraryObjectListResponse:
    try:
        items = service.list_objects(
            session,
            resource=resource,
            account_id=account_id,
            public_only=public_only,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )
    except LibraryError as exc:
        raise _bad_request(exc) from exc
    return LibraryObjectListResponse(items=[_object_response(resource, item) for item in items])


@router.post(
    "/{resource}",
    response_model=LibraryObjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_library_object(
    resource: LibraryResource,
    request: CreateLibraryObjectRequest,
    session: Session = Depends(get_database_session),
) -> LibraryObjectResponse:
    try:
        obj = service.create_object(session, resource=resource, data=request.model_dump())
    except LibraryError as exc:
        raise _bad_request(exc) from exc
    return _object_response(resource, obj)


@router.get("/{resource}/{object_id}", response_model=LibraryObjectDetailResponse)
def get_library_object(
    resource: LibraryResource,
    object_id: str,
    session: Session = Depends(get_database_session),
) -> LibraryObjectDetailResponse:
    try:
        obj = service.get_object(session, resource=resource, object_id=object_id)
    except LibraryError as exc:
        raise _not_found(exc) from exc
    versions = list(getattr(obj, "versions", []))
    return LibraryObjectDetailResponse(
        object=_object_response(resource, obj),
        released_version=(
            _version_response(resource, obj.released_version)
            if obj.released_version is not None
            else None
        ),
        versions=[_version_response(resource, version) for version in versions],
    )


@router.patch("/{resource}/{object_id}/draft", response_model=LibraryObjectResponse)
def update_library_draft(
    resource: LibraryResource,
    object_id: str,
    request: UpdateLibraryDraftRequest,
    session: Session = Depends(get_database_session),
) -> LibraryObjectResponse:
    data = request.model_dump(exclude_unset=True)
    try:
        obj = service.update_draft(session, resource=resource, object_id=object_id, data=data)
    except LibraryError as exc:
        raise _not_found(exc) from exc
    return _object_response(resource, obj)


@router.post("/{resource}/{object_id}/release", response_model=LibraryVersionResponse)
def release_library_object(
    resource: LibraryResource,
    object_id: str,
    request: ReleaseLibraryObjectRequest,
    session: Session = Depends(get_database_session),
) -> LibraryVersionResponse:
    try:
        version = service.release_object(
            session,
            resource=resource,
            object_id=object_id,
            release_data=request.model_dump(exclude_none=True),
        )
    except LibraryError as exc:
        raise _bad_request(exc) from exc
    return _version_response(resource, version)


@router.post("/{resource}/versions/{version_id}/fork", response_model=LibraryObjectResponse)
def fork_library_version(
    resource: LibraryResource,
    version_id: str,
    request: ForkLibraryVersionRequest,
    session: Session = Depends(get_database_session),
) -> LibraryObjectResponse:
    try:
        obj = service.fork_version(
            session,
            resource=resource,
            version_id=version_id,
            data=request.model_dump(exclude_none=True),
        )
    except LibraryError as exc:
        raise _bad_request(exc) from exc
    return _object_response(resource, obj)


@router.post("/{resource}/{object_id}/archive", response_model=LibraryObjectResponse)
def archive_library_object(
    resource: LibraryResource,
    object_id: str,
    request: ArchiveLibraryObjectRequest | None = Body(default=None),
    session: Session = Depends(get_database_session),
) -> LibraryObjectResponse:
    lifecycle_status = request.lifecycle_status if request is not None else "archived"
    try:
        obj = service.archive_object(
            session,
            resource=resource,
            object_id=object_id,
            lifecycle_status=lifecycle_status,
        )
    except LibraryError as exc:
        raise _bad_request(exc) from exc
    return _object_response(resource, obj)


@router.get("/{resource}/versions/{version_id}", response_model=LibraryVersionResponse)
def get_library_version(
    resource: LibraryResource,
    version_id: str,
    session: Session = Depends(get_database_session),
) -> LibraryVersionResponse:
    try:
        version = service.get_version(session, resource=resource, version_id=version_id)
    except LibraryError as exc:
        raise _not_found(exc) from exc
    return _version_response(resource, version)


@router.post("/{resource}/versions/{version_id}/deprecate", response_model=LibraryVersionResponse)
def deprecate_library_version(
    resource: LibraryResource,
    version_id: str,
    request: DeprecateVersionRequest,
    session: Session = Depends(get_database_session),
) -> LibraryVersionResponse:
    try:
        version = service.deprecate_version(
            session,
            resource=resource,
            version_id=version_id,
            validation_status=request.validation_status,
            superseded_by_version_id=request.superseded_by_version_id,
            message=request.message,
        )
    except LibraryError as exc:
        raise _bad_request(exc) from exc
    return _version_response(resource, version)


def _object_response(resource: str, obj: Any) -> LibraryObjectResponse:
    return LibraryObjectResponse(
        id=obj.id,
        resource=resource,
        account_id=obj.account_id,
        name=obj.name,
        slug=obj.slug,
        description=obj.description,
        visibility=obj.visibility,
        gallery_listed=obj.gallery_listed,
        lifecycle_status=obj.lifecycle_status,
        catalog_status=obj.catalog_status,
        catalog_priority=obj.catalog_priority,
        is_default=obj.is_default,
        source_label=obj.source_label,
        source_url=obj.source_url,
        source_notes=obj.source_notes,
        draft_payload=obj.draft_payload,
        draft_updated_at=obj.draft_updated_at,
        released_version_id=obj.released_version_id,
        forked_from_version_id=obj.forked_from_version_id,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        deleted_at=obj.deleted_at,
    )


def _version_response(resource: str, version: Any) -> LibraryVersionResponse:
    binding = service.binding_for(resource)
    payload = getattr(version, binding.payload_attr)
    aliases: dict[str, Any] = {}
    if resource == "engines":
        aliases["input_boundary"] = payload
    elif resource == "cvt-designs":
        aliases["cinder_assembly"] = payload
    elif resource == "output-systems":
        aliases["output_boundary_template"] = payload
    elif resource == "vehicle-assemblies":
        aliases["assembly_payload"] = getattr(version, "assembly_payload", payload)

    return LibraryVersionResponse(
        id=version.id,
        resource=resource,
        object_id=getattr(version, binding.object_fk_name),
        version_number=version.version_number,
        payload=payload,
        **aliases,
        tuning_schema=getattr(version, "tuning_schema", None),
        summary=version.summary,
        payload_hash=version.payload_hash,
        schema_version=version.schema_version,
        payload_schema_name=version.payload_schema_name,
        payload_schema_version=version.payload_schema_version,
        validation_status=version.validation_status,
        validation_messages=version.validation_messages,
        created_by_user_id=version.created_by_user_id,
        created_at=version.created_at,
        release_notes=version.release_notes,
        visibility_at_release=version.visibility_at_release,
        attribution_institution_id=version.attribution_institution_id,
        attribution_label=version.attribution_label,
        superseded_by_version_id=version.superseded_by_version_id,
        deprecated_at=version.deprecated_at,
        engine_version_id=getattr(version, "engine_version_id", None),
        cvt_design_version_id=getattr(version, "cvt_design_version_id", None),
        output_system_version_id=getattr(version, "output_system_version_id", None),
    )


def _institution_response(institution: Any) -> InstitutionResponse:
    return InstitutionResponse(
        id=institution.id,
        name=institution.name,
        slug=institution.slug,
        institution_type=institution.institution_type,
        country_code=institution.country_code,
        region=institution.region,
        website_url=institution.website_url,
        email_domains=list(institution.email_domains),
        aliases=list(institution.aliases),
        is_verified=institution.is_verified,
    )


def _tune_response(tune: Tune) -> TuneResponse:
    return TuneResponse(
        id=tune.id,
        account_id=tune.account_id,
        vehicle_assembly_id=tune.vehicle_assembly_id,
        cvt_design_id=tune.cvt_design_id,
        name=tune.name,
        values=tune.values,
        notes=tune.notes,
        created_at=tune.created_at,
        updated_at=tune.updated_at,
        deleted_at=tune.deleted_at,
    )


def _load_case_response(load_case: LoadCase) -> LoadCaseResponse:
    return LoadCaseResponse(
        id=load_case.id,
        account_id=load_case.account_id,
        name=load_case.name,
        kind=load_case.kind,
        visibility=load_case.visibility,
        payload=load_case.payload,
        created_at=load_case.created_at,
        updated_at=load_case.updated_at,
        deleted_at=load_case.deleted_at,
    )


def _execution_preset_response(preset: ExecutionPreset) -> ExecutionPresetResponse:
    return ExecutionPresetResponse(
        id=preset.id,
        account_id=preset.account_id,
        name=preset.name,
        kind=preset.kind,
        payload=preset.payload,
        is_system_default=preset.is_system_default,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


def _bad_request(exc: Exception) -> ApiProblem:
    return ApiProblem(400, "library_request_invalid", str(exc))


def _not_found(exc: Exception) -> ApiProblem:
    return ApiProblem(404, "library_object_not_found", str(exc))
