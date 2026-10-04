"""An effective, revision-specific tuning surface; never silently drop a value."""

import math
from copy import deepcopy

from app.application import access
from app.application.physical_contracts import baseline_case, cvt_fields
from app.core.errors import ApiProblem
from app.database.models import CVTDesignVersion, OutputSystemVersion
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
    for i, component in enumerate(assembly["pulleys"]["primary"]["components"]):
        if component["kind"] != "fixed_pivot_roller_flyweight":
            continue
        prefix = f"/pulleys/primary/components/{i}"
        result += [
            {
                "key": "primary_flyweight_mass",
                "kind": "number",
                "label": "Mass per flyweight",
                "description": "Scales all mass moments by the same ratio, preserving this flyweight's shape and density distribution.",
                "group": "primary",
                "unit": "kg",
                "minimum": 0.000001,
                "path": prefix + "/mass_geometry/mass_per_flyweight_kg",
                "mass_geometry_path": prefix + "/mass_geometry",
                "default": component["mass_geometry"]["mass_per_flyweight_kg"],
            },
            {
                "key": "primary_ramp_profile",
                "kind": "ramp",
                "label": "Primary ramp profile",
                "description": "Ramp geometry for the selected fixed-pivot actuator.",
                "group": "ramp",
                "path": prefix + "/geometry/ramp_profile",
                "default": component["geometry"]["ramp_profile"],
            },
        ]
    return result


def setup_tuning(session, principal, setup_revision_id):
    setup = access.library_version(
        session, principal, "vehicle-assemblies", setup_revision_id
    )
    cvt = session.get(CVTDesignVersion, setup.cvt_design_version_id)
    assembly = _current_assembly_document(
        cvt.cinder_assembly, baseline_case()["execution"]
    )
    return setup, assembly, parameters(assembly, cvt.tuning_schema)


def tune_surface(session, principal, setup_revision_id):
    setup, assembly, params = setup_tuning(session, principal, setup_revision_id)
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
                    "unit": unit,
                    "display_unit": display,
                    "display_scale": scale,
                    "default": param["default"],
                    "minimum": param.get("minimum"),
                    "maximum": param.get("maximum"),
                }
            )
    return TuneSurface(
        template={
            "kind": "tunes",
            "name": "New tune",
            "setup_revision_id": setup.id,
            "values": {p["key"]: p["default"] for p in params},
        },
        setup_name=setup.vehicle_assembly.name,
        setup_revision_number=setup.version_number,
        default_vehicle_mass_kg=session.get(
            OutputSystemVersion, setup.output_system_version_id
        ).output_boundary_template["vehicle"]["mass_kg"],
        fields=fields,
    )


def apply_values(assembly, params, values):
    known = {p["key"]: p for p in params}
    unknown = values.keys() - known.keys()
    if unknown:
        raise ApiProblem(
            422,
            "unsupported_tune_value",
            "Values not supported by this setup revision: "
            + ", ".join(sorted(unknown)),
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
                ratio = value / mass["mass_per_flyweight_kg"]
                for name in mass:
                    if "moment" in name:
                        mass[name] *= ratio
        elif not isinstance(value, dict) or value.get("kind") != "piecewise_ramp":
            raise ApiProblem(
                422, "tune_value", f"{param['label']} must be a piecewise ramp."
            )
        parent_path, name = param["path"].rsplit("/", 1)
        pointer(assembly, parent_path)[name] = deepcopy(value)
