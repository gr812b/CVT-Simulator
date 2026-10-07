"""Transactional physical-library saves over the existing immutable version tables.

A setup save commits changed owned components and its selected revisions together.
Unchanged references stay pinned. Editing someone else's component creates a
public copy; it never writes through to that person's object.
"""

import copy
import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.application import access
from app.application.auth import Principal, aware
from app.application.physical_contracts import (
    baseline_case,
    belt_from_assembly,
    normalize_document,
    template_document,
    validate_physical,
    vehicle_boundary,
    vehicle_from_boundary,
)
from app.core.errors import ApiProblem
from app.database import library
from app.database.base import utc_now
from app.database.hashing import canonical_json_hash
from app.database.models import OutputSystemVersion
from app.database.publication_models import PhysicalPublication
from app.database.resolver import _current_assembly_document, _current_primary_boundary
from app.database.tuning import readable_tuning_schema
from app.schemas.physical_library import (
    BeltChoice,
    BeltData,
    BeltDocument,
    ComponentUpdate,
    CvtChoice,
    CvtData,
    CvtDocument,
    EngineChoice,
    EngineData,
    EngineDocument,
    PhysicalDetail,
    PhysicalDifference,
    PhysicalDocument,
    PhysicalItem,
    PhysicalMetadata,
    PhysicalRevision,
    PhysicalSelection,
    SetupData,
    SetupDocument,
)

RESOURCES = {
    "engines": "engines",
    "belts": "belts",
    "cvts": "cvt-designs",
    "setups": "vehicle-assemblies",
}
DOCUMENTS = {
    "engines": EngineDocument,
    "belts": BeltDocument,
    "cvts": CvtDocument,
    "setups": SetupDocument,
}
CHOICES = {"engines": EngineChoice, "belts": BeltChoice, "cvts": CvtChoice}


def _metadata(document) -> dict:
    return document.model_dump(include=set(PhysicalMetadata.model_fields))


def _parent(session, kind, version):
    binding = library.binding_for(RESOURCES[kind])
    return session.get(binding.object_model, getattr(version, binding.object_fk_name))


def _revision(session, principal, kind, revision_id):
    return access.library_version(session, principal, RESOURCES[kind], revision_id)


def _version_metadata(session, principal, kind, version):
    parent = _parent(session, kind, version)
    metadata = version.summary.get("physical_metadata") or {
        field: getattr(parent, field, None) or "" for field in PhysicalMetadata.model_fields
    }
    metadata = copy.deepcopy(metadata)
    return metadata


def document_for_revision(
    session: Session, principal: Principal, kind: str, revision_id: str
) -> PhysicalDocument:
    version = _revision(session, principal, kind, revision_id)
    metadata = _version_metadata(session, principal, kind, version)
    if kind == "engines":
        data = EngineData.model_validate(_current_primary_boundary(version.input_boundary))
    elif kind == "belts":
        data = BeltData.model_validate(version.belt_payload)
    elif kind == "cvts":
        assembly = _current_assembly_document(version.cinder_assembly, baseline_case()["execution"])
        if version.belt_version_id:
            belt = choice_for_revision(session, principal, "belts", version.belt_version_id)
        else:
            belt = BeltChoice(
                name=f"Belt for {metadata['name']}",
                data=belt_from_assembly(assembly),
                source_label=metadata["source_label"],
            )
        data = CvtData(assembly=assembly, belt=belt)
    else:
        output = session.get(OutputSystemVersion, version.output_system_version_id)
        data = SetupData(
            engine=choice_for_revision(session, principal, "engines", version.engine_version_id),
            cvt=choice_for_revision(session, principal, "cvts", version.cvt_design_version_id),
            vehicle=vehicle_from_boundary(output.output_boundary_template),
        )
    # Read old revisions through the same adapter used on save so the handful
    # of pre-Patch-C CVTs immediately adopt groove-width travel semantics.
    return normalize_document(DOCUMENTS[kind](kind=kind, data=data, **metadata))


