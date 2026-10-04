"""Publishing explicitly shares one sanitized, self-contained configuration.

The source and dependencies remain private. A publication stores fixed values,
not an access grant to their mutable objects or other revisions.
"""

from copy import deepcopy

from sqlalchemy import func, or_, select, update

from app.application import access, configuration_copies
from app.application import physical_library as physical
from app.application.auth import aware
from app.application.physical_contracts import validate_physical
from app.core.errors import ApiProblem
from app.database.hashing import canonical_json_hash
from app.database.models import CVTDesignVersion
from app.database.publication_models import ConfigurationCopy, PhysicalPublication
from app.schemas.physical_library import CvtDocument, SetupDocument
from app.schemas.publications import (
    ManagedPublication,
    PublicationDetail,
    PublicationItem,
    PublicationPage,
    PublicationPreview,
)


def _bundle(session, principal, kind, revision_id):
    document = physical.document_for_revision(session, principal, kind, revision_id)
    revision = physical._revision(session, principal, kind, revision_id)
    dependencies = []
    choices = (
        [("belts", document.data.belt)]
        if kind == "cvts"
        else [
            ("engines", document.data.engine),
            ("cvts", document.data.cvt),
            ("belts", document.data.cvt.data.belt),
        ]
    )
    cvt_revision = (
        revision
        if kind == "cvts"
        else session.get(CVTDesignVersion, revision.cvt_design_version_id)
    )
    for component_kind, choice in choices:
        source = (
            physical._revision(session, principal, component_kind, choice.revision_id)
            if choice.revision_id
            else None
        )
        parent = physical._parent(session, component_kind, source) if source else None
        dependencies.append(
            {
                "kind": component_kind,
                "name": choice.name,
                "revision_number": source.version_number if source else None,
                "owned": parent is not None
                and parent.account_id == principal.account_id,
            }
        )
        choice.revision_id = None
        choice.source_notes = ""
    document.source_notes = ""
    tuning = deepcopy(cvt_revision.tuning_schema)
    payload = document.model_dump(mode="json")
    fingerprint = canonical_json_hash(
        {"document": payload, "dependencies": dependencies, "tuning_schema": tuning}
    )
    return document, revision, dependencies, tuning, fingerprint


def preview(session, principal, kind, object_id):
    obj = access.library_object(
        session, principal, physical.RESOURCES[kind], object_id, write=True
    )
    if obj.lifecycle_status == "archived":
        raise ApiProblem(
            409, "archived_publication", "Unarchive this item before publishing."
        )
    document, revision, dependencies, _, fingerprint = _bundle(
        session, principal, kind, obj.released_version_id
    )
    validation, _ = validate_physical(document)
    return PublicationPreview(
        source_revision_id=revision.id,
        source_revision_number=revision.version_number,
        document=document,
        dependencies=dependencies,
        snapshot_hash=fingerprint,
        validation=validation,
    )


def publish(session, principal, kind, object_id, request):
    # Lock and compare the root, just like Save. Nested revisions are immutable.
    obj = physical._lock_current(
        session, principal, kind, object_id, request.expected_revision_id
    )
    if obj.lifecycle_status == "archived":
        raise ApiProblem(
            409, "archived_publication", "Unarchive this item before publishing."
        )
    if request.gallery_listed and request.visibility != "public":
        raise ApiProblem(
            422,
            "publication_listing",
            "Only public publications can be listed in the gallery.",
        )
    document, revision, dependencies, tuning, fingerprint = _bundle(
        session, principal, kind, obj.released_version_id
    )
    if fingerprint != request.snapshot_hash:
        raise ApiProblem(
            409,
            "publication_preview_changed",
            "Review the current publication preview before sharing it.",
        )
    existing = session.scalar(
        select(PhysicalPublication).where(
            PhysicalPublication.kind == kind,
            PhysicalPublication.source_revision_id == revision.id,
        )
    )
    if existing:
        return managed(existing)
    validation, _ = validate_physical(document)
    if not validation["is_valid"]:
        raise ApiProblem(
            422,
            "publication_invalid",
            "Fix this configuration's input errors before publishing.",
            validation,
        )
    number = (
        session.scalar(
            select(func.count())
            .select_from(PhysicalPublication)
            .where(
                PhysicalPublication.kind == kind,
                PhysicalPublication.source_object_id == object_id,
            )
        )
        + 1
    )
    row = PhysicalPublication(
        account_id=principal.account_id,
        kind=kind,
        source_object_id=object_id,
        source_revision_id=revision.id,
        revision_number=revision.version_number,
        publication_number=number,
        name=document.name,
        description=document.description,
        author=principal.user.display_name or "CINDER member",
        source_label=document.source_label,
        source_url=document.source_url,
        document=document.model_dump(mode="json"),
        dependencies=dependencies,
        tuning_schema=tuning,
        validation=validation,
        snapshot_hash=fingerprint,
        visibility=request.visibility,
        gallery_listed=request.gallery_listed,
    )
    session.add(row)
    session.flush()
    return managed(row)


