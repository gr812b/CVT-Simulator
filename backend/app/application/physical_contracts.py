"""Physical editor projections, canonical units and CINDER preflight integration."""

import copy
import csv
import io
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from app.application.cinder_gateway import CinderGateway
from app.application.input_validation import validate_assembly, validate_case
from app.core.errors import ApiProblem
from app.database.resolver import normalize_preset_case
from app.schemas.physical_library import (
    BeltChoice,
    BeltData,
    BeltDocument,
    BeltSection,
    BeltSectionSolveRequest,
    CurveImportRequest,
    CvtChoice,
    CvtData,
    CvtDocument,
    EngineChoice,
    EngineData,
    EngineDocument,
    EnginePoint,
    PhysicalDocument,
    PhysicalField,
    SetupData,
    SetupDocument,
    VehicleData,
)

GATEWAY = CinderGateway()


@lru_cache(maxsize=1)
def _baseline():
    path = Path(__file__).resolve().parents[2] / "presets" / "baja-launch-baseline.json"
    return normalize_preset_case(json.loads(path.read_text())["simulation_case"])


def baseline_case():
    return copy.deepcopy(_baseline())


def resolve_belt_section(request: BeltSectionSolveRequest) -> BeltSection:
    values = request.model_dump(exclude_none=True)
    missing = next(key for key in BeltSection.model_fields if key not in values)
    top, bottom, height, angle = (
        values.get(key) for key in ("outer_width_m", "inner_width_m", "height_m", "half_angle_rad")
    )
    if missing == "half_angle_rad":
        values[missing] = math.atan((top - bottom) / (2 * height))
    elif missing == "height_m":
        values[missing] = (top - bottom) / (2 * math.tan(angle))
    elif missing == "outer_width_m":
        values[missing] = bottom + 2 * height * math.tan(angle)
    else:
        values[missing] = top - 2 * height * math.tan(angle)
    try:
        return BeltSection.model_validate(values)
    except ValueError as exc:
        raise ApiProblem(
            422,
            "invalid_belt_section",
            "These measurements do not form a valid belt section. Top width must exceed bottom width, and all dimensions must be positive.",
        ) from exc


def belt_from_assembly(assembly: dict) -> BeltData:
    geometry = assembly["geometry"]
    return BeltData(
        outer_length_m=geometry["belt_outer_length_m"],
        density_kg_per_m3=assembly["inertias"]["belt_density_kg_per_m3"],
        **geometry["belt"],
        half_angle_rad=math.atan(
            (geometry["belt"]["outer_width_m"] - geometry["belt"]["inner_width_m"])
            / (2 * geometry["belt"]["height_m"])
        ),
    )


def with_belt(data: CvtData) -> CvtData:
    """A chosen belt owns its dimensions; do not accept two competing copies."""
    result = data.model_copy(deep=True)
    belt = result.belt.data
    result.assembly.setdefault("geometry", {}).update(
        {
            "belt_outer_length_m": belt.outer_length_m,
            "sheave_half_angle_rad": belt.half_angle_rad,
            "belt": belt.model_dump(
                exclude={
                    "outer_length_m",
                    "density_kg_per_m3",
                    "length_reference",
                    "half_angle_rad",
                }
            ),
        }
    )
    result.assembly.setdefault("inertias", {})["belt_density_kg_per_m3"] = belt.density_kg_per_m3
    return result


def normalize_document(document: PhysicalDocument) -> PhysicalDocument:
    result = document.model_copy(deep=True)
    if isinstance(result, CvtDocument):
        result.data = with_belt(result.data)
    elif isinstance(result, SetupDocument):
        result.data.cvt.data = with_belt(result.data.cvt.data)
    return result


def vehicle_from_boundary(boundary: dict) -> VehicleData:
    return VehicleData(
        **boundary["vehicle"],
        **boundary["final_drive"],
        direct_secondary_shaft_inertia_kg_m2=boundary["direct_secondary_shaft_inertia_kg_m2"],
        **{
            key: boundary["road_load"][key]
            for key in (
                "rolling_resistance_coefficient",
                "drag_coefficient",
                "frontal_area_m2",
                "air_density_kg_per_m3",
            )
        },
    )


