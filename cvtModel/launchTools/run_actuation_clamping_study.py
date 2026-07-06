"""Direct plotting smoke test for CINDER's static clamping-response study.

This script owns no CVT force math.  It builds one existing CVT baseline,
asks CINDER for two table-like response fields, checks returned-column
consistency, and plots the force columns supplied by CINDER.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from cinder.model.cvt.closure import ClosureUnknown, ClosureUnknowns
from cinder.studies.actuation import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    ActuationStateCoordinate,
    ClampingForceResponseField,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    sample_pulley_clamping_force,
)
from baja_trial_baseline import RPM_TO_RAD_PER_SECOND, build_baja_trial_baseline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("actuation_study_demo"),
        help="Directory receiving plots and flattened response tables.",
    )
    parser.add_argument("--samples", type=int, default=81)
    parser.add_argument("--no-show", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.samples < 2:
        raise ValueError("--samples must be at least 2.")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    baseline = build_baja_trial_baseline()
    cvt = baseline.assembly
    spec = cvt.geometry.spec

    primary = sample_pulley_clamping_force(
        PulleyClampingForceStudyRequest(
            cvt=cvt,
            pulley=PulleyLocation.INPUT,
            point=ActuationOperatingPoint(shift_position=spec.deadzone_shift),
            axes=(
                ActuationResponseAxis(
                    ActuationStateCoordinate.SHIFT_POSITION,
                    np.linspace(spec.deadzone_shift, spec.max_shift, args.samples),
                ),
                ActuationResponseAxis(
                    ActuationStateCoordinate.SHAFT_SPEED,
                    np.linspace(0.0, 6_000.0 * RPM_TO_RAD_PER_SECOND, args.samples),
                ),
            ),
        )
    )

    secondary = sample_pulley_clamping_force(
        PulleyClampingForceStudyRequest(
            cvt=cvt,
            pulley=PulleyLocation.OUTPUT,
            point=ActuationOperatingPoint(
                shift_position=spec.deadzone_shift,
                shaft_speed=1_800.0 * RPM_TO_RAD_PER_SECOND,
                closure_unknowns=ClosureUnknowns.zeros(),
            ),
            axes=(
                ActuationResponseAxis(
                    ActuationStateCoordinate.SHIFT_POSITION,
                    np.linspace(spec.deadzone_shift, spec.max_shift, args.samples),
                ),
                ActuationResponseAxis(
                    ClosureUnknown.SECONDARY_TORQUE,
                    np.linspace(0.0, 140.0, args.samples),
                ),
            ),
        )
    )

    _check_force_columns(primary)
    _check_force_columns(secondary)
    _write_flat_table(primary, args.out_dir / "primary_clamping_response.csv")
    _write_flat_table(secondary, args.out_dir / "secondary_clamping_response.csv")
    _plot_force_columns(
        primary,
        output_directory=args.out_dir,
        title_prefix="Primary clamping response",
        x_label="Global shift position [mm]",
        y_label="Input shaft speed [RPM]",
        x_values=primary.column("shift_position_m") * 1.0e3,
        y_values=primary.column("shaft_speed_rad_per_s") / RPM_TO_RAD_PER_SECOND,
        file_prefix="primary",
    )
    _plot_force_columns(
        secondary,
        output_directory=args.out_dir,
        title_prefix="Secondary clamping response",
        x_label="Global shift position [mm]",
        y_label="Secondary shaft torque [N m]",
        x_values=secondary.column("shift_position_m") * 1.0e3,
        y_values=secondary.column("secondary_torque_Nm"),
        file_prefix="secondary",
    )

    print("\nStatic actuator clamping study")
    print("=" * 72)
    print("Primary returned columns:")
    for key in primary.column_keys:
        print(f"  {key}")
    print("\nSecondary returned columns:")
    for key in secondary.column_keys:
        print(f"  {key}")
    print(f"\nWrote output to: {args.out_dir.resolve()}")

    if args.no_show:
        plt.close("all")
    else:
        plt.show()


def _check_force_columns(field: ClampingForceResponseField) -> None:
    """Check only relations returned by CINDER; do not recalculate CVT mechanics."""

    contributions = tuple(
        key
        for key in field.column_keys
        if key.endswith("_clamping_force_N") and key != "total_clamping_force_N"
    )
    np.testing.assert_allclose(
        field.column("total_clamping_force_N"),
        sum((field.column(key) for key in contributions), start=0.0),
        rtol=0.0,
        atol=1.0e-10,
    )


def _write_flat_table(field: ClampingForceResponseField, output_path: Path) -> None:
    """Write CINDER's self-describing columns as ordinary CSV rows."""

    keys = field.column_keys
    flattened = {key: field.column(key).ravel() for key in keys}
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for index in range(field.column(keys[0]).size):
            writer.writerow({key: flattened[key][index] for key in keys})


def _plot_force_columns(
    field: ClampingForceResponseField,
    *,
    output_directory: Path,
    title_prefix: str,
    x_label: str,
    y_label: str,
    x_values: np.ndarray,
    y_values: np.ndarray,
    file_prefix: str,
) -> None:
    """Plot every resolved force column returned by the study, without naming mechanisms."""

    force_columns = tuple(
        key
        for key in field.column_keys
        if key.endswith("_clamping_force_N")
        and (
            key == "total_clamping_force_N"
            or not np.allclose(field.column(key), field.column(key).flat[0])
        )
    )
    for key in force_columns:
        figure, axis = plt.subplots()
        contour = axis.contourf(x_values, y_values, field.column(key), levels=24)
        figure.colorbar(contour, ax=axis, label="Clamping force [N]")
        axis.set_xlabel(x_label)
        axis.set_ylabel(y_label)
        axis.set_title(f"{title_prefix}: {key}")
        figure.tight_layout()
        figure.savefig(output_directory / f"{file_prefix}_{key}.png", dpi=180)


if __name__ == "__main__":
    main()
