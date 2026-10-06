"""An effective, revision-specific tuning surface; never silently drop a value."""

import math
from copy import deepcopy

from sqlalchemy import select

from app.application import access
from app.application.physical_contracts import baseline_case, cvt_fields
from app.core.errors import ApiProblem
from app.database.experiment_models import (
    CVTDefaultTune,
    Experiment,
    ExperimentRevision,
)
from app.database.hashing import canonical_json_hash
from app.database.resolver import _current_assembly_document
from app.database.tuning import readable_tuning_schema
from app.schemas.experiments import TuneSurface


def pointer(root, path):
    value = root
    for key in path.strip("/").split("/"):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def parameters(assembly, schema):
    result = readable_tuning_schema(assembly, schema)["parameters"]
    for param in result:
        param["minimum"] = param.get("minimum", param.get("min"))
        param["maximum"] = param.get("maximum", param.get("max"))
    for i, component in enumerate(assembly["pulleys"]["primary"]["components"]):
        if component["kind"] != "fixed_pivot_roller_flyweight":
            continue
        prefix = f"/pulleys/primary/components/{i}"
        mass = component["mass_geometry"]
        body = schema.get("flyweight_tip_body_mass_kg")
        length = component["geometry"]["arm_length_m"]
        tip = mass["mass_per_flyweight_kg"] - body if body else None
        tip_model = (
            body is not None
            and tip > 0
            and all(
                math.isclose(mass[key], expected, rel_tol=1e-8, abs_tol=1e-12)
                for key, expected in (
                    ("first_moment_u_kg_m", body * length / 2 + tip * length),
                    ("second_moment_u_kg_m2", body * length**2 / 3 + tip * length**2),
                )
            )
        )
        result += [
            {
                "key": "primary_tip_mass" if tip_model else "primary_flyweight_mass",
                "kind": "number",
                "label": "Replaceable tip mass" if tip_model else "Mass per flyweight",
                "description": "Changes the tip and its mass moments, retaining the arm/body."
                if tip_model
                else "Scales mass and moments together at unchanged mass distribution.",
                "group": "primary",
                "unit": "kg",
                "minimum": 0.000001,
                "path": prefix + "/mass_geometry/mass_per_flyweight_kg",
                "mass_geometry_path": prefix + "/mass_geometry",
                "tip_body_mass": body if tip_model else None,
                "tip_arm_length": length,
                "default": tip if tip_model else mass["mass_per_flyweight_kg"],
            },
            {
                "key": "primary_ramp_profile",
                "kind": "ramp",
                "label": "Primary ramp profile",
                "description": "Ramp geometry for the selected fixed-pivot actuator.",
                "group": "primary",
                "path": prefix + "/geometry/ramp_profile",
                "default": component["geometry"]["ramp_profile"],
            },
        ]
        # Tune intent is a signed displacement from the fixed pivot. The
        # assembly still stores the absolute ramp reference in its own frame.
        geometry = component["geometry"]
        for axis, reference, pivot, label, description in (
            (
                "axial",
                "ramp_reference_axial_position_m",
                "pivot_axial_position_m",
                "Axial offset from pivot",
                "Ramp starting tip at fully open primary; positive in the local closing direction.",
            ),
            (
                "radial",
                "ramp_reference_radius_m",
                "pivot_radius_m",
                "Radial offset from pivot",
                "Ramp starting tip at fully open primary; positive radially outwards from the pivot.",
            ),
        ):
            result.append(
                {
                    "key": f"primary_ramp_{axis}_offset",
                    "kind": "number",
                    "label": label,
                    "description": description,
                    "group": "primary",
                    "subgroup": "ramp_position",
                    "unit": "m",
                    "path": prefix + "/geometry/" + reference,
                    "storage_offset": geometry[pivot],
                    "default": geometry[reference] - geometry[pivot],
                }
            )
    coupling = assembly["pulleys"]["secondary"].get("helical_coupling")
    if coupling:
        result = [p for p in result if p["key"] != "secondary_helix_profile"]
        result.append(
            {
                "key": "secondary_helix_profile",
                "kind": "ramp",
                "group": "secondary",
                "label": "Secondary helix profile",
                "description": "Helix angle is measured from the circumferential direction.",
                "path": "/pulleys/secondary/helical_coupling/profile/circumferential_profile",
                "default": coupling["profile"]["circumferential_profile"],
                "angle_convention": "helix",
            }
        )
    return result