def vehicle_boundary(data: VehicleData) -> dict:
    # Numerical regularization and gravity stay in the backend's supported
    # execution template, outside the ordinary physical editor.
    boundary = baseline_case()["shaft_boundaries"]["secondary"]
    boundary["vehicle"] = data.model_dump(include={"mass_kg", "wheel_rotational_inertia_kg_m2"})
    boundary["final_drive"] = data.model_dump(include={"reduction_ratio", "wheel_radius_m"})
    boundary["direct_secondary_shaft_inertia_kg_m2"] = data.direct_secondary_shaft_inertia_kg_m2
    boundary["road_load"].update(
        data.model_dump(
            include={
                "rolling_resistance_coefficient",
                "drag_coefficient",
                "frontal_area_m2",
                "air_density_kg_per_m3",
            }
        )
    )
    return boundary


def assembly_with_matching_belt(assembly: dict) -> dict:
    """Close the section from bottom width, height and the hardware half-angle.

    Enduro 100 uses the confirmed 11.5 degrees. Its top width is derived;
    the research preset and recorded demo remain untouched.
    """
    assembly = copy.deepcopy(assembly)
    geometry = assembly["geometry"]
    belt = geometry["belt"]
    belt["outer_width_m"] = belt["inner_width_m"] + 2 * belt["height_m"] * math.tan(
        geometry["sheave_half_angle_rad"]
    )
    return assembly


def template_document(kind: str) -> PhysicalDocument:
    case = baseline_case()
    case["assembly"] = assembly_with_matching_belt(case["assembly"])
    metadata = {
        "description": "Starting values from the project baseline; enter your own measurements.",
        "source_label": "CINDER project example",
        "source_notes": "Illustrative model inputs, not certified manufacturer specifications.",
    }
    engine = EngineChoice(
        name="CINDER Default · McMaster engine",
        data=EngineData.model_validate(case["shaft_boundaries"]["primary"]),
        **metadata,
    )
    belt = BeltChoice(
        name="CINDER Default · rubber belt",
        data=belt_from_assembly(case["assembly"]),
        **metadata,
    )
    cvt = CvtChoice(
        name="CINDER Default · McMaster CVT",
        data=with_belt(CvtData(assembly=case["assembly"], belt=belt)),
        **metadata,
    )
    if kind == "engines":
        return EngineDocument(kind=kind, **engine.model_dump(exclude={"revision_id"}))
    if kind == "belts":
        return BeltDocument(kind=kind, **belt.model_dump(exclude={"revision_id"}))
    if kind == "cvts":
        return CvtDocument(kind=kind, **cvt.model_dump(exclude={"revision_id"}))
    return SetupDocument(
        kind="setups",
        name="My vehicle setup",
        data=SetupData(
            engine=engine,
            cvt=cvt,
            vehicle=vehicle_from_boundary(case["shaft_boundaries"]["secondary"]),
        ),
        **metadata,
    )


def validate_physical(document: PhysicalDocument) -> tuple[dict, dict | None]:
    document = normalize_document(document)
    if isinstance(document, BeltDocument):
        return {"is_valid": True, "findings": []}, None
    if isinstance(document, CvtDocument):
        return validate_assembly(document.data.assembly), None
    case = baseline_case()
    if isinstance(document, EngineDocument):
        case["shaft_boundaries"]["primary"] = document.data.model_dump()
    else:
        case["assembly"] = document.data.cvt.data.assembly
        case["shaft_boundaries"] = {
            "primary": document.data.engine.data.model_dump(),
            "secondary": vehicle_boundary(document.data.vehicle),
        }
    report = validate_case(case)
    return report, case if isinstance(document, SetupDocument) and report["is_valid"] else None


