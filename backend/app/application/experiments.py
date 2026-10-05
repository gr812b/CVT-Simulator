"""Public, immutable experiment history and frozen input resolution."""

from copy import deepcopy

from pydantic import TypeAdapter
from sqlalchemy import select, update

from app.application import access
from app.application.auth import aware
from app.application.cinder_gateway import CinderGateway
from app.application.experiment_tuning import apply_values, setup_tuning
from app.application.input_validation import validate_assembly, validate_case
from app.application.physical_contracts import (
    baseline_case,
    vehicle_boundary,
)
from app.application.physical_library import document_for_revision
from app.application.roads import apply_scenario, default_scenario, validate_scenario
from app.core.errors import ApiProblem
from app.database.base import utc_now
from app.database.experiment_models import Experiment, ExperimentRevision
from app.database.hashing import canonical_json_hash
from app.database.models import CVTDesignVersion, VehicleAssemblyVersion
from app.schemas.experiments import (
    ExperimentDetail,
    ExperimentDocument,
    ExperimentItem,
    ExperimentPreview,
)

DOCUMENT = TypeAdapter(ExperimentDocument)


def get_item(session, principal, object_id, *, write=False):
    obj = session.get(Experiment, object_id)
    if obj is None or (write and obj.account_id != principal.account_id):
        raise access.unavailable()
    if write:
        principal.require_write()
    return obj


def get_revision(session, principal, revision_id, kind=None):
    revision = session.get(ExperimentRevision, revision_id)
    if revision is None:
        raise access.unavailable()
    obj = get_item(session, principal, revision.experiment_id)
    if kind is not None and obj.kind != kind:
        raise access.unavailable()
    return revision


def item_response(session, principal, obj, revision=None):
    revision = revision or session.get(ExperimentRevision, obj.current_revision_id)
    setup = (
        session.get(VehicleAssemblyVersion, revision.document["setup_revision_id"])
        if obj.kind == "tunes"
        else None
    )
    cvt = session.get(CVTDesignVersion, setup.cvt_design_version_id) if setup else None
    from app.application.authorship import author_name

    return ExperimentItem(
        author=author_name(session, revision.created_by_user_id),
        cvt_object_id=cvt.cvt_design_id if cvt else None,
        cvt_revision_id=cvt.id if cvt else None,
        id=obj.id,
        kind=obj.kind,
        name=revision.document["name"],
        revision_id=revision.id,
        revision_number=revision.number,
        updated_at=aware(obj.updated_at),
        owned=obj.account_id == principal.account_id,
        archived=obj.archived,
        setup_object_id=setup.vehicle_assembly_id if setup else None,
        sample=obj.is_sample,
        description=revision.document.get("notes", ""),
    )


def list_items(session, principal, kind, include_archived=False, cvt_object_id=None):
    stmt = select(Experiment).where(
        Experiment.kind == kind,
    )
    if not include_archived:
        stmt = stmt.where(Experiment.archived.is_(False))
    items = [
        item_response(session, principal, obj)
        for obj in session.scalars(
            stmt.order_by(Experiment.updated_at.desc(), Experiment.id)
        )
    ]
    return [
        item
        for item in items
        if cvt_object_id is None or item.cvt_object_id == cvt_object_id
    ]


def detail(session, principal, object_id, revision_id=None):
    obj = get_item(session, principal, object_id)
    revision = get_revision(session, principal, revision_id or obj.current_revision_id)
    if revision.experiment_id != obj.id:
        raise access.unavailable()
    history = session.scalars(
        select(ExperimentRevision)
        .where(ExperimentRevision.experiment_id == obj.id)
        .order_by(ExperimentRevision.number.desc())
    )
    return ExperimentDetail(
        item=item_response(session, principal, obj, revision),
        document=DOCUMENT.validate_python(revision.document),
        history=[
            {
                "id": row.id,
                "number": row.number,
                "name": row.document["name"],
                "created_at": aware(row.created_at),
                "change_note": row.change_note,
            }
            for row in history
        ],
    )


def validate_document(session, principal, document, settings):
    if document.kind == "scenarios":
        validate_scenario(document, settings)
        return None
    setup, assembly, params = setup_tuning(
        session, principal, document.setup_revision_id
    )
    apply_values(assembly, params, document.values)
    gateway = CinderGateway()
    try:
        gateway.validate_assembly_shape(assembly)
        validation = validate_assembly(assembly)
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiProblem(422, "invalid_tune", str(exc)) from exc
    if not validation["is_valid"]:
        raise ApiProblem(
            422, "invalid_tune", "The tuned assembly is invalid.", validation
        )
    return setup.vehicle_assembly_id


