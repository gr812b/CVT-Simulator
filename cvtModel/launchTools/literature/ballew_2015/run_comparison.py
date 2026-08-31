"""Run the Ballew (2015) five-second CINDER model-to-model comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from math import isclose
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# Make this nested literature runner usable directly from a normal repository
# checkout without requiring an editable install first.
ROOT = Path(__file__).resolve().parent
CVT_MODEL_ROOT = ROOT.parents[2]
for candidate in (CVT_MODEL_ROOT / "src", CVT_MODEL_ROOT):
    if (candidate / "cinder").is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from comparison import (  # noqa: E402
    build_reference_ratio,
    load_reference_series,
    write_all_outputs,
)
from case import (  # noqa: E402
    build_ballew_inertias,
    build_boundary_setup,
    build_initial_cvt_state,
    build_primary_replay_actuator,
)
from constants import (  # noqa: E402
    CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
    CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
    DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2,
    PUBLISHED,
    REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2,
)
from simulation import (  # noqa: E402
    build_simulation_setup,
    integrate_ballew_case,
    integrate_ballew_case_to,
    sample_cinder_trace,
    uniform_report_times,
)
from belt import build_ballew_geometry, build_equivalent_belt_mapping  # noqa: E402

REFERENCE = ROOT / "reference"
PRIMARY_FORCE_CSV = REFERENCE / "figure_45_primary_force.csv"
INPUT_RPM_CSV = REFERENCE / "figure_41_input_rpm.csv"
OUTPUT_RPM_CSV = REFERENCE / "figure_41_output_rpm.csv"
SOURCE_PDF = REFERENCE / "source" / "Ballew_2015_thesis.pdf"
SOURCE_PDF_SHA256 = "cafead74895bbfaf092fe0354f0572064f44c6b4ff10c422877c5ae587f8df44"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "force_replay"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run CINDER against Ballew's 2015 simulated vehicle-acceleration case."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--method", default="LSODA")
    parser.add_argument("--rtol", type=float, default=1.0e-7)
    parser.add_argument("--atol", type=float, default=1.0e-9)
    parser.add_argument("--max-step", type=float, default=1.0e-3)
    parser.add_argument("--report-step", type=float, default=5.0e-3)
    parser.add_argument("--max-transitions", type=int, default=2000)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="validate the reconstruction/reference bundle without integrating",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="write CSV/JSON/Markdown outputs without PNG plots",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _require_inputs()

    mapping = build_equivalent_belt_mapping()
    geometry = build_ballew_geometry(mapping)
    inertias = build_ballew_inertias(mapping)
    initial_state = build_initial_cvt_state(geometry)
    build_boundary_setup()  # validates the reconstructed vehicle boundary
    build_primary_replay_actuator(PRIMARY_FORCE_CSV)  # validates force coverage

    _validate_output_inertia()
    _validate_belt_mass(inertias)
    _validate_zero_sheave_axial_mass(inertias)
    _validate_initial_state(geometry, initial_state)
    _print_audit(mapping, geometry, inertias, initial_state)

    input_reference = load_reference_series(INPUT_RPM_CSV, value_column="input_rpm")
    output_reference = load_reference_series(OUTPUT_RPM_CSV, value_column="output_rpm")
    primary_force = load_reference_series(
        PRIMARY_FORCE_CSV, value_column="primary_axial_force_n"
    )
    ratio_reference = build_reference_ratio(input_reference, output_reference)
    print(
        "\nReference bundle: "
        f"force={primary_force.time_s.size}, inputRPM={input_reference.time_s.size}, "
        f"outputRPM={output_reference.time_s.size}, ratio-grid={ratio_reference.time_s.size}"
    )

    if args.audit_only:
        print("\nAudit complete; --audit-only requested, integration skipped.")
        return

    setup = build_simulation_setup(PRIMARY_FORCE_CSV)
    print(f"Initial hybrid mode: {setup.initial_mode}")
    print(
        "Running untouched five-second CINDER baseline: "
        f"{args.method}, rtol={args.rtol:g}, atol={args.atol:g}, "
        f"max_step={args.max_step:g} s"
    )
    try:
        result = integrate_ballew_case(
            setup,
            relative_tolerance=args.rtol,
            absolute_tolerance=args.atol,
            max_step_s=args.max_step,
            method=args.method,
            maximum_transitions=args.max_transitions,
        )
    except Exception as exc:
        full_error = f"{type(exc).__name__}: {exc}"
        print(f"\nCorrected force-replay run did not complete: {full_error}")
        safe, bracket_error = _find_last_successful_horizon(args=args)
        report_horizon = max(1.0e-8, safe - max(1.0e-9, safe * 1.0e-6))
        setup = build_simulation_setup(PRIMARY_FORCE_CSV)
        result = _integrate_replay_to(setup, report_horizon, args)
        _write_partial_force_replay_outputs(
            output_dir=args.output_dir,
            setup=setup,
            result=result,
            args=args,
            full_run_error=full_error if full_error else bracket_error,
            safe_horizon_s=report_horizon,
            make_plots=not args.no_plots,
        )
        print(f"  last reproducibly successful horizon: {report_horizon:.9f} s")
        print(f"  first visible Figure 45 point: {primary_force.time_s[1]:.9f} s")
        print(f"  first visible Figure 41 primary point: {input_reference.time_s[0]:.9f} s")
        print("  No CINDER parameter or reference trace was changed to force continuation.")
        print(f"Outputs: {args.output_dir.resolve()}")
        return

    uniform_trace = sample_cinder_trace(
        setup,
        result,
        uniform_report_times(step_s=args.report_step),
    )
    input_prediction = sample_cinder_trace(setup, result, input_reference.time_s)
    output_prediction = sample_cinder_trace(setup, result, output_reference.time_s)
    ratio_prediction = sample_cinder_trace(setup, result, ratio_reference.time_s)

    solver_settings = {
        "method": args.method,
        "relative_tolerance": args.rtol,
        "absolute_tolerance": args.atol,
        "max_step_s": args.max_step,
        "maximum_transitions": args.max_transitions,
        "uniform_report_step_s": args.report_step,
        "dense_output_for_reference_sampling": True,
    }
    payload = write_all_outputs(
        output_dir=args.output_dir,
        setup=setup,
        result=result,
        uniform_trace=uniform_trace,
        primary_force=primary_force,
        input_reference=input_reference,
        output_reference=output_reference,
        input_prediction=input_prediction,
        output_prediction=output_prediction,
        ratio_reference=ratio_reference,
        ratio_prediction=ratio_prediction,
        solver_settings=solver_settings,
        make_plots=not args.no_plots,
    )

    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    print(
        f"\nCompleted: {result.termination_reason}; "
        f"segments={len(result.segments)}, transitions={len(result.transitions)}"
    )
    for label, key, unit in (
        ("primary RPM", "primary_rpm", "rpm"),
        ("secondary RPM", "secondary_rpm", "rpm"),
        ("speed ratio", "speed_ratio", ""),
    ):
        values = metrics[key]
        assert isinstance(values, dict)
        print(
            f"  {label}: RMSE={values['root_mean_square_error']:.6g} {unit}, "
            f"MAE={values['mean_absolute_error']:.6g} {unit}, "
            f"max={values['max_absolute_error']:.6g} {unit}"
        )
    print(f"Outputs: {args.output_dir.resolve()}")
    print("No reconstruction parameter was fitted to the Figure 41 traces.")


def _integrate_replay_to(setup, final_time_s: float, args: argparse.Namespace):
    result = integrate_ballew_case_to(
        setup,
        final_time_s=final_time_s,
        relative_tolerance=args.rtol,
        absolute_tolerance=args.atol,
        max_step_s=args.max_step,
        method=args.method,
        maximum_transitions=args.max_transitions,
    )
    if not result.completed:
        raise RuntimeError(
            f"hybrid transition terminated at t={result.final_time:.12g}: "
            f"{result.termination_reason}"
        )
    return result


def _find_last_successful_horizon(*, args: argparse.Namespace) -> tuple[float, str]:
    """Bracket the earliest corrected-replay failure without changing physics."""

    target_s = PUBLISHED.simulation_duration_s
    lo = 0.0
    hi = min(0.01, target_s)
    last_error = "unknown"
    while True:
        try:
            setup = build_simulation_setup(PRIMARY_FORCE_CSV)
            _integrate_replay_to(setup, hi, args)
            lo = hi
            if hi >= target_s:
                return target_s, ""
            hi = min(target_s, hi * 2.0)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            break

    for _ in range(16):
        mid = 0.5 * (lo + hi)
        if mid <= 0.0:
            break
        try:
            setup = build_simulation_setup(PRIMARY_FORCE_CSV)
            _integrate_replay_to(setup, mid, args)
            lo = mid
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            hi = mid
    return lo, last_error


def _write_partial_force_replay_outputs(
    *,
    output_dir: Path,
    setup,
    result,
    args: argparse.Namespace,
    full_run_error: str,
    safe_horizon_s: float,
    make_plots: bool,
) -> None:
    """Persist a failed corrected replay as a diagnostic result, not a traceback."""

    output_dir.mkdir(parents=True, exist_ok=True)
    n = max(2, int(np.ceil(safe_horizon_s / min(args.report_step, 2.0e-4))) + 1)
    times = np.linspace(0.0, safe_horizon_s, n)
    trace = sample_cinder_trace(setup, result, times)

    with (output_dir / "partial_trace.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow((
            "time_s", "primary_rpm", "secondary_rpm", "speed_ratio",
            "shift_m", "shift_speed_m_per_s", "primary_effective_radius_m",
            "secondary_effective_radius_m", "belt_speed_m_per_s", "mode",
        ))
        for i, t in enumerate(trace.time_s):
            writer.writerow((
                f"{t:.12g}", f"{trace.primary_rpm[i]:.12g}",
                f"{trace.secondary_rpm[i]:.12g}", f"{trace.speed_ratio[i]:.12g}",
                f"{trace.shift_m[i]:.12g}", f"{trace.shift_speed_m_per_s[i]:.12g}",
                f"{trace.primary_effective_radius_m[i]:.12g}",
                f"{trace.secondary_effective_radius_m[i]:.12g}",
                f"{trace.belt_speed_m_per_s[i]:.12g}", trace.mode[i],
            ))

    input_ref = load_reference_series(INPUT_RPM_CSV, value_column="input_rpm")
    force_ref = load_reference_series(PRIMARY_FORCE_CSV, value_column="primary_axial_force_n")
    payload = {
        "benchmark": "Ballew 2015 corrected force-replay comparison",
        "completed": False,
        "full_run_error": full_run_error,
        "last_reproducibly_successful_horizon_s": safe_horizon_s,
        "reference_visibility": {
            "figure_45_first_visible_s": float(force_ref.time_s[1]),
            "figure_41_primary_first_visible_s": float(input_ref.time_s[0]),
        },
        "friction_translation": {
            "ballew_mu_static": PUBLISHED.static_friction_coefficient,
            "ballew_mu_kinetic": PUBLISHED.kinetic_friction_coefficient,
            "cinder_static_lambda_limit": CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
            "cinder_kinetic_lambda_magnitude": CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
            "mapping": "lambda = mu / (2 tan(beta))",
        },
        "final_safe_state": {
            "primary_rpm": float(trace.primary_rpm[-1]),
            "secondary_rpm": float(trace.secondary_rpm[-1]),
            "speed_ratio": float(trace.speed_ratio[-1]),
            "shift_mm": float(trace.shift_m[-1] * 1e3),
            "mode": trace.mode[-1],
        },
        "interpretation": (
            "Figure 45 is replayed as the primary clamp input with Ballew's published friction "
            "coefficients translated into CINDER's reduced traction convention. The unchanged "
            "CINDER closure becomes singular before the digitized paper traces are visible; the "
            "benchmark records that outcome rather than reverting the translation or tuning the plant."
        ),
    }
    (output_dir / "termination.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    if make_plots:
        fig, axes = plt.subplots(3, 1, figsize=(9.0, 8.0), sharex=True)
        axes[0].plot(trace.time_s, trace.primary_rpm, label="CINDER primary")
        axes[0].plot(trace.time_s, trace.secondary_rpm, label="CINDER secondary")
        axes[0].set_ylabel("RPM")
        axes[0].legend()
        axes[0].grid(True, alpha=0.25)
        axes[1].plot(trace.time_s, trace.speed_ratio)
        axes[1].set_ylabel("Speed ratio")
        axes[1].grid(True, alpha=0.25)
        axes[2].plot(trace.time_s, trace.shift_m * 1e3)
        axes[2].set_ylabel("Shift [mm]")
        axes[2].set_xlabel("Time [s]")
        axes[2].grid(True, alpha=0.25)
        fig.suptitle("Corrected Ballew force replay (partial trajectory before singular closure)")
        fig.tight_layout()
        fig.savefig(output_dir / "partial_force_replay_diagnostic.png", dpi=180)
        plt.close(fig)


def _require_inputs() -> None:
    missing = [
        path
        for path in (PRIMARY_FORCE_CSV, INPUT_RPM_CSV, OUTPUT_RPM_CSV, SOURCE_PDF)
        if not path.exists()
    ]
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise FileNotFoundError(f"Ballew benchmark source/reference files missing: {names}")

    digest = hashlib.sha256(SOURCE_PDF.read_bytes()).hexdigest()
    if digest != SOURCE_PDF_SHA256:
        raise RuntimeError(
            "Archived Ballew thesis PDF does not match the provenance SHA-256."
        )


def _print_audit(mapping, geometry, inertias, initial_state) -> None:
    initial_position = geometry.evaluate(initial_state.shift_position)
    actual_initial_ratio = PUBLISHED.initial_input_rpm / PUBLISHED.initial_output_rpm

    print("Ballew 2015 CINDER simulated-vehicle benchmark")
    print("  source PDF: archived and SHA-256 verified")
    print("  case: model-to-model simulated vehicle acceleration, not dyno/road data")
    print(f"  fixed engine torque: {PUBLISHED.engine_torque_nm:g} N m")
    print(f"  fixed secondary clamp: {PUBLISHED.output_axial_force_n:g} N")
    print("  primary clamp: prescribed Figure 45 time history")
    print("  output resistance: reconstructed ATV inertia + road load")

    print("\nFriction convention (A10)")
    print(
        f"  Ballew source mu_s / mu_k: {PUBLISHED.static_friction_coefficient:g} / "
        f"{PUBLISHED.kinetic_friction_coefficient:g}"
    )
    print(
        "  CINDER translated lambda_s / lambda_k: "
        f"{CINDER_STATIC_TRACTION_LAMBDA_LIMIT:.9f} / "
        f"{CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE:.9f}"
    )
    print("  mapping: lambda = mu / (2 tan(beta)); gross-capacity translation, not fitting")

    print("\nBelt/shift reconstruction (A3-A5)")
    print(f"  Ballew effective path: {mapping.reference_effective_length_m:.9f} m")
    print(f"  CINDER outer path: {mapping.cinder_outer_length_m:.9f} m")
    print(f"  resolved belt mass: {inertias.belt.mass:.12f} kg")
    print(
        "  moving sheave masses: "
        f"{inertias.axial_translation.primary_moving_sheave_mass:g} / "
        f"{inertias.axial_translation.secondary_moving_sheave_mass:g} kg"
    )
    print("  operating topology: zero-width deadzone / always engaged")
    print("  sheave clamp rows: algebraic; belt dynamics retained")
    print(
        f"  initial RPM: {PUBLISHED.initial_input_rpm:g} / "
        f"{PUBLISHED.initial_output_rpm:g}; exact ratio={actual_initial_ratio:.12f}"
    )
    print(f"  initial shift: {initial_state.shift_position * 1e3:.9f} mm")
    print(
        "  initial effective radii: "
        f"{initial_position.primary.effective * 1e3:.9f} / "
        f"{initial_position.secondary.effective * 1e3:.9f} mm"
    )

    print("\nVehicle-side reconstruction (A1/A9; not fitted)")
    print(
        f"  reflected ATV translation inertia: "
        f"{REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2:.9f} kg m^2"
    )
    print(
        f"  direct secondary boundary inertia: "
        f"{DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2:.9f} kg m^2"
    )


def _validate_output_inertia() -> None:
    reconstructed = (
        PUBLISHED.output_pulley_inertia_kg_m2
        + REFLECTED_ATV_TRANSLATION_INERTIA_KG_M2
        + DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2
    )
    if not isclose(
        reconstructed,
        PUBLISHED.output_pulley_and_atv_inertia_kg_m2,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise RuntimeError("Reconstruction A1 no longer preserves output inertia.")


def _validate_belt_mass(inertias) -> None:
    if not isclose(
        inertias.belt.mass,
        PUBLISHED.belt_mass_kg,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    ):
        raise RuntimeError("Reconstruction A4 no longer preserves the 1 kg belt mass.")


def _validate_zero_sheave_axial_mass(inertias) -> None:
    axial = inertias.axial_translation
    if (
        axial.primary_moving_sheave_mass != 0.0
        or axial.secondary_moving_sheave_mass != 0.0
    ):
        raise RuntimeError("Reconstruction A5 requires zero movable-sheave axial mass.")
    if not isclose(
        axial.belt_mass,
        PUBLISHED.belt_mass_kg,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    ):
        raise RuntimeError("Reconstruction A5 must retain the full belt mass.")


def _validate_initial_state(geometry, state) -> None:
    position = geometry.evaluate(state.shift_position)
    speed_ratio = PUBLISHED.initial_input_rpm / PUBLISHED.initial_output_rpm
    geometry_ratio = position.secondary.effective / position.primary.effective
    if not isclose(geometry_ratio, speed_ratio, rel_tol=0.0, abs_tol=2.0e-11):
        raise RuntimeError("Reconstruction A3 no longer preserves the exact RPM ratio.")
    if state.shift_speed != 0.0:
        raise RuntimeError("Reconstruction A3 requires zero initial shift rate.")


if __name__ == "__main__":
    main()
