#!/usr/bin/env python3
"""Apply the CINDER-only physical tracking-boundary overlay.

Usage from an extracted overlay directory:

    python apply_cinder_tracking_boundaries.py /path/to/CVT-Simulator

The ZIP contains only cvtModel changes.  This script patches existing CINDER
exports/contracts against known develop-branch anchors and fails rather than
guessing if the checkout has drifted.  It intentionally does not change the
CINDER package version; bump that separately when releasing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = "CINDER tracking boundaries v4"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one patch anchor in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_optional_once(path: Path, old: str, new: str) -> None:
    """Upgrade an older overlay block when present; otherwise leave it alone."""
    text = path.read_text(encoding="utf-8")
    if new in text or old not in text:
        return
    if text.count(old) != 1:
        raise RuntimeError(f"Expected at most one upgrade anchor in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "\n" + block.rstrip() + "\n", encoding="utf-8")


def patch_cinder(repo: Path) -> None:
    # Shaft boundary exports.
    shaft_init = repo / "cvtModel/src/cinder/model/boundaries/shaft/__init__.py"
    append_once(
        shaft_init,
        "from .tracking import SpeedTrackingShaftBoundary",
        "\n# Generic physical tracking boundary; imported last to avoid coupling the\n"
        "# core boundary protocol to any validation workflow.\n"
        "from .tracking import SpeedTrackingShaftBoundary  # noqa: E402,F401\n",
    )

    boundaries_init = repo / "cvtModel/src/cinder/model/boundaries/__init__.py"
    replace_once(
        boundaries_init,
        "    ShaftBoundaryContext,\n    TanhLongitudinalTire,",
        "    ShaftBoundaryContext,\n    SpeedTrackingShaftBoundary,\n    TanhLongitudinalTire,",
    )
    replace_once(
        boundaries_init,
        '    "ShaftBoundaryContext",\n    "TanhLongitudinalTire",',
        '    "ShaftBoundaryContext",\n    "SpeedTrackingShaftBoundary",\n    "TanhLongitudinalTire",',
    )

    top_init = repo / "cvtModel/src/cinder/__init__.py"
    replace_once(
        top_init,
        "    ShaftBoundaryContext,\n    TanhLongitudinalTire,",
        "    ShaftBoundaryContext,\n    SpeedTrackingShaftBoundary,\n    TanhLongitudinalTire,",
    )
    replace_once(
        top_init,
        '    "ShaftBoundaryContext",\n    "ShaftBoundaryValue",',
        '    "ShaftBoundaryContext",\n    "ShaftBoundaryValue",\n    "SpeedTrackingShaftBoundary",',
    )

    # Axial tracking force exports.
    forces_init = repo / "cvtModel/src/cinder/model/cvt/actuation/forces/__init__.py"
    replace_once(
        forces_init,
        "from .axial_spring import AxialSpringForce, AxialSpringForceSpec\n",
        "from .axial_motion_tracking import (\n"
        "    AxialMotionTrackingForce,\n"
        "    AxialMotionTrackingForceSpec,\n"
        ")\n"
        "from .axial_spring import AxialSpringForce, AxialSpringForceSpec\n",
    )
    replace_once(
        forces_init,
        '__all__ = [\n    "AxialSpringForce",',
        '__all__ = [\n    "AxialMotionTrackingForce",\n    "AxialMotionTrackingForceSpec",\n    "AxialSpringForce",',
    )

    act_init = repo / "cvtModel/src/cinder/model/cvt/actuation/__init__.py"
    replace_once(
        act_init,
        "from .forces import (\n    AxialSpringForce,",
        "from .forces import (\n    AxialMotionTrackingForce,\n    AxialMotionTrackingForceSpec,\n    AxialSpringForce,",
    )
    replace_once(
        act_init,
        '    "InspectableAxialForceLaw",\n    "AxialSpringForce",',
        '    "InspectableAxialForceLaw",\n    "AxialMotionTrackingForce",\n    "AxialMotionTrackingForceSpec",\n    "AxialSpringForce",',
    )

    # Assembly document support for the generic axial tracking actuator.
    document = repo / "cvtModel/src/cinder/contracts/document.py"
    replace_once(
        document,
        "from cinder.model.cvt.actuation import (\n    AxialSpringForce,",
        "from cinder.model.cvt.actuation import (\n    AxialMotionTrackingForce,\n    AxialMotionTrackingForceSpec,\n    AxialSpringForce,",
    )
    replace_once(
        document,
        "from cinder.model.cvt.profiles import (\n",
        "from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint\n"
        "from cinder.model.cvt.profiles import (\n",
    )
    replace_once(
        document,
        "def _encode_force_law(force_law: object) -> dict[str, Any]:\n",
        "def _encode_time_reference(reference: PiecewiseLinearReference | None) -> dict[str, Any] | None:\n"
        "    if reference is None:\n"
        "        return None\n"
        "    return {\n"
        "        \"points\": [\n"
        "            {\"time_s\": point.time, \"value\": point.value}\n"
        "            for point in reference.points\n"
        "        ]\n"
        "    }\n\n\n"
        "def _decode_time_reference(payload: object, *, name: str) -> PiecewiseLinearReference | None:\n"
        "    if payload is None:\n"
        "        return None\n"
        "    data = _mapping(payload, name)\n"
        "    points = _sequence(_require(data, \"points\"), f\"{name}.points\")\n"
        "    return PiecewiseLinearReference(\n"
        "        tuple(\n"
        "            TimeValuePoint(\n"
        "                time=_number(_mapping(point, f\"{name}.points[{index}]\"), \"time_s\"),\n"
        "                value=_number(_mapping(point, f\"{name}.points[{index}]\"), \"value\"),\n"
        "            )\n"
        "            for index, point in enumerate(points)\n"
        "        )\n"
        "    )\n\n\n"
        "def _encode_force_law(force_law: object) -> dict[str, Any]:\n",
    )
    replace_once(
        document,
        "def _encode_force_law(force_law: object) -> dict[str, Any]:\n    if isinstance(force_law, AxialSpringForce):",
        "def _encode_force_law(force_law: object) -> dict[str, Any]:\n"
        "    if isinstance(force_law, AxialMotionTrackingForce):\n"
        "        spec = force_law.spec\n"
        "        if spec.force_limit == float(\"inf\"):\n"
        "            raise UnsupportedDesignDocumentError(\n"
        "                \"Serialized axial tracking actuators require a finite force_limit.\"\n"
        "            )\n"
        "        return {\n"
        "            \"kind\": \"axial_motion_tracking\",\n"
        "            \"position_reference\": _encode_time_reference(spec.position_reference),\n"
        "            \"speed_reference\": _encode_time_reference(spec.speed_reference),\n"
        "            \"position_gain_N_per_m\": spec.position_gain,\n"
        "            \"speed_gain_N_s_per_m\": spec.speed_gain,\n"
        "            \"force_limit_N\": spec.force_limit,\n"
        "        }\n"
        "    if isinstance(force_law, AxialSpringForce):",
    )
    replace_once(
        document,
        'def _decode_force_law(payload: Mapping[str, Any]) -> object:\n    kind = _string(payload, "kind")\n    if kind == "axial_spring":',
        'def _decode_force_law(payload: Mapping[str, Any]) -> object:\n'
        '    kind = _string(payload, "kind")\n'
        '    if kind == "axial_motion_tracking":\n'
        '        return AxialMotionTrackingForce(\n'
        '            AxialMotionTrackingForceSpec(\n'
        '                position_reference=_decode_time_reference(\n'
        '                    payload.get("position_reference"), name="position_reference"\n'
        '                ),\n'
        '                speed_reference=_decode_time_reference(\n'
        '                    payload.get("speed_reference"), name="speed_reference"\n'
        '                ),\n'
        '                position_gain=_number(payload, "position_gain_N_per_m"),\n'
        '                speed_gain=_number(payload, "speed_gain_N_s_per_m"),\n'
        '                force_limit=_number(payload, "force_limit_N"),\n'
        '            )\n'
        '        )\n'
        '    if kind == "axial_spring":',
    )

    # Public component catalog.
    catalog = repo / "cvtModel/src/cinder/contracts/catalog.py"
    anchor = """    return (\n        ComponentDescriptor(\n            kind=\"axial_spring\","""
    insertion = """    return (\n        ComponentDescriptor(\n            kind=\"axial_motion_tracking\",\n            label=\"Axial motion tracking actuator\",\n            description=(\n                \"Force-limited servo-like local axial actuator that tracks a \"\n                \"piecewise-linear position and/or speed reference without imposing \"\n                \"an exact kinematic constraint.\"\n            ),\n            parameters=(\n                ComponentParameter(\n                    \"position_reference\", \"Position reference\", \"object\", False,\n                    \"Optional piecewise-linear local axial-position reference.\",\n                    value_kind=\"object\", dimension=\"structure\",\n                ),\n                ComponentParameter(\n                    \"speed_reference\", \"Speed reference\", \"object\", False,\n                    \"Optional piecewise-linear local axial-speed reference.\",\n                    value_kind=\"object\", dimension=\"structure\",\n                ),\n                ComponentParameter(\n                    \"position_gain_N_per_m\", \"Position gain\", \"N/m\", True,\n                    \"Proportional local position-error gain.\", 0.0,\n                    dimension=\"linear_stiffness\",\n                ),\n                ComponentParameter(\n                    \"speed_gain_N_s_per_m\", \"Speed gain\", \"N·s/m\", True,\n                    \"Local axial-speed-error gain.\", 0.0, dimension=\"damping\",\n                ),\n                ComponentParameter(\n                    \"force_limit_N\", \"Force limit\", \"N\", True,\n                    \"Symmetric actuator force limit.\", 0.0, dimension=\"force\",\n                ),\n            ),\n        ),\n        ComponentDescriptor(\n            kind=\"axial_spring\","""
    replace_once(catalog, anchor, insertion)

    # Assembly JSON schema for the actuator/reference payload.
    schema = repo / "cvtModel/src/cinder/contracts/schema.py"
    spring_anchor = '        "assemblyAxialSpring": {\n'
    tracking_defs = '''        "assemblyTimeReferencePoint": {\n            "type": "object",\n            "required": ["time_s", "value"],\n            "properties": {"time_s": number, "value": number},\n            "additionalProperties": False,\n        },\n        "assemblyTimeReference": {\n            "type": "object",\n            "required": ["points"],\n            "properties": {\n                "points": {\n                    "type": "array",\n                    "minItems": 2,\n                    "items": {"$ref": "#/$defs/assemblyTimeReferencePoint"},\n                }\n            },\n            "additionalProperties": False,\n        },\n        "assemblyAxialMotionTracking": {\n            "type": "object",\n            "required": [\n                "kind", "position_reference", "speed_reference",\n                "position_gain_N_per_m", "speed_gain_N_s_per_m", "force_limit_N"\n            ],\n            "properties": {\n                "kind": {"const": "axial_motion_tracking"},\n                "position_reference": {\n                    "oneOf": [\n                        {"$ref": "#/$defs/assemblyTimeReference"},\n                        {"type": "null"}\n                    ]\n                },\n                "speed_reference": {\n                    "oneOf": [\n                        {"$ref": "#/$defs/assemblyTimeReference"},\n                        {"type": "null"}\n                    ]\n                },\n                "position_gain_N_per_m": nonnegative,\n                "speed_gain_N_s_per_m": nonnegative,\n                "force_limit_N": positive,\n            },\n            "additionalProperties": False,\n        },\n'''
    replace_once(schema, spring_anchor, tracking_defs + spring_anchor)
    replace_once(
        schema,
        '        "assemblyForceLaw": {\n            "oneOf": [\n                {"$ref": "#/$defs/assemblyAxialSpring"},',
        '        "assemblyForceLaw": {\n            "oneOf": [\n                {"$ref": "#/$defs/assemblyAxialMotionTracking"},\n                {"$ref": "#/$defs/assemblyAxialSpring"},',
    )

    # Composed simulation document support for speed-tracking shaft boundaries.
    simdoc = repo / "cvtModel/src/cinder/contracts/simulation_document.py"
    replace_once(
        simdoc,
        "from cinder.model.boundaries.shaft import (\n    FixedShaftBoundary,",
        "from cinder.model.boundaries.shaft import (\n    FixedShaftBoundary,\n    SpeedTrackingShaftBoundary,",
    )
    replace_once(
        simdoc,
        "from cinder.model.system import CVTAssemblySpec, CVTState, MechanicalCVTPlant\n",
        "from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint\n"
        "from cinder.model.system import CVTAssemblySpec, CVTState, MechanicalCVTPlant\n",
    )
    replace_once(
        simdoc,
        "def _encode_shaft_boundary(boundary: object) -> dict[str, Any]:\n",
        "def _encode_time_reference(reference: PiecewiseLinearReference) -> dict[str, Any]:\n"
        "    return {\n"
        "        \"points\": [\n"
        "            {\"time_s\": point.time, \"value\": point.value}\n"
        "            for point in reference.points\n"
        "        ]\n"
        "    }\n\n\n"
        "def _decode_time_reference(payload: object, *, name: str) -> PiecewiseLinearReference:\n"
        "    data = _mapping(payload, name)\n"
        "    points = _sequence(_require(data, \"points\"), f\"{name}.points\")\n"
        "    return PiecewiseLinearReference(\n"
        "        tuple(\n"
        "            TimeValuePoint(\n"
        "                time=_number(_mapping(point, f\"{name}.points[{index}]\"), \"time_s\"),\n"
        "                value=_number(_mapping(point, f\"{name}.points[{index}]\"), \"value\"),\n"
        "            )\n"
        "            for index, point in enumerate(points)\n"
        "        )\n"
        "    )\n\n\n"
        "def _encode_shaft_boundary(boundary: object) -> dict[str, Any]:\n",
    )

    old_encode = (
        "    if isinstance(boundary, SpeedTrackingShaftBoundary):\n"
        "        return {\n"
        "            \"kind\": \"speed_tracking_shaft\",\n"
        "            \"speed_reference\": _encode_time_reference(boundary.speed_reference),\n"
        "            \"proportional_gain_Nm_s_per_rad\": boundary.proportional_gain,\n"
        "            \"torque_limit_Nm\": boundary.torque_limit,\n"
        "            \"equivalent_inertia_kg_m2\": boundary.equivalent_inertia,\n"
        "            \"feedforward_inertia_kg_m2\": boundary.feedforward_inertia,\n"
        "        }\n"
    )
    new_encode = (
        "    if isinstance(boundary, SpeedTrackingShaftBoundary):\n"
        "        return {\n"
        "            \"kind\": \"speed_tracking_shaft\",\n"
        "            \"speed_reference\": _encode_time_reference(boundary.speed_reference),\n"
        "            \"proportional_gain_Nm_s_per_rad\": boundary.proportional_gain,\n"
        "            \"tracking_error_budget_rad_per_s\": boundary.tracking_error_budget,\n"
        "            \"feedback_authority_fraction\": boundary.feedback_authority_fraction,\n"
        "            \"torque_limit_Nm\": boundary.torque_limit,\n"
        "            \"equivalent_inertia_kg_m2\": boundary.equivalent_inertia,\n"
        "            \"feedforward_inertia_kg_m2\": boundary.feedforward_inertia,\n"
        "        }\n"
    )
    replace_optional_once(simdoc, old_encode, new_encode)
    replace_once(
        simdoc,
        "def _encode_shaft_boundary(boundary: object) -> dict[str, Any]:\n    if isinstance(boundary, FixedShaftBoundary):",
        "def _encode_shaft_boundary(boundary: object) -> dict[str, Any]:\n" + new_encode
        + "    if isinstance(boundary, FixedShaftBoundary):",
    )

    old_decode = (
        "    if kind == \"speed_tracking_shaft\":\n"
        "        return SpeedTrackingShaftBoundary(\n"
        "            speed_reference=_decode_time_reference(\n"
        "                _require(payload, \"speed_reference\"), name=\"shaft_boundary.speed_reference\"\n"
        "            ),\n"
        "            proportional_gain=_number(payload, \"proportional_gain_Nm_s_per_rad\"),\n"
        "            torque_limit=_number(payload, \"torque_limit_Nm\"),\n"
        "            equivalent_inertia=_number(payload, \"equivalent_inertia_kg_m2\"),\n"
        "            feedforward_inertia=_number(payload, \"feedforward_inertia_kg_m2\"),\n"
        "        )\n"
    )
    new_decode = (
        "    if kind == \"speed_tracking_shaft\":\n"
        "        reference = _decode_time_reference(\n"
        "            _require(payload, \"speed_reference\"), name=\"shaft_boundary.speed_reference\"\n"
        "        )\n"
        "        torque_limit = _number(payload, \"torque_limit_Nm\")\n"
        "        equivalent_inertia = (\n"
        "            _number(payload, \"equivalent_inertia_kg_m2\")\n"
        "            if \"equivalent_inertia_kg_m2\" in payload else 0.0\n"
        "        )\n"
        "        feedforward_inertia = (\n"
        "            _number(payload, \"feedforward_inertia_kg_m2\")\n"
        "            if \"feedforward_inertia_kg_m2\" in payload else None\n"
        "        )\n"
        "        error_budget = payload.get(\"tracking_error_budget_rad_per_s\")\n"
        "        authority_fraction = payload.get(\"feedback_authority_fraction\")\n"
        "        explicit_gain = payload.get(\"proportional_gain_Nm_s_per_rad\")\n"
        "        if error_budget is not None:\n"
        "            boundary = SpeedTrackingShaftBoundary.from_tracking_error_budget(\n"
        "                speed_reference=reference,\n"
        "                torque_limit=torque_limit,\n"
        "                tracking_error_budget=float(error_budget),\n"
        "                equivalent_inertia=equivalent_inertia,\n"
        "                feedforward_inertia=feedforward_inertia,\n"
        "                feedback_authority_fraction=(\n"
        "                    SpeedTrackingShaftBoundary.DEFAULT_FEEDBACK_AUTHORITY_FRACTION\n"
        "                    if authority_fraction is None else float(authority_fraction)\n"
        "                ),\n"
        "            )\n"
        "            if explicit_gain is not None and abs(\n"
        "                boundary.proportional_gain - float(explicit_gain)\n"
        "            ) > 1.0e-12 * max(1.0, abs(boundary.proportional_gain)):\n"
        "                raise DesignDocumentError(\n"
        "                    \"speed_tracking_shaft explicit gain is inconsistent with its error-budget tuning.\"\n"
        "                )\n"
        "            return boundary\n"
        "        if explicit_gain is not None:\n"
        "            return SpeedTrackingShaftBoundary(\n"
        "                speed_reference=reference,\n"
        "                proportional_gain=float(explicit_gain),\n"
        "                torque_limit=torque_limit,\n"
        "                equivalent_inertia=equivalent_inertia,\n"
        "                feedforward_inertia=(\n"
        "                    0.0 if feedforward_inertia is None else feedforward_inertia\n"
        "                ),\n"
        "            )\n"
        "        return SpeedTrackingShaftBoundary.auto_tuned(\n"
        "            speed_reference=reference,\n"
        "            torque_limit=torque_limit,\n"
        "            equivalent_inertia=equivalent_inertia,\n"
        "            feedforward_inertia=feedforward_inertia,\n"
        "        )\n"
    )
    replace_optional_once(simdoc, old_decode, new_decode)
    replace_once(
        simdoc,
        'def _decode_shaft_boundary(payload: Mapping[str, Any]) -> object:\n    kind = _string(payload, "kind")\n    if kind == "fixed_shaft":',
        'def _decode_shaft_boundary(payload: Mapping[str, Any]) -> object:\n'
        '    kind = _string(payload, "kind")\n' + new_decode
        + '    if kind == "fixed_shaft":',
    )

    editable = repo / "cvtModel/src/cinder/contracts/editable_schema.py"
    # Keep the resolved gain visible for advanced users, but surface the
    # error-budget control as the normal tuning concept.
    editable_anchor = '''        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/equivalent_rotational_inertia_kg_m2",'''
    old_editable_block = '''        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/equivalent_inertia_kg_m2",\n            "Primary boundary inertia", "Primary shaft boundary", "kg m^2", 0.0,\n            when={"/shaft_boundaries/primary/kind": "fixed_shaft"},\n        ),\n        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/proportional_gain_Nm_s_per_rad",\n            "Primary speed-tracking gain", "Primary shaft boundary", "N m s/rad", 0.0,\n            when={"/shaft_boundaries/primary/kind": "speed_tracking_shaft"},\n        ),\n        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/torque_limit_Nm",\n            "Primary tracking torque limit", "Primary shaft boundary", "N m", 0.0,\n            when={"/shaft_boundaries/primary/kind": "speed_tracking_shaft"},\n        ),\n'''
    editable_block = '''        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/equivalent_inertia_kg_m2",\n            "Primary boundary inertia", "Primary shaft boundary", "kg m^2", 0.0,\n            when={"/shaft_boundaries/primary/kind": "fixed_shaft"},\n        ),\n        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/tracking_error_budget_rad_per_s",\n            "Primary tracking error budget", "Primary shaft boundary", "rad/s", 0.0,\n            when={"/shaft_boundaries/primary/kind": "speed_tracking_shaft"},\n        ),\n        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/proportional_gain_Nm_s_per_rad",\n            "Primary resolved speed-tracking gain", "Primary shaft boundary", "N m s/rad", 0.0,\n            when={"/shaft_boundaries/primary/kind": "speed_tracking_shaft"},\n        ),\n        EditableFieldDescriptor(\n            "/shaft_boundaries/primary/torque_limit_Nm",\n            "Primary tracking torque limit", "Primary shaft boundary", "N m", 0.0,\n            when={"/shaft_boundaries/primary/kind": "speed_tracking_shaft"},\n        ),\n'''
    replace_optional_once(editable, old_editable_block, editable_block)
    replace_once(editable, editable_anchor, editable_block + editable_anchor)



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "repo",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="CVT-Simulator repository root (default: current directory).",
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    required = [
        repo / "cvtModel/src/cinder/contracts/document.py",
        repo / "cvtModel/src/cinder/contracts/simulation_document.py",
        repo / "cvtModel/src/cinder/model/boundaries/shaft/__init__.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(
            "Not a compatible CVT-Simulator checkout; missing:\n  " + "\n  ".join(missing)
        )

    # New files are delivered by extracting this ZIP at repository root.
    delivered = [
        repo / "cvtModel/src/cinder/model/reference.py",
        repo / "cvtModel/src/cinder/model/boundaries/shaft/tracking.py",
        repo / "cvtModel/src/cinder/model/cvt/actuation/forces/axial_motion_tracking.py",
        repo / "cvtModel/tools/check_tracking_boundaries.py",
    ]
    absent = [str(path) for path in delivered if not path.exists()]
    if absent:
        raise SystemExit(
            "Overlay files are missing. Extract the ZIP into the repository root first:\n  "
            + "\n  ".join(absent)
        )

    patch_cinder(repo)
    print("CINDER physical tracking-boundary overlay applied successfully.")
    print("Next checks:")
    print("  python -m pip install -e cvtModel")
    print("  python -m pytest cvtModel/test/validation/test_tracking_components.py cvtModel/test/validation/test_tracking_documents.py")
    print("  python cvtModel/tools/check_tracking_boundaries.py")
    print("  python cvtModel/tools/check_tracking_boundaries.py --plot  # optional visual audit")


if __name__ == "__main__":
    main()
