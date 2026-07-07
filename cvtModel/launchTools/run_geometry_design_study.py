"""Direct smoke/demo for CINDER's static CVT geometry design-study API.

Examples
--------
python launchTools/run_geometry_design_study.py --no-show
python launchTools/run_geometry_design_study.py --out-dir geometry_study_output

The script deliberately calls the Case A/Case B solvers and each downstream
numeric evaluator separately. Plotting stays here rather than inside CINDER.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np

from cinder.studies.geometry import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    TargetRatioDesignRequest,
    evaluate_geometry_feasibility,
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
    sample_geometry_path,
    solve_geometry_from_endpoint_radii,
    solve_geometry_from_target_ratios,
    summarize_geometry_design,
)
from baja_trial_baseline import build_baja_trial_baseline


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate and plot CINDER's static CVT geometry study."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("geometry_study_output"),
        help="Directory for generated PNG files and summary JSON.",
    )
    parser.add_argument(
        "--path-samples",
        type=int,
        default=301,
        help="Number of samples along the selected geometry path.",
    )
    parser.add_argument(
        "--field-samples",
        type=int,
        default=180,
        help="Number of primary and secondary radius samples per field axis.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Write figures without opening interactive windows.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    if args.path_samples < 2 or args.field_samples < 2:
        raise SystemExit("--path-samples and --field-samples must both be at least 2.")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    baseline = build_baja_trial_baseline()
    spec = baseline.assembly.geometry.spec
    context = GeometryDesignContext(
        belt=spec.belt,
        belt_outer_length=spec.belt_outer_length,
        sheave_half_angle=spec.sheave_half_angle,
        deadzone_shift=spec.deadzone_shift,
        max_shift=spec.max_shift,
    )

    # Case A: belt plus the low-ratio primary/secondary endpoint radii.
    case_a = solve_geometry_from_endpoint_radii(
        EndpointRadiiDesignRequest(
            context=context,
            primary_outer_radius_at_zero_shift=(
                spec.primary_outer_radius_at_zero_shift
            ),
            secondary_outer_radius_at_zero_shift=(
                spec.secondary_outer_radius_at_zero_shift
            ),
        )
    )

    # Case B: the same design reconstructed only from its ratio extremes.
    case_b = solve_geometry_from_target_ratios(
        TargetRatioDesignRequest(
            context=context,
            maximum_ratio=case_a.maximum_ratio_endpoint.ratio,
            minimum_ratio=case_a.minimum_ratio_endpoint.ratio,
        )
    )

    summary = summarize_geometry_design(case_a)
    path = sample_geometry_path(case_a, sample_count=args.path_samples)
    feasibility = evaluate_geometry_feasibility(
        case_a,
        minimum_primary_wrap_angle=2.0,
        minimum_secondary_wrap_angle=2.0,
    )

    primary_axis, secondary_axis = _field_axes(case_a, args.field_samples)
    radius_plane = evaluate_radius_plane(
        belt=spec.belt,
        center_distance=case_a.center_distance,
        primary_outer_radius=primary_axis,
        secondary_outer_radius=secondary_axis,
    )
    sensitivity = evaluate_ratio_sensitivity_field(
        belt=spec.belt,
        center_distance=case_a.center_distance,
        sheave_half_angle=spec.sheave_half_angle,
        primary_outer_radius=primary_axis,
        secondary_outer_radius=secondary_axis,
    )

    _write_summary(
        output_path=args.out_dir / "geometry_study_summary.json",
        summary=summary,
        case_a=case_a,
        case_b=case_b,
        feasibility=feasibility,
    )
    _print_summary(summary, case_a, case_b, feasibility)

    _plot_ratio_path(path, args.out_dir / "ratio_vs_shift.png")
    _plot_wrap_path(path, args.out_dir / "wrap_angles_vs_shift.png")
    _plot_radius_plane(radius_plane, path, spec.belt_outer_length, args.out_dir / "radius_plane.png")
    _plot_sensitivity_surface(
        sensitivity,
        path,
        args.out_dir / "ratio_sensitivity_surface.png",
    )
    _plot_primary_projection(
        sensitivity,
        path,
        args.out_dir / "ratio_sensitivity_by_primary_radius.png",
    )
    _plot_secondary_projection(
        sensitivity,
        path,
        args.out_dir / "ratio_sensitivity_by_secondary_radius.png",
    )

    if args.no_show:
        plt.close("all")
    else:
        plt.show()


def _field_axes(design, samples: int) -> tuple[np.ndarray, np.ndarray]:
    low = design.maximum_ratio_endpoint
    high = design.minimum_ratio_endpoint
    belt_height = design.geometry_spec.belt.height
    primary_axis = np.linspace(
        max(belt_height * 1.01, low.primary_outer_radius * 0.70),
        high.primary_outer_radius * 1.30,
        samples,
    )
    secondary_axis = np.linspace(
        max(belt_height * 1.01, high.secondary_outer_radius * 0.70),
        low.secondary_outer_radius * 1.20,
        samples,
    )
    return primary_axis, secondary_axis


def _write_summary(*, output_path: Path, summary, case_a, case_b, feasibility) -> None:
    record = {
        "summary_si": asdict(summary),
        "case_a_endpoints_si": {
            "maximum_ratio": asdict(case_a.maximum_ratio_endpoint),
            "minimum_ratio": asdict(case_a.minimum_ratio_endpoint),
        },
        "case_b_reconstruction_si": {
            "center_distance": case_b.center_distance,
            "maximum_ratio": case_b.maximum_ratio_endpoint.ratio,
            "minimum_ratio": case_b.minimum_ratio_endpoint.ratio,
        },
        "feasibility": {
            "is_feasible": feasibility.is_feasible,
            "issues": [asdict(issue) for issue in feasibility.issues],
        },
    }
    output_path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _print_summary(summary, case_a, case_b, feasibility) -> None:
    print("\nStatic CVT geometry study")
    print("=" * 72)
    print(f"Center distance:              {summary.center_distance * 1e3:9.3f} mm")
    print(f"Maximum ratio (zero shift):   {summary.maximum_ratio:9.5f}")
    print(f"Minimum ratio (max shift):    {summary.minimum_ratio:9.5f}")
    print(f"Ratio span:                   {summary.ratio_span:9.5f}x")
    print(f"Active axial shift travel:    {summary.active_shift_travel * 1e3:9.3f} mm")
    print(f"Active primary radial travel: {summary.active_primary_radial_travel * 1e3:9.3f} mm")
    print("\nCase B reconstruction error")
    print(
        "  center distance: "
        f"{(case_b.center_distance - case_a.center_distance) * 1e9:+.3f} nm"
    )
    print(
        "  maximum ratio:   "
        f"{case_b.maximum_ratio_endpoint.ratio - case_a.maximum_ratio_endpoint.ratio:+.3e}"
    )
    print(
        "  minimum ratio:   "
        f"{case_b.minimum_ratio_endpoint.ratio - case_a.minimum_ratio_endpoint.ratio:+.3e}"
    )
    if feasibility.issues:
        print("\nFeasibility findings")
        for issue in feasibility.issues:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}")
    else:
        print("\nFeasibility findings: none")


def _plot_ratio_path(path, output_path: Path) -> None:
    figure, axis = plt.subplots()
    axis.plot(path.shift * 1e3, path.ratio)
    axis.set_xlabel("Global shift position [mm]")
    axis.set_ylabel("CVT ratio")
    axis.set_title("CVT ratio along resolved shift path")
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)


def _plot_wrap_path(path, output_path: Path) -> None:
    figure, axis = plt.subplots()
    axis.plot(path.shift * 1e3, np.degrees(path.primary_wrap_angle), label="Primary")
    axis.plot(path.shift * 1e3, np.degrees(path.secondary_wrap_angle), label="Secondary")
    axis.set_xlabel("Global shift position [mm]")
    axis.set_ylabel("Wrap angle [deg]")
    axis.set_title("Wrap angles along resolved shift path")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)


def _plot_radius_plane(radius_plane, path, selected_length: float, output_path: Path) -> None:
    primary_mesh, secondary_mesh = np.meshgrid(
        radius_plane.primary_outer_radius * 1e3,
        radius_plane.secondary_outer_radius * 1e3,
        indexing="xy",
    )
    figure, axis = plt.subplots()
    ratio_contours = axis.contour(
        primary_mesh,
        secondary_mesh,
        radius_plane.ratio,
        levels=10,
    )
    axis.clabel(ratio_contours, inline=True, fontsize=8, fmt="R = %.2g")
    length_levels = selected_length * np.array([0.90, 0.95, 1.00, 1.05, 1.10])
    length_contours = axis.contour(
        primary_mesh,
        secondary_mesh,
        radius_plane.implied_belt_outer_length,
        levels=length_levels,
        linestyles="dashed",
    )
    axis.clabel(
        length_contours,
        inline=True,
        fontsize=8,
        fmt=lambda value: f"L = {value * 1e3:.0f} mm",
    )
    axis.plot(
        path.primary_outer_radius * 1e3,
        path.secondary_outer_radius * 1e3,
        linewidth=2,
        label="Resolved path",
    )
    axis.set_xlabel("Primary outer radius [mm]")
    axis.set_ylabel("Secondary outer radius [mm]")
    axis.set_title("Radius plane: ratio and belt-length families")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)


def _plot_sensitivity_surface(sensitivity, path, output_path: Path) -> None:
    primary_mesh, secondary_mesh = np.meshgrid(
        sensitivity.primary_outer_radius * 1e3,
        sensitivity.secondary_outer_radius * 1e3,
        indexing="xy",
    )
    figure = plt.figure()
    axis = figure.add_subplot(projection="3d")
    axis.plot_surface(
        primary_mesh,
        secondary_mesh,
        sensitivity.ratio_change_per_mm_shift,
        rstride=2,
        cstride=2,
        linewidth=0,
    )
    axis.plot(
        path.primary_outer_radius * 1e3,
        path.secondary_outer_radius * 1e3,
        path.ratio_change_per_mm_shift,
        linewidth=2,
        label="Resolved path",
    )
    axis.set_xlabel("Primary outer radius [mm]")
    axis.set_ylabel("Secondary outer radius [mm]")
    axis.set_zlabel("dR per mm shift")
    axis.set_title("Static CVT ratio sensitivity surface")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)


def _plot_primary_projection(sensitivity, path, output_path: Path) -> None:
    primary_mesh, secondary_mesh = np.meshgrid(
        sensitivity.primary_outer_radius * 1e3,
        sensitivity.secondary_outer_radius * 1e3,
        indexing="xy",
    )
    valid = sensitivity.feasible_mask & np.isfinite(sensitivity.ratio_change_per_mm_shift)
    figure, axis = plt.subplots()
    triangulation = _structured_projection_triangulation(
        x=primary_mesh,
        y=sensitivity.ratio_change_per_mm_shift,
        valid=valid,
    )
    contours = axis.tricontourf(
        triangulation,
        secondary_mesh.ravel(),
        levels=20,
    )
    figure.colorbar(contours, ax=axis, label="Secondary outer radius [mm]")
    axis.plot(
        path.primary_outer_radius * 1e3,
        path.ratio_change_per_mm_shift,
        linewidth=2,
        label="Resolved path",
    )
    axis.set_xlabel("Primary outer radius [mm]")
    axis.set_ylabel("dR per mm shift")
    axis.set_title("Sensitivity projection coloured by secondary radius")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)


def _plot_secondary_projection(sensitivity, path, output_path: Path) -> None:
    primary_mesh, secondary_mesh = np.meshgrid(
        sensitivity.primary_outer_radius * 1e3,
        sensitivity.secondary_outer_radius * 1e3,
        indexing="xy",
    )
    valid = sensitivity.feasible_mask & np.isfinite(sensitivity.ratio_change_per_mm_shift)
    figure, axis = plt.subplots()
    triangulation = _structured_projection_triangulation(
        x=secondary_mesh,
        y=sensitivity.ratio_change_per_mm_shift,
        valid=valid,
    )
    contours = axis.tricontourf(
        triangulation,
        primary_mesh.ravel(),
        levels=20,
    )
    figure.colorbar(contours, ax=axis, label="Primary outer radius [mm]")
    axis.plot(
        path.secondary_outer_radius * 1e3,
        path.ratio_change_per_mm_shift,
        linewidth=2,
        label="Resolved path",
    )
    axis.set_xlabel("Secondary outer radius [mm]")
    axis.set_ylabel("dR per mm shift")
    axis.set_title("Sensitivity projection coloured by primary radius")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)


def _structured_projection_triangulation(*, x: np.ndarray, y: np.ndarray, valid: np.ndarray):
    """Triangulate only local valid radius-grid cells for a projected field.

    A generic Delaunay triangulation bridges concave masked regions in the
    ``radius``--``dR/ds`` projection. Building triangles cell-by-cell preserves
    the original radius-plane topology and therefore leaves invalid regions
    visibly blank.
    """

    if x.shape != y.shape or x.shape != valid.shape:
        raise ValueError("Projected field arrays must share one shape.")
    rows, columns = x.shape
    node_index = np.arange(rows * columns, dtype=int).reshape(rows, columns)
    triangles: list[tuple[int, int, int]] = []
    mask: list[bool] = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            lower_left = node_index[row, column]
            lower_right = node_index[row, column + 1]
            upper_left = node_index[row + 1, column]
            upper_right = node_index[row + 1, column + 1]
            triangles.extend(
                (
                    (lower_left, lower_right, upper_right),
                    (lower_left, upper_right, upper_left),
                )
            )
            cell_valid = bool(
                valid[row, column]
                and valid[row, column + 1]
                and valid[row + 1, column]
                and valid[row + 1, column + 1]
            )
            mask.extend((not cell_valid, not cell_valid))

    triangulation = mtri.Triangulation(
        x.ravel(),
        y.ravel(),
        triangles=np.asarray(triangles, dtype=int),
    )
    triangulation.set_mask(np.asarray(mask, dtype=bool))
    return triangulation


if __name__ == "__main__":
    main()