def choice_for_revision(session, principal, kind, revision_id):
    document = document_for_revision(session, principal, kind, revision_id)
    return CHOICES[kind](revision_id=revision_id, **document.model_dump(exclude={"kind"}))


def template_for_library(session, principal, kind):
    """New containers select the existing defaults instead of cloning hardware."""
    from app.database.physical_seed import sample_id

    document = template_document(kind)
    if kind == "setups":
        document.data.cvt = choice_for_revision(session, principal, "cvts", sample_id("cvt:r1"))
        document.data.engine = choice_for_revision(
            session, principal, "engines", sample_id("engine:r1")
        )
    elif kind == "cvts":
        document.data.belt = choice_for_revision(session, principal, "belts", sample_id("belt:r1"))
    return document


def item_response(obj, kind, principal) -> PhysicalItem:
    from sqlalchemy.orm import object_session

    from app.application.authorship import author_name, public_author_id

    version = obj.released_version
    return PhysicalItem(
        author=author_name(object_session(obj), version.created_by_user_id),
        author_id=public_author_id(object_session(obj), version.created_by_user_id),
        id=obj.id,
        kind=kind,
        name=obj.name,
        description=obj.description or "",
        source_label=obj.source_label or "",
        revision_id=version.id,
        revision_number=version.version_number,
        updated_at=aware(obj.updated_at),
        owned=obj.account_id == principal.account_id,
        archived=obj.lifecycle_status == "archived",
        sample=obj.catalog_status in ("seeded_example", "official", "admin_curated"),
        is_default=obj.is_default,
        validation_status=version.validation_status,
    )


def list_items(session, principal, kind, scope="own", include_archived=False, author_id=None):
    binding = library.binding_for(RESOURCES[kind])
    model = binding.object_model
    own = model.account_id == principal.account_id
    samples = (model.visibility == "public") & model.catalog_status.in_(
        ("seeded_example", "official", "admin_curated")
    )
    statement = select(model).where(
        model.deleted_at.is_(None), model.released_version_id.is_not(None)
    )
    statement = statement.where(
        own if scope == "own" else samples if scope == "samples" else model.visibility == "public"
    )
    if author_id is not None:
        version = binding.version_model
        statement = statement.join(version, model.released_version_id == version.id).where(
            version.created_by_user_id == author_id,
            model.visibility == "public",
        )
    if not include_archived:
        statement = statement.where(model.lifecycle_status != "archived")
    result = []
    for obj in session.scalars(
        statement.order_by(model.is_default.desc(), model.updated_at.desc(), model.id)
    ):
        try:
            _revision(session, principal, kind, obj.released_version_id)
        except ApiProblem:
            continue
        result.append(item_response(obj, kind, principal))
    return result


def _conflict():
    return ApiProblem(
        409,
        "revision_conflict",
        "This item changed in another tab. Reload its latest revision before saving; your working values have not been saved.",
    )