def import_engine_curve(request: CurveImportRequest) -> list[EnginePoint]:
    text = request.text.lstrip("\ufeff").strip()
    if not text:
        raise ApiProblem(422, "curve_empty", "Paste at least two speed and torque rows.")
    first = text.splitlines()[0]
    delimiter = "\t" if "\t" in first else ";" if ";" in first else ","
    rows = csv.reader(io.StringIO(text), delimiter=delimiter)
    points = []
    for index, row in enumerate(rows, 1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) == 1:
            row = row[0].split()
        if len(row) != 2:
            raise ApiProblem(
                422,
                "curve_columns",
                f"Row {index}: expected exactly two columns (speed, torque).",
            )
        try:
            speed, torque = (float(value.strip()) for value in row)
        except ValueError as exc:
            # Only an explicit, recognizable first-row header is ignored.
            if (
                index == 1
                and re.search(r"rpm|speed|rad", row[0], re.IGNORECASE)
                and re.search(r"torque|nm|n.m|lb", row[1], re.IGNORECASE)
            ):
                continue
            raise ApiProblem(
                422, "curve_number", f"Row {index}: speed and torque must be numbers."
            ) from exc
        if not all(math.isfinite(value) for value in (speed, torque)) or speed < 0:
            raise ApiProblem(
                422,
                "curve_number",
                f"Row {index}: enter finite values and nonnegative speed.",
            )
        points.append(
            EnginePoint(
                angular_speed_rad_per_s=(
                    speed * math.pi / 30 if request.speed_unit == "rpm" else speed
                ),
                torque_Nm=torque * 1.3558179483314 if request.torque_unit == "lb·ft" else torque,
            )
        )
    if not 2 <= len(points) <= 1000:
        raise ApiProblem(422, "curve_size", "Import between 2 and 1,000 points.")
    points.sort(key=lambda point: point.angular_speed_rad_per_s)
    if any(
        a.angular_speed_rad_per_s == b.angular_speed_rad_per_s for a, b in zip(points, points[1:])
    ):
        raise ApiProblem(
            422,
            "curve_duplicate_speed",
            "Each speed must occur once. Remove duplicate speed rows.",
        )
    return points


@lru_cache(maxsize=1)
def cvt_fields() -> list[PhysicalField]:
    """Editor hints derived from the canonical assembly schema, including variants."""
    schema = GATEWAY.inline_assembly_json_schema()
    fields = {}
    units = (
        ("_kg_per_m3", "kg/m³", "kg/m³", 1),
        ("_kg_m2", "kg·m²", "kg·m²", 1),
        ("_kg_m", "kg·m", "kg·m", 1),
        ("_Nm_per_rad", "N·m/rad", "N·m/rad", 1),
        ("_N_per_m", "N/m", "N/mm", 0.001),
        ("_per_m2", "1/m²", "1/m²", 1),
        ("_per_m", "1/m", "1/m", 1),
        ("_m2", "m²", "m²", 1),
        ("_rad", "rad", "°", 180 / math.pi),
        ("_kg", "kg", "kg", 1),
        ("_m", "m", "mm", 1000),
    )
    notes = {
        "primary_outer_radius_at_zero_shift_m": "Radius to the belt's outer surface at zero shift; not the sheave outside radius or the cord radius.",
        "secondary_outer_radius_at_zero_shift_m": "Radius to the belt's outer surface at zero shift; not the sheave outside radius or the cord radius.",
        "sheave_half_angle_rad": "Half of the included angle between the two sheave faces.",
        "deadzone_shift_m": "Primary axial travel before belt contact closes the initial gap.",
        "max_shift_m": "Maximum global shift coordinate; check that the actuator profiles cover this travel.",
        "movable_sheave_rotational_inertia_kg_m2": "Movable sheave inertia about its shaft. Keep engine and final-drive inertia in their own editors.",
        "mass_per_flyweight_kg": "Mass of one flyweight. Its first and second moments below must describe the same measured mass distribution.",
    }

    def visit(node, path):
        raw_type = node.get("type", [])
        types = {raw_type} if isinstance(raw_type, str) else set(raw_type)
        if types & {"number", "integer"}:
            key = path.rsplit("/", 1)[-1]
            label, unit, display, scale = key, "", "", 1
            for suffix, unit_name, display_name, factor in units:
                if key.endswith(suffix):
                    label, unit, display, scale = (
                        key[: -len(suffix)],
                        unit_name,
                        display_name,
                        factor,
                    )
                    break
            fields[path] = PhysicalField(
                path=path,
                label=label.replace("_", " ").capitalize(),
                unit=unit,
                display_unit=display,
                display_scale=scale,
                description=notes.get(key, ""),
                integer=node.get("type") == "integer",
                minimum=node.get("minimum"),
                maximum=node.get("maximum"),
                advanced=any(
                    word in key
                    for word in (
                        "tolerance",
                        "scan_points",
                        "validation_positions",
                        "compilation_points",
                    )
                ),
            )
        for key, value in node.get("properties", {}).items():
            visit(value, f"{path}/{key}")
        if "items" in node:
            visit(node["items"], f"{path}/*")
        for option in node.get("oneOf", node.get("anyOf", [])):
            visit(option, path)

    visit(schema, "")
    return list(fields.values())