def cvt_tuning(session, principal, cvt_revision_id):
    cvt = access.library_version(session, principal, "cvt-designs", cvt_revision_id)
    assembly = _current_assembly_document(
        cvt.cinder_assembly, baseline_case()["execution"]
    )
    return cvt, assembly, parameters(assembly, cvt.tuning_schema)


def ensure_default_tune(session, cvt):
    """Called only by creation/seed workflows, never as a side effect of reading."""
    current = session.get(CVTDefaultTune, cvt.id)
    if current:
        return current
    reference = session.scalar(
        select(Experiment).where(
            Experiment.cvt_object_id == cvt.cvt_design_id,
            Experiment.is_sample.is_(True),
            Experiment.name == "R00 · Reference",
            Experiment.archived.is_(False),
        )
    )
    if reference:
        revision = session.get(ExperimentRevision, reference.current_revision_id)
        if revision.document.get("cvt_revision_id") != cvt.id:
            reference = None
    if reference is None:
        reference = Experiment(
            account_id=cvt.cvt_design.account_id,
            kind="tunes",
            name="Default tune",
            cvt_object_id=cvt.cvt_design_id,
            is_sample=cvt.cvt_design.catalog_status
            in ("seeded_example", "official", "admin_curated"),
        )
        session.add(reference)
        session.flush()
        assembly = _current_assembly_document(
            cvt.cinder_assembly, baseline_case()["execution"]
        )
        document = {
            "kind": "tunes",
            "name": reference.name,
            "notes": "",
            "cvt_revision_id": cvt.id,
            "values": {
                p["key"]: p["default"] for p in parameters(assembly, cvt.tuning_schema)
            },
        }
        revision = ExperimentRevision(
            experiment_id=reference.id,
            number=1,
            document=document,
            content_hash=canonical_json_hash(document),
            created_by_user_id=cvt.created_by_user_id,
            change_note="Initial tune for this CVT version.",
        )
        session.add(revision)
        session.flush()
        reference.current_revision_id = revision.id
    current = CVTDefaultTune(cvt_revision_id=cvt.id, tune_id=reference.id)
    session.add(current)
    session.flush()
    return current


def default_tune_revision(session, cvt_revision_id):
    default = session.get(CVTDefaultTune, cvt_revision_id)
    if default is None:
        raise ApiProblem(
            409,
            "missing_default_tune",
            "Initialize the database to create this CVT's default tune.",
        )
    obj = session.get(Experiment, default.tune_id)
    return session.get(ExperimentRevision, obj.current_revision_id)


def set_default_tune(session, principal, cvt_revision_id, request):
    from app.application import experiments

    cvt = access.library_version(session, principal, "cvt-designs", cvt_revision_id)
    access.library_object(
        session, principal, "cvt-designs", cvt.cvt_design_id, write=True
    )
    tune = experiments.get_item(session, principal, request.tune_id)
    revision = session.get(ExperimentRevision, tune.current_revision_id)
    if (
        tune.archived
        or tune.kind != "tunes"
        or revision.document["cvt_revision_id"] != cvt.id
    ):
        raise ApiProblem(
            422, "tune_cvt_mismatch", "Choose an active tune for this CVT version."
        )
    from sqlalchemy import update

    changed = session.execute(
        update(CVTDefaultTune)
        .where(
            CVTDefaultTune.cvt_revision_id == cvt.id,
            CVTDefaultTune.tune_id == request.expected_tune_id,
        )
        .values(tune_id=tune.id)
    ).rowcount
    if not changed:
        raise ApiProblem(
            409,
            "default_tune_conflict",
            "The default tune changed. Reload before choosing it again.",
        )
    return tune_surface(session, principal, cvt.id)