def save(
    session, principal, settings, document, *, expected=None, object_id=None, note=""
):
    principal.require_write()
    setup_id = validate_document(session, principal, document, settings)
    payload = document.model_dump(mode="json")
    content_hash = canonical_json_hash(payload)
    if object_id:
        obj = get_item(session, principal, object_id, write=True)
        if obj.kind != document.kind:
            raise ApiProblem(422, "experiment_kind", "The document kind cannot change.")
        changed = session.execute(
            update(Experiment)
            .where(
                Experiment.id == obj.id,
                Experiment.current_revision_id == expected,
                Experiment.archived.is_(False),
            )
            .values(updated_at=utc_now())
            .execution_options(synchronize_session=False)
        ).rowcount
        if not changed:
            raise ApiProblem(
                409,
                "revision_conflict",
                "This item changed or was archived. Reopen it before saving.",
            )
        previous = session.get(ExperimentRevision, expected)
        if previous.content_hash == content_hash:
            return obj, False
        number = previous.number + 1
    else:
        if expected is not None:
            raise ApiProblem(
                409,
                "revision_conflict",
                "A new item must not have an expected revision.",
            )
        obj = Experiment(
            account_id=principal.account_id, kind=document.kind, name=document.name
        )
        session.add(obj)
        session.flush()
        number = 1
    revision = ExperimentRevision(
        experiment_id=obj.id,
        number=number,
        document=payload,
        content_hash=content_hash,
        change_note=note,
        created_by_user_id=principal.user_id,
    )
    session.add(revision)
    session.flush()
    obj.current_revision_id, obj.name, obj.setup_object_id = (
        revision.id,
        document.name,
        setup_id,
    )
    obj.updated_at = utc_now()
    session.flush()
    return obj, True


def archive(session, principal, object_id, expected, archived):
    obj = get_item(session, principal, object_id, write=True)
    if not session.execute(
        update(Experiment)
        .where(Experiment.id == obj.id, Experiment.current_revision_id == expected)
        .values(archived=archived, updated_at=utc_now())
        .execution_options(synchronize_session=False)
    ).rowcount:
        raise ApiProblem(
            409, "revision_conflict", "This item changed. Reopen it before archiving."
        )
    session.refresh(obj)
    return item_response(session, principal, obj)


def configuration(session, principal, settings, selection):
    """Rebuild editor intent without invoking mechanics validation or writing data."""
    setup, assembly, params = setup_tuning(
        session, principal, selection.setup_revision_id
    )
    setup_document = document_for_revision(session, principal, "setups", setup.id)
    tune_revision = (
        get_revision(session, principal, selection.tune_revision_id, "tunes")
        if selection.tune_revision_id
        else None
    )
    scenario_revision = (
        get_revision(session, principal, selection.scenario_revision_id, "scenarios")
        if selection.scenario_revision_id
        else None
    )
    tune = DOCUMENT.validate_python(tune_revision.document) if tune_revision else None
    tune_setup = (
        session.get(VehicleAssemblyVersion, tune.setup_revision_id) if tune else None
    )
    if tune and (
        tune_setup is None
        or tune_setup.cvt_design_version_id != setup.cvt_design_version_id
    ):
        raise ApiProblem(
            422,
            "tune_cvt_mismatch",
            "This tune belongs to a different CVT version. Select its CVT or start a new tune for the selected CVT.",
        )
    values = (
        selection.tune_values
        if selection.tune_values is not None
        else tune.values
        if tune
        else {}
    )
    scenario = selection.scenario or (
        DOCUMENT.validate_python(scenario_revision.document)
        if scenario_revision
        else default_scenario()
    )
    apply_values(assembly, params, values)
    case = baseline_case()
    case["assembly"] = assembly
    case["shaft_boundaries"] = {
        "primary": setup_document.data.engine.data.model_dump(),
        "secondary": vehicle_boundary(setup_document.data.vehicle),
    }
    if selection.primary_boundary is not None:
        case["shaft_boundaries"]["primary"] = selection.primary_boundary.model_dump()
    if selection.vehicle_mass_kg is not None:
        case["shaft_boundaries"]["secondary"]["vehicle"]["mass_kg"] = (
            selection.vehicle_mass_kg
        )
    road = apply_scenario(case, scenario, settings)
    provenance = {
        "primary_boundary": selection.primary_boundary.model_dump()
        if selection.primary_boundary
        else None,
        "setup_revision_id": setup.id,
        "setup_revision_number": setup.version_number,
        "setup_name": setup_document.name,
        "engine_revision_id": setup.engine_version_id,
        "cvt_revision_id": setup.cvt_design_version_id,
        "output_revision_id": setup.output_system_version_id,
        "tune_revision_id": tune_revision.id if tune_revision else None,
        "tune_revision_number": tune_revision.number if tune_revision else None,
        "tune_document": deepcopy(tune_revision.document) if tune_revision else None,
        "tune_values": deepcopy(values),
        "tune_unsaved": tune is None or values != tune.values,
        "scenario_revision_id": scenario_revision.id if scenario_revision else None,
        "scenario_revision_number": scenario_revision.number
        if scenario_revision
        else None,
        "scenario": scenario.model_dump(mode="json"),
        "resolved_road": road.model_dump(mode="json"),
        "scenario_unsaved": scenario_revision is None
        or scenario.model_dump(mode="json") != scenario_revision.document,
        "vehicle_mass_override_kg": selection.vehicle_mass_kg,
    }
    return case, road, provenance


def resolve(session, principal, settings, selection):
    case, road, provenance = configuration(session, principal, settings, selection)
    gateway = CinderGateway()
    try:
        gateway.validate_assembly_shape(case["assembly"])
        validation = validate_case(case)
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiProblem(422, "invalid_experiment", str(exc)) from exc
    return ExperimentPreview(
        validation=validation, road=road, simulation_case=case, provenance=provenance
    )
