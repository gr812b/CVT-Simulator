"""Explicit ownership and dependency checks shared by HTTP entry points."""

from typing import Any

from sqlalchemy.orm import Session

from app.application.auth import Principal
from app.core.errors import ApiProblem
from app.database import library
from app.database.models import ExecutionPreset, LoadCase, Tune


def unavailable() -> ApiProblem:
    return ApiProblem(
        404, "resource_not_found", "The requested resource was not found."
    )


def owned(item: Any, principal: Principal, *, write: bool = False) -> Any:
    if (
        item is None
        or item.account_id != principal.account_id
        or getattr(item, "deleted_at", None)
    ):
        raise unavailable()
    if write:
        principal.require_write()
    return item


def library_object(
    session: Session,
    principal: Principal,
    resource: str,
    object_id: str,
    *,
    write: bool = False,
) -> Any:
    binding = library.binding_for(resource)
    item = session.get(binding.object_model, object_id)
    if write:
        return owned(item, principal, write=True)
    if item is None or item.deleted_at is not None:
        raise unavailable()
    if item.account_id != principal.account_id:
        if (
            item.visibility not in {"public", "unlisted"}
            or not item.released_version_id
        ):
            raise unavailable()
        library_version(session, principal, resource, item.released_version_id)
    return item


def version_is_shared(version: Any, parent: Any) -> bool:
    return (
        parent.deleted_at is None
        and parent.visibility in {"public", "unlisted"}
        and version.visibility_at_release in {"public", "unlisted"}
    )


def library_version(
    session: Session,
    principal: Principal,
    resource: str,
    version_id: str,
    *,
    write: bool = False,
    shared: bool = False,
) -> Any:
    binding = library.binding_for(resource)
    version = session.get(binding.version_model, version_id)
    if version is None:
        raise unavailable()
    parent = session.get(binding.object_model, getattr(version, binding.object_fk_name))
    if write:
        owned(parent, principal, write=True)
    elif parent is None or parent.deleted_at is not None:
        raise unavailable()
    elif (
        shared or parent.account_id != principal.account_id
    ) and not version_is_shared(version, parent):
        raise unavailable()
    if resource == "vehicle-assemblies":
        for key, kind in COMPONENTS:
            library_version(
                session, principal, kind, getattr(version, key), shared=shared
            )
    return version


COMPONENTS = (
    ("engine_version_id", "engines"),
    ("cvt_design_version_id", "cvt-designs"),
    ("output_system_version_id", "output-systems"),
)


def check_assembly_release(
    session: Session, principal: Principal, obj: Any, data: dict
) -> None:
    shared = (data.get("visibility_at_release") or obj.visibility) != "private"
    draft = obj.draft_payload or {}
    for key, resource in COMPONENTS:
        version_id = data.get(key) or draft.get(key)
        if not version_id:
            raise ApiProblem(422, "assembly_dependency_required", f"{key} is required.")
        library_version(session, principal, resource, version_id, shared=shared)


def run_selection(session: Session, principal: Principal, selection: Any) -> None:
    assembly = library_version(
        session, principal, "vehicle-assemblies", selection.vehicle_assembly_version_id
    )
    if selection.tune_id:
        tune = owned(session.get(Tune, selection.tune_id), principal)
        if (
            tune.vehicle_assembly_id != assembly.vehicle_assembly_id
            or tune.cvt_design_id != assembly.cvt_design_version.cvt_design_id
        ):
            raise ApiProblem(
                422,
                "tune_setup_mismatch",
                "Choose a tune belonging to this vehicle and CVT.",
            )
    if selection.load_case_id:
        load = session.get(LoadCase, selection.load_case_id)
        if load is None or load.deleted_at is not None:
            raise unavailable()
        if load.account_id != principal.account_id and load.visibility not in {
            "public",
            "unlisted",
        }:
            raise unavailable()
    if selection.execution_preset_id:
        preset = session.get(ExecutionPreset, selection.execution_preset_id)
        if preset is None or preset.account_id not in {None, principal.account_id}:
            raise unavailable()