def setup_tuning(session, principal, setup_revision_id):
    setup = access.library_version(
        session, principal, "vehicle-assemblies", setup_revision_id
    )
    _, assembly, params = cvt_tuning(session, principal, setup.cvt_design_version_id)
    return setup, assembly, params


def tune_surface(session, principal, cvt_revision_id):
    cvt, _assembly, params = cvt_tuning(session, principal, cvt_revision_id)
    hints = cvt_fields()
    fields = []
    for param in params:
        common = {
            key: param.get(key, "")
            for key in ("key", "label", "description", "group", "kind")
        }
        if param["kind"] == "ramp":
            path = param["path"]
            normalized = "/".join("*" if p.isdigit() else p for p in path.split("/"))
            fields.append(
                {
                    **common,
                    "default": param["default"],
                    "angle_convention": param.get("angle_convention", "profile"),
                    "fields": [
                        hint.model_copy(update={"path": hint.path[len(normalized) :]})
                        for hint in hints
                        if hint.path.startswith(normalized + "/")
                    ],
                }
            )
        else:
            unit = param.get("unit", "")
            display, scale = {
                "kg": ("g", 1000),
                "m": ("mm", 1000),
                "rad": ("°", 180 / math.pi),
                "N/m": ("N/mm", 0.001),
            }.get(unit, (unit, 1))
            fields.append(
                {
                    **common,
                    "subgroup": param.get("subgroup", "parameters"),
                    "unit": unit,
                    "display_unit": display,
                    "display_scale": scale,
                    "default": param["default"],
                    "minimum": param.get("minimum"),
                    "maximum": param.get("maximum"),
                }
            )
    from app.application import experiments

    revision = default_tune_revision(session, cvt.id)
    default = experiments.detail(
        session, principal, revision.experiment_id, revision.id
    )
    template = default.document.model_copy(deep=True)
    template.values = {**{p["key"]: p["default"] for p in params}, **template.values}
    return TuneSurface(
        cvt_object_id=cvt.cvt_design_id,
        cvt_revision_id=cvt.id,
        cvt_name=cvt.cvt_design.name,
        cvt_revision_number=cvt.version_number,
        can_set_default=cvt.cvt_design.account_id == principal.account_id,
        default_tune=default,
        template=template,
        fields=fields,
    )


def apply_values(assembly, params, values):
    known = {p["key"]: p for p in params}
    unknown = values.keys() - known.keys()
    if unknown:
        raise ApiProblem(
            422,
            "unsupported_tune_value",
            "Values not supported by this CVT version: " + ", ".join(sorted(unknown)),
        )
    for key, value in values.items():
        param = known[key]
        if param["kind"] == "number":
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ApiProblem(
                    422, "tune_value", f"{param['label']} must be a finite number."
                )
            if (param.get("minimum") is not None and value < param["minimum"]) or (
                param.get("maximum") is not None and value > param["maximum"]
            ):
                raise ApiProblem(
                    422,
                    "tune_value",
                    f"{param['label']} is outside its supported range.",
                )
            if "mass_geometry_path" in param:
                mass = pointer(assembly, param["mass_geometry_path"])
                body = param.get("tip_body_mass")
                if body is not None:
                    delta = value - (mass["mass_per_flyweight_kg"] - body)
                    length = param["tip_arm_length"]
                    mass["first_moment_u_kg_m"] += delta * length
                    mass["second_moment_u_kg_m2"] += delta * length**2
                    value += body
                else:
                    ratio = value / mass["mass_per_flyweight_kg"]
                    for name in mass:
                        if "moment" in name:
                            mass[name] *= ratio
        elif not isinstance(value, dict) or value.get("kind") != "piecewise_ramp":
            raise ApiProblem(
                422, "tune_value", f"{param['label']} must be a piecewise ramp."
            )
        if param["kind"] == "number" and "storage_offset" in param:
            value += param["storage_offset"]
        parent_path, name = param["path"].rsplit("/", 1)
        pointer(assembly, parent_path)[name] = deepcopy(value)