def item(row):
    document = physical.DOCUMENTS[row.kind].model_validate(row.document)
    cvt = document.data if isinstance(document, CvtDocument) else document.data.cvt.data
    properties = [
        {
            "key": "belt_length",
            "label": "Belt outer length",
            "value": cvt.belt.data.outer_length_m,
            "unit": "m",
        },
        {
            "key": "belt_density",
            "label": "Belt density",
            "value": cvt.belt.data.density_kg_per_m3,
            "unit": "kg/m³",
        },
    ]
    if isinstance(document, SetupDocument):
        properties[:0] = [
            {
                "key": "vehicle_mass",
                "label": "Vehicle mass",
                "value": document.data.vehicle.mass_kg,
                "unit": "kg",
            },
            {
                "key": "reduction",
                "label": "Final-drive reduction",
                "value": document.data.vehicle.reduction_ratio,
                "unit": "",
            },
        ]
    return PublicationItem(
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "kind",
                "name",
                "description",
                "author",
                "source_label",
                "source_url",
                "revision_number",
                "publication_number",
                "visibility",
                "gallery_listed",
                "sample",
            )
        },
        published_at=aware(row.published_at),
        properties=properties,
    )


def managed(row):
    return ManagedPublication(item=item(row), access_version=row.access_version)


def readable(session, publication_id):
    row = session.get(PhysicalPublication, publication_id)
    if row is None or row.visibility not in {"public", "unlisted"}:
        raise access.unavailable()
    return row


def browse(session, *, kind=None, query="", limit=24, offset=0):
    model = PhysicalPublication
    conditions = [model.visibility == "public", model.gallery_listed.is_(True)]
    if kind:
        conditions.append(model.kind == kind)
    if query.strip():
        escaped = (
            query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        conditions.append(
            or_(
                *[
                    column.ilike(f"%{escaped}%", escape="\\")
                    for column in (
                        model.name,
                        model.description,
                        model.author,
                        model.source_label,
                    )
                ]
            )
        )
    total = session.scalar(select(func.count()).select_from(model).where(*conditions))
    rows = session.scalars(
        select(model)
        .where(*conditions)
        .order_by(model.published_at.desc(), model.id)
        .offset(offset)
        .limit(limit)
    )
    return PublicationPage(
        items=[item(row) for row in rows], total=total, offset=offset, limit=limit
    )


def detail(session, publication_id):
    row = readable(session, publication_id)
    # An unlisted sibling is accessible by its own link only, never discoverable
    # from another publication or a gallery query.
    history = session.scalars(
        select(PhysicalPublication)
        .where(
            PhysicalPublication.kind == row.kind,
            PhysicalPublication.source_object_id == row.source_object_id,
            PhysicalPublication.visibility == "public",
            PhysicalPublication.gallery_listed.is_(True),
        )
        .order_by(PhysicalPublication.publication_number.desc())
    )
    return PublicationDetail(
        item=item(row),
        document=row.document,
        dependencies=row.dependencies,
        snapshot_hash=row.snapshot_hash,
        validation=row.validation,
        history=[item(other) for other in history],
    )


def set_access(session, principal, publication_id, request):
    row = access.owned(
        session.get(PhysicalPublication, publication_id), principal, write=True
    )
    if request.gallery_listed and request.visibility != "public":
        raise ApiProblem(
            422,
            "publication_listing",
            "Only public publications can be listed in the gallery.",
        )
    if not session.execute(
        update(PhysicalPublication)
        .where(
            PhysicalPublication.id == row.id,
            PhysicalPublication.access_version == request.expected_access_version,
        )
        .values(
            visibility=request.visibility,
            gallery_listed=request.gallery_listed,
            access_version=row.access_version + 1,
        )
        .execution_options(synchronize_session=False)
    ).rowcount:
        raise ApiProblem(
            409,
            "publication_conflict",
            "Publication access changed in another tab. Reload before changing it.",
        )
    session.refresh(row)
    return managed(row)


def copy_publication(session, principal, publication_id, request):
    existing, fingerprint = configuration_copies.begin_copy(
        session, principal, request, {"publication": publication_id}
    )
    if existing:
        return configuration_copies.copy_result(session, principal, existing)
    row = readable(session, publication_id)
    document = physical.DOCUMENTS[row.kind].model_validate(row.document)
    document.name = request.name or f"{document.name[:230]} (copy)"
    obj, _ = physical.save_document(
        session,
        principal,
        document,
        duplicate=True,
        tuning_schema=row.tuning_schema,
        note=f"Copied publication {row.id} by {row.author}.",
    )
    record = ConfigurationCopy(
        account_id=principal.account_id,
        request_key=request.request_key,
        request_hash=fingerprint,
        kind=row.kind,
        object_id=obj.id,
        publication_id=row.id,
    )
    session.add(record)
    session.flush()
    return configuration_copies.copy_result(session, principal, record)
