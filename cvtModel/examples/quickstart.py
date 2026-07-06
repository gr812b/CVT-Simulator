"""A small runnable CINDER walkthrough using the packaged example assembly.

Run after installing the repository in editable mode:

    python examples/quickstart.py

This script owns no CVT equations. It demonstrates:

    JSON assembly -> decode -> validate -> geometry path -> actuator field
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cinder.contracts import (
    decode_assembly_document,
    project_clamping_force_response,
    project_geometry_path,
    validate_assembly,
)
from cinder.studies.actuation import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    ActuationStateCoordinate,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    sample_pulley_clamping_force,
)
from cinder.studies.geometry import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    sample_geometry_path,
    solve_geometry_from_endpoint_radii,
    summarize_geometry_design,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "examples" / "baja_baseline_assembly.json").read_text())
    assembly = decode_assembly_document(payload)
    validation = validate_assembly(assembly)
    if not validation.is_valid:
        raise RuntimeError(f"Assembly errors: {validation.errors!r}")

    spec = assembly.geometry.spec
    context = GeometryDesignContext(
        belt=spec.belt,
        belt_outer_length=spec.belt_outer_length,
        sheave_half_angle=spec.sheave_half_angle,
        deadzone_shift=spec.deadzone_shift,
        max_shift=spec.max_shift,
    )
    design = solve_geometry_from_endpoint_radii(
        EndpointRadiiDesignRequest(
            context=context,
            primary_outer_radius_at_zero_shift=spec.primary_outer_radius_at_zero_shift,
            secondary_outer_radius_at_zero_shift=spec.secondary_outer_radius_at_zero_shift,
        )
    )
    summary = summarize_geometry_design(design)
    path = sample_geometry_path(design, sample_count=41)

    field = sample_pulley_clamping_force(
        PulleyClampingForceStudyRequest(
            cvt=assembly,
            pulley=PulleyLocation.INPUT,
            point=ActuationOperatingPoint(shift_position=spec.deadzone_shift),
            axes=(
                ActuationResponseAxis(
                    ActuationStateCoordinate.SHIFT_POSITION,
                    np.linspace(spec.deadzone_shift, spec.max_shift, 21),
                ),
                ActuationResponseAxis(
                    ActuationStateCoordinate.SHAFT_SPEED,
                    np.linspace(0.0, 6_000.0 * 2.0 * np.pi / 60.0, 21),
                ),
            ),
        )
    )

    print("Validation errors:", validation.errors)
    print(f"Center distance: {summary.center_distance * 1e3:.2f} mm")
    print(f"Ratio range: {summary.maximum_ratio:.3f} to {summary.minimum_ratio:.3f}")
    print("Geometry path keys:", tuple(project_geometry_path(path)["columns"][i]["key"] for i in range(len(project_geometry_path(path)["columns"]))))
    print("Actuation field keys:", tuple(project_clamping_force_response(field)["columns"][i]["key"] for i in range(len(project_clamping_force_response(field)["columns"]))))


if __name__ == "__main__":
    main()
