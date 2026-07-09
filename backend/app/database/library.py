"""Repository/service helpers for database-backed library objects.

The public API has separate resource names (engines, CVT designs, output
systems, vehicle assemblies), but their lifecycle is intentionally uniform:
mutable object with draft payload, immutable released versions, optional fork
source, catalog metadata, and stale/deprecated metadata on versions.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.database.hashing import canonical_json_hash
from app.database.models import (
    CVTDesign,
    CVTDesignVersion,
    Engine,
    EngineVersion,
    Institution,
    OutputSystem,
    OutputSystemVersion,
    VehicleAssembly,
    VehicleAssemblyVersion,
)

JsonDict = dict[str, Any]
ResourceName = Literal["engines", "cvt-designs", "output-systems", "vehicle-assemblies"]


@dataclass(frozen=True, slots=True)
class ResourceBinding:
    name: ResourceName
    object_model: type
    version_model: type
    object_fk_name: str
    object_relationship_name: str
    payload_attr: str
    default_payload_schema_name: str


RESOURCE_BINDINGS: dict[str, ResourceBinding] = {
    "engines": ResourceBinding(
        name="engines",
        object_model=Engine,
        version_model=EngineVersion,
        object_fk_name="engine_id",
        object_relationship_name="engine",
        payload_attr="input_boundary",
        default_payload_schema_name="cinder.input_boundary",
    ),
    "cvt-designs": ResourceBinding(
        name="cvt-designs",
        object_model=CVTDesign,
        version_model=CVTDesignVersion,
        object_fk_name="cvt_design_id",
        object_relationship_name="cvt_design",
        payload_attr="cinder_assembly",
        default_payload_schema_name="cinder.cvt_assembly",
    ),
    "output-systems": ResourceBinding(
        name="output-systems",
        object_model=OutputSystem,
        version_model=OutputSystemVersion,
        object_fk_name="output_system_id",
        object_relationship_name="output_system",
        payload_attr="output_boundary_template",
        default_payload_schema_name="cinder.output_boundary",
    ),
    "vehicle-assemblies": ResourceBinding(
        name="vehicle-assemblies",
        object_model=VehicleAssembly,
        version_model=VehicleAssemblyVersion,
        object_fk_name="vehicle_assembly_id",
        object_relationship_name="vehicle_assembly",
        payload_attr="assembly_payload",
        default_payload_schema_name="cvt_simulator.vehicle_assembly",
    ),
}


class LibraryError(ValueError):
    """Raised when a library operation cannot be completed."""


def binding_for(resource: str) -> ResourceBinding:
    try:
        return RESOURCE_BINDINGS[resource]
    except KeyError as exc:
        raise LibraryError(f"Unknown library resource {resource!r}.") from exc


def list_objects(
    session: Session,
    *,
    resource: str,
    account_id: str | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    public_only: bool = False,
) -> list[Any]:
    binding = binding_for(resource)
    model = binding.object_model
    stmt = select(model)
    if account_id is not None:
        stmt = stmt.where(model.account_id == account_id)
    if public_only:
        stmt = stmt.where(model.visibility == "public")
    if not include_archived:
        stmt = stmt.where(model.lifecycle_status != "archived")
    if not include_deleted:
        stmt = stmt.where(model.deleted_at.is_(None))
    stmt = stmt.order_by(
        model.is_default.desc(),
        model.catalog_priority.desc(),
        model.updated_at.desc(),
        model.name.asc(),
    )
    return list(session.scalars(stmt).all())


def get_object(session: Session, *, resource: str, object_id: str) -> Any:
    binding = binding_for(resource)
    obj = session.get(binding.object_model, object_id)
    if obj is None:
        raise LibraryError(f"Unknown {resource} object {object_id!r}.")
    return obj


def get_version(session: Session, *, resource: str, version_id: str) -> Any:
    binding = binding_for(resource)
    version = session.get(binding.version_model, version_id)
    if version is None:
        raise LibraryError(f"Unknown {resource} version {version_id!r}.")
    return version


def create_object(session: Session, *, resource: str, data: JsonDict) -> Any:
    binding = binding_for(resource)
    obj = binding.object_model(**data)
    session.add(obj)
    session.flush()
    return obj


def update_draft(session: Session, *, resource: str, object_id: str, data: JsonDict) -> Any:
    """Update mutable object metadata and draft payload.

    ``data`` is expected to come from a request body dumped with
    ``exclude_unset=True``. That means a missing key means "leave unchanged",
    while an explicitly supplied JSON null means "clear this field". Preserve
    that distinction here; do not skip ``None`` values.
    """

    obj = get_object(session, resource=resource, object_id=object_id)
    for key, value in data.items():
        if hasattr(obj, key):
            setattr(obj, key, copy.deepcopy(value))
    if "draft_payload" in data:
        obj.draft_updated_at = utc_now()
    session.flush()
    return obj


def release_object(
    session: Session,
    *,
    resource: str,
    object_id: str,
    release_data: JsonDict,
) -> Any:
    binding = binding_for(resource)
    obj = get_object(session, resource=resource, object_id=object_id)

    if resource == "vehicle-assemblies":
        version = _release_vehicle_assembly(session, binding=binding, obj=obj, data=release_data)
    else:
        payload, normalized_release_data = _payload_release_body(
            resource=resource,
            obj=obj,
            release_data=release_data,
        )
        version = _release_payload_object(
            session,
            binding=binding,
            obj=obj,
            payload=payload,
            data=normalized_release_data,
        )

    obj.released_version_id = version.id
    obj.visibility = release_data.get("visibility_at_release") or obj.visibility
    session.flush()
    return version


def fork_version(
    session: Session,
    *,
    resource: str,
    version_id: str,
    data: JsonDict,
) -> Any:
    binding = binding_for(resource)
    source = get_version(session, resource=resource, version_id=version_id)
    payload = _version_payload(binding, source)
    if resource == "cvt-designs":
        payload = {
            "cinder_assembly": payload,
            "tuning_schema": copy.deepcopy(getattr(source, "tuning_schema", {})),
        }
    elif resource == "vehicle-assemblies":
        payload = {
            "engine_version_id": source.engine_version_id,
            "cvt_design_version_id": source.cvt_design_version_id,
            "output_system_version_id": source.output_system_version_id,
            "assembly_payload": copy.deepcopy(source.assembly_payload),
        }

    obj = binding.object_model(
        account_id=data["account_id"],
        name=data.get("name")
        or f"Fork of {getattr(source, binding.object_relationship_name).name}",
        slug=data.get("slug"),
        description=data.get("description"),
        visibility=data.get("visibility", "private"),
        gallery_listed=False,
        lifecycle_status="active",
        catalog_status="user_created",
        catalog_priority=0,
        is_default=False,
        draft_payload=payload,
        draft_updated_at=utc_now(),
        forked_from_version_id=source.id,
    )
    session.add(obj)
    session.flush()
    return obj


def archive_object(
    session: Session, *, resource: str, object_id: str, lifecycle_status: str
) -> Any:
    if lifecycle_status not in {"active", "deprecated", "archived"}:
        raise LibraryError(f"Unsupported lifecycle_status {lifecycle_status!r}.")
    obj = get_object(session, resource=resource, object_id=object_id)
    obj.lifecycle_status = lifecycle_status
    session.flush()
    return obj


def deprecate_version(
    session: Session,
    *,
    resource: str,
    version_id: str,
    validation_status: str,
    superseded_by_version_id: str | None,
    message: str | None,
) -> Any:
    if validation_status not in {
        "deprecated",
        "needs_migration",
        "unsupported",
        "invalid",
        "valid",
    }:
        raise LibraryError(f"Unsupported validation_status {validation_status!r}.")
    version = get_version(session, resource=resource, version_id=version_id)
    version.validation_status = validation_status
    version.superseded_by_version_id = superseded_by_version_id
    if validation_status in {"deprecated", "needs_migration", "unsupported", "invalid"}:
        version.deprecated_at = utc_now()
    if message:
        messages = list(version.validation_messages or [])
        messages.append({"message": message, "at": utc_now().isoformat()})
        version.validation_messages = messages
    session.flush()
    return version


def list_institutions(session: Session, *, query: str | None = None) -> list[Institution]:
    stmt = select(Institution)
    if query:
        pattern = f"%{query.lower()}%"
        stmt = stmt.where(Institution.name.ilike(pattern) | Institution.slug.ilike(pattern))
    stmt = stmt.order_by(Institution.name.asc())
    return list(session.scalars(stmt).all())


def _payload_release_body(
    *,
    resource: str,
    obj: Any,
    release_data: JsonDict,
) -> tuple[JsonDict, JsonDict]:
    """Return the released model payload and normalized release metadata.

    Most resources store their draft directly as the version payload. CVT
    designs are the exception: their editable draft may bundle both the CINDER
    assembly body and the tuning schema so a forked CVT can be released without
    the client reconstructing those two fields manually.
    """

    data = copy.deepcopy(release_data)
    explicit_payload = copy.deepcopy(data.get("payload"))
    draft = copy.deepcopy(obj.draft_payload)

    if resource == "cvt-designs":
        if explicit_payload is not None:
            payload = explicit_payload
        elif isinstance(draft, dict) and "cinder_assembly" in draft:
            payload = copy.deepcopy(draft["cinder_assembly"])
            data.setdefault("tuning_schema", copy.deepcopy(draft.get("tuning_schema") or {}))
        else:
            payload = draft
    else:
        payload = explicit_payload if explicit_payload is not None else draft

    if payload is None:
        raise LibraryError(f"Cannot release {resource} object without a payload.")
    if not isinstance(payload, dict):
        raise LibraryError(f"Released {resource} payload must be a JSON object.")
    return payload, data


def _release_payload_object(
    session: Session,
    *,
    binding: ResourceBinding,
    obj: Any,
    payload: JsonDict,
    data: JsonDict,
) -> Any:
    version_number = _next_version_number(session, binding=binding, object_id=obj.id)
    kwargs: JsonDict = {
        binding.object_fk_name: obj.id,
        "version_number": version_number,
        binding.payload_attr: payload,
        "summary": copy.deepcopy(data.get("summary") or {}),
        "payload_hash": canonical_json_hash(payload),
        "schema_version": 1,
        "payload_schema_name": data.get("payload_schema_name")
        or binding.default_payload_schema_name,
        "payload_schema_version": data.get("payload_schema_version", 1),
        "validation_status": data.get("validation_status", "valid"),
        "validation_messages": copy.deepcopy(data.get("validation_messages") or []),
        "created_by_user_id": data.get("created_by_user_id"),
        "release_notes": data.get("release_notes"),
        "visibility_at_release": data.get("visibility_at_release") or obj.visibility,
        "attribution_institution_id": data.get("attribution_institution_id"),
        "attribution_label": data.get("attribution_label"),
    }
    if binding.name == "cvt-designs":
        kwargs["tuning_schema"] = copy.deepcopy(data.get("tuning_schema") or {})
    version = binding.version_model(**kwargs)
    session.add(version)
    session.flush()
    return version


def _release_vehicle_assembly(
    session: Session,
    *,
    binding: ResourceBinding,
    obj: Any,
    data: JsonDict,
) -> Any:
    draft = copy.deepcopy(obj.draft_payload or {})
    engine_version_id = data.get("engine_version_id") or draft.get("engine_version_id")
    cvt_design_version_id = data.get("cvt_design_version_id") or draft.get("cvt_design_version_id")
    output_system_version_id = data.get("output_system_version_id") or draft.get(
        "output_system_version_id"
    )
    if not engine_version_id or not cvt_design_version_id or not output_system_version_id:
        raise LibraryError(
            "Vehicle assembly releases require engine_version_id, "
            "cvt_design_version_id, and output_system_version_id."
        )
    assembly_payload = copy.deepcopy(data.get("assembly_payload"))
    if assembly_payload is None:
        assembly_payload = copy.deepcopy(draft.get("assembly_payload") or data.get("payload") or {})

    payload_for_hash = {
        "engine_version_id": engine_version_id,
        "cvt_design_version_id": cvt_design_version_id,
        "output_system_version_id": output_system_version_id,
        "assembly_payload": assembly_payload,
    }
    version = VehicleAssemblyVersion(
        vehicle_assembly_id=obj.id,
        version_number=_next_version_number(session, binding=binding, object_id=obj.id),
        engine_version_id=engine_version_id,
        cvt_design_version_id=cvt_design_version_id,
        output_system_version_id=output_system_version_id,
        assembly_payload=assembly_payload,
        summary=copy.deepcopy(data.get("summary") or {}),
        payload_hash=canonical_json_hash(payload_for_hash),
        schema_version=1,
        payload_schema_name=data.get("payload_schema_name") or binding.default_payload_schema_name,
        payload_schema_version=data.get("payload_schema_version", 1),
        validation_status=data.get("validation_status", "valid"),
        validation_messages=copy.deepcopy(data.get("validation_messages") or []),
        created_by_user_id=data.get("created_by_user_id"),
        release_notes=data.get("release_notes"),
        visibility_at_release=data.get("visibility_at_release") or obj.visibility,
        attribution_institution_id=data.get("attribution_institution_id"),
        attribution_label=data.get("attribution_label"),
    )
    session.add(version)
    session.flush()
    return version


def _next_version_number(session: Session, *, binding: ResourceBinding, object_id: str) -> int:
    fk_column = getattr(binding.version_model, binding.object_fk_name)
    stmt = select(binding.version_model).where(fk_column == object_id)
    existing = list(session.scalars(stmt).all())
    return max((version.version_number for version in existing), default=0) + 1


def _version_payload(binding: ResourceBinding, version: Any) -> JsonDict:
    return copy.deepcopy(cast(JsonDict, getattr(version, binding.payload_attr)))