def _lock_current(session, principal, kind, object_id, expected):
    resource = RESOURCES.get(kind, kind)
    obj = access.library_object(session, principal, resource, object_id, write=True)
    model = type(obj)
    # A conditional UPDATE both checks the revision and takes a write lock on
    # SQLite/PostgreSQL. Child revisions and the root remain one transaction.
    result = session.execute(
        update(model)
        .where(model.id == obj.id, model.released_version_id == expected)
        .values(draft_updated_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise _conflict()
    session.refresh(obj)
    return obj


def _save_choice(session, principal, kind, choice, *, duplicate=False, tuning_schema=None):
    document = DOCUMENTS[kind](kind=kind, **choice.model_dump(exclude={"revision_id"}))
    parent = source = None
    if choice.revision_id:
        source = _revision(session, principal, kind, choice.revision_id)
        parent = _parent(session, kind, source)
        original = document_for_revision(session, principal, kind, source.id)
        # A root copy does not imply a copy of unchanged dependencies. Keep the
        # authorized, immutable revision; fork only an explicitly changed child.
        if normalize_document(original) == normalize_document(document):
            return choice
    own = parent is not None and parent.account_id == principal.account_id and not duplicate
    obj, _ = save_document(
        session,
        principal,
        document,
        object_id=parent.id if own else None,
        expected=source.id if own else None,
        note="Saved with a physical setup.",
        duplicate=duplicate,
        forked_from=source.id if source and not own else None,
        tuning_schema=tuning_schema,
    )
    return choice_for_revision(session, principal, kind, obj.released_version_id)


def _save_output(session, principal, setup_obj, vehicle, previous):
    payload = vehicle_boundary(vehicle)
    if previous:
        old = session.get(OutputSystemVersion, previous.output_system_version_id)
        if vehicle_from_boundary(old.output_boundary_template) == vehicle:
            return old.id
        parent = old.output_system
        if parent.account_id == principal.account_id:
            obj = _lock_current(session, principal, "output-systems", parent.id, old.id)
        else:
            obj = None
    else:
        obj = None
    if obj is None:
        obj = library.create_object(
            session,
            resource="output-systems",
            data={
                "account_id": principal.account_id,
                "name": f"Vehicle for {setup_obj.name}",
                "visibility": "public",
                "draft_payload": payload,
            },
        )
    version = library.release_object(
        session,
        resource="output-systems",
        object_id=obj.id,
        release_data={
            "payload": payload,
            "created_by_user_id": principal.user_id,
            "visibility_at_release": "public",
            "release_notes": "Saved with vehicle setup.",
        },
    )
    obj.draft_payload = payload
    return version.id


def save_document(
    session: Session,
    principal: Principal,
    document: PhysicalDocument,
    *,
    object_id: str | None = None,
    expected: str | None = None,
    note: str = "",
    duplicate: bool = False,
    forked_from: str | None = None,
    tuning_schema: dict | None = None,
):
    principal.require_write()
    document = normalize_document(document)
    kind, resource = document.kind, RESOURCES[document.kind]
    previous = None
    if object_id:
        obj = _lock_current(session, principal, kind, object_id, expected)
        previous = session.get(library.binding_for(resource).version_model, obj.released_version_id)
        if previous and document_for_revision(session, principal, kind, previous.id) == document:
            return obj, False
    else:
        if expected is not None:
            raise _conflict()
        obj = library.create_object(
            session,
            resource=resource,
            data={
                "account_id": principal.account_id,
                **_metadata(document),
                "visibility": "public",
                "forked_from_version_id": forked_from,
            },
        )

    if isinstance(document, CvtDocument):
        document.data.belt = _save_choice(
            session, principal, "belts", document.data.belt, duplicate=duplicate
        )
    elif isinstance(document, SetupDocument):
        document.data.engine = _save_choice(
            session, principal, "engines", document.data.engine, duplicate=duplicate
        )
        document.data.cvt = _save_choice(
            session,
            principal,
            "cvts",
            document.data.cvt,
            duplicate=duplicate,
            tuning_schema=tuning_schema,
        )
    document = normalize_document(document)
    validation, _ = validate_physical(document)
    release = {
        "created_by_user_id": principal.user_id,
        "release_notes": note or "Saved physical inputs.",
        "visibility_at_release": obj.visibility,
        "summary": {"physical_metadata": _metadata(document)},
        "validation_status": "valid" if validation["is_valid"] else "invalid",
        "validation_messages": validation["findings"],
    }
    if isinstance(document, SetupDocument):
        release.update(
            {
                "engine_version_id": document.data.engine.revision_id,
                "cvt_design_version_id": document.data.cvt.revision_id,
                "output_system_version_id": _save_output(
                    session, principal, obj, document.data.vehicle, previous
                ),
                "assembly_payload": {},
            }
        )
        obj.draft_payload = {
            key: release[key]
            for key in (
                "engine_version_id",
                "cvt_design_version_id",
                "output_system_version_id",
                "assembly_payload",
            )
        }
    elif isinstance(document, CvtDocument):
        release["payload"] = document.data.assembly
        # Preserve capabilities from an existing source; only paths supported by
        # the new hardware survive. The frontend never invents tuning abilities.
        source = previous
        if source is None and forked_from:
            source = _revision(session, principal, kind, forked_from)
        release["tuning_schema"] = readable_tuning_schema(
            document.data.assembly,
            (
                tuning_schema
                if tuning_schema is not None
                else source.tuning_schema if source else _default_tuning_schema()
            ),
        )
        obj.draft_payload = {
            "cinder_assembly": document.data.assembly,
            "tuning_schema": release["tuning_schema"],
        }
    else:
        release["payload"] = document.data.model_dump()
        obj.draft_payload = release["payload"]
    for key, value in _metadata(document).items():
        setattr(obj, key, value)
    if isinstance(document, SetupDocument):
        access.check_assembly_release(session, principal, obj, release)
    elif isinstance(document, CvtDocument):
        access.library_version(
            session,
            principal,
            "belts",
            document.data.belt.revision_id,
            shared=obj.visibility != "private",
        )
    version = library.release_object(
        session, resource=resource, object_id=obj.id, release_data=release
    )
    if isinstance(document, CvtDocument):
        version.belt_version_id = document.data.belt.revision_id
        from app.application.experiment_tuning import ensure_default_tune

        ensure_default_tune(session, version)
    version.payload_hash = canonical_json_hash(document.model_dump(mode="json"))
    obj.draft_updated_at = utc_now()
    session.flush()
    session.expire(obj, ["released_version"])
    from app.application.publications import publish_saved_revision

    publish_saved_revision(session, principal, kind, obj)
    return obj, True


def _default_tuning_schema():
    # Existing published application metadata, normalized against the current
    # canonical hardware rather than a second frontend capability list.
    from app.database.seed import _baseline_tuning_schema

    return _baseline_tuning_schema()


def available_updates(session, principal, document):
    choices = []
    if isinstance(document, SetupDocument):
        choices.extend(
            (
                ("engine", "engines", document.data.engine),
                ("cvt", "cvts", document.data.cvt),
            )
        )
        choices.append(("belt", "belts", document.data.cvt.data.belt))
    elif isinstance(document, CvtDocument):
        choices.append(("belt", "belts", document.data.belt))
    updates = []
    for component, kind, choice in choices:
        if not choice.revision_id:
            continue
        current = _revision(session, principal, kind, choice.revision_id)
        parent = _parent(session, kind, current)
        latest_id = parent.released_version_id
        if not latest_id or latest_id == current.id or parent.lifecycle_status == "archived":
            continue
        try:
            latest = _revision(session, principal, kind, latest_id)
        except ApiProblem:
            continue
        updates.append(
            ComponentUpdate(
                component=component,
                name=parent.name,
                current_revision_id=current.id,
                current_number=current.version_number,
                available_revision_id=latest.id,
                available_number=latest.version_number,
            )
        )
    return updates


def selection_for_revision(session, principal, kind, revision_id):
    """A lightweight selection with metadata from the requested saved version."""
    version = _revision(session, principal, kind, revision_id)
    document = document_for_revision(session, principal, kind, revision_id)
    item = item_response(_parent(session, kind, version), kind, principal)
    return PhysicalSelection(
        item=item.model_copy(
            update={
                "revision_id": version.id,
                "revision_number": version.version_number,
                "name": document.name,
                "description": document.description,
                "source_label": document.source_label,
                "validation_status": version.validation_status,
            }
        ),
        document=document,
    )


def detail(session, principal, kind, object_id, revision_id=None):
    obj = access.library_object(session, principal, RESOURCES[kind], object_id)
    selected = revision_id or obj.released_version_id
    if not selected:
        raise ApiProblem(
            409,
            "physical_revision_required",
            "This legacy draft has no saved revision. Save a complete physical item first.",
        )
    version = _revision(session, principal, kind, selected)
    if _parent(session, kind, version).id != obj.id:
        raise access.unavailable()
    selection = selection_for_revision(session, principal, kind, selected)
    document = selection.document
    history = []
    for item in sorted(obj.versions, key=lambda entry: entry.version_number, reverse=True):
        try:
            _revision(session, principal, kind, item.id)
        except ApiProblem:
            continue
        history.append(
            PhysicalRevision(
                id=item.id,
                number=item.version_number,
                created_at=aware(item.created_at),
                change_note=item.release_notes or "",
                name=_version_metadata(session, principal, kind, item)["name"],
                validation_status=item.validation_status,
            )
        )
    # Immutable revisions already retain their save-time validation. Reading a
    # record must not rerun the numerical preflight; review/submission validates
    # against the installed solver explicitly.
    validation = {
        "is_valid": version.validation_status == "valid",
        "findings": version.validation_messages or [],
    }
    references = []
    choices = []
    if document.kind == "setups":
        choices = [("engines", document.data.engine), ("cvts", document.data.cvt)]
    elif document.kind == "cvts":
        choices = [("belts", document.data.belt)]
    for child_kind, choice in choices:
        if choice.revision_id:
            child = _revision(session, principal, child_kind, choice.revision_id)
            references.append(
                {
                    "kind": child_kind,
                    "object_id": _parent(session, child_kind, child).id,
                    "revision_id": choice.revision_id,
                    "name": choice.name,
                }
            )
    return PhysicalDetail(
        references=references,
        item=selection.item,
        document=document,
        history=history,
        updates=available_updates(session, principal, document),
        validation=validation,
    )


def duplicate_revision(session, principal, kind, revision_id, name=None):
    document = document_for_revision(session, principal, kind, revision_id)
    document.name = name or f"{document.name} (copy)"[:240]
    if not document.source_label:
        document.source_label = f"Copy of {revision_id}"
    obj, _ = save_document(
        session,
        principal,
        document,
        duplicate=True,
        forked_from=revision_id,
        note="Copied a fixed revision into this workspace.",
    )
    return obj


def differences(before: Any, after: Any, path="") -> list[PhysicalDifference]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return [
            change
            for key in sorted(before.keys() | after.keys())
            for change in differences(before.get(key), after.get(key), f"{path}/{key}")
        ]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [
            change
            for index, (left, right) in enumerate(zip(before, after))
            for change in differences(left, right, f"{path}/{index}")
        ]

    def display(value):
        return "—" if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)

    return [PhysicalDifference(path=path, before=display(before), after=display(after))]


def update_preview(session, principal, kind, object_id, component, target_revision_id):
    current = detail(session, principal, kind, object_id)
    if not current.item.owned:
        raise access.unavailable()
    update_choice = next(
        (
            item
            for item in current.updates
            if item.component == component and item.available_revision_id == target_revision_id
        ),
        None,
    )
    if update_choice is None:
        raise ApiProblem(
            409,
            "component_update_changed",
            "This update is no longer available. Refresh the item.",
        )
    document = current.document.model_copy(deep=True)
    kind_for_component = {"engine": "engines", "cvt": "cvts", "belt": "belts"}[component]
    replacement = choice_for_revision(session, principal, kind_for_component, target_revision_id)
    if component == "engine" and isinstance(document, SetupDocument):
        document.data.engine = replacement
    elif component == "cvt" and isinstance(document, SetupDocument):
        document.data.cvt = replacement
    elif component == "belt":
        cvt = document.data.cvt.data if isinstance(document, SetupDocument) else document.data
        cvt.belt = replacement
    document = normalize_document(document)
    changes = differences(current.document.model_dump(), document.model_dump())
    return current.item.revision_id, document, changes, validate_physical(document)[0]


def archive(session, principal, kind, object_id, request):
    """Archive discovery without changing public immutable snapshot URLs."""
    obj = _lock_current(session, principal, kind, object_id, request.expected_revision_id)
    obj.lifecycle_status = "archived" if request.archived else "active"
    session.execute(
        update(PhysicalPublication)
        .where(
            PhysicalPublication.kind == kind,
            PhysicalPublication.source_object_id == obj.id,
        )
        .values(gallery_listed=False)
    )
    if not request.archived:
        session.execute(
            update(PhysicalPublication)
            .where(
                PhysicalPublication.kind == kind,
                PhysicalPublication.source_revision_id == obj.released_version_id,
            )
            .values(gallery_listed=True)
        )
    session.flush()
    return item_response(obj, kind, principal)
