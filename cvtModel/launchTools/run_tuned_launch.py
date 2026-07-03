"""Run one mechanically plausible CINDER tune through a full hybrid launch.

The default is an intentionally slower 10 s exploratory configuration centered
on a 20 degree torque-reactive helix.  It starts from the requested physical
launch state:

    omega_p(0) = 1800 rpm, omega_s(0) = 0, v_b(0) = 0, s(0) = lower stop.

Use ``screen_launch_tuning.py`` for a fast selected-contact screen, then use
``preflight_launch_sweep.py`` to compare a small group over the full 10 s
window.  This runner is the final detailed diagnostic for one selected tune.

Examples from the repository root:

    python tools/run_tuned_launch.py --no-show

    python tools/run_tuned_launch.py \
        --flyweight-mass-kg 0.55 --helix-angle-deg 20 \
        --secondary-twist-deg 140 --secondary-preload-mm 70 \
        --duration-s 10 --solver-method LSODA --no-show

    python tools/run_tuned_launch.py \
        --ranked-csv artifacts/launch_tuning/ranked_tunes.csv --rank 1 \
        --duration-s 10 --output-dir artifacts/selected_launch --no-show
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

_TOOLS_DIRECTORY = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _TOOLS_DIRECTORY.parent
# Keep this launchTools directory first: its baseline/tuning helpers are an
# intentional overlay and must not be shadowed by an older root-level copy.
if str(_TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIRECTORY))
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT, _REPOSITORY_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.append(str(_candidate))

from launch_tuning_common import (  # noqa: E402
    MILLIMETRE,
    RPM_PER_RADIAN_PER_SECOND,
    TuneCandidate,
    integrate_resolved_tune,
    plot_launch_diagnostics,
    plot_primary_ramp_profile,
    resolve_primary_preload,
    sample_launch_trace,
    transition_metrics,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--ranked-csv", type=Path, help="CSV produced by screen_launch_tuning.py")
    source.add_argument("--manual", action="store_true", help="Use manual parameters (the default).")
    parser.add_argument("--rank", type=int, default=1, help="One-based valid rank in --ranked-csv.")
    parser.add_argument("--flyweight-mass-kg", type=float, default=0.80)
    parser.add_argument("--helix-angle-deg", type=float, default=20.0)
    parser.add_argument("--secondary-twist-deg", type=float, default=300.0)
    parser.add_argument("--secondary-preload-mm", type=float, default=110.0)
    parser.add_argument(
        "--primary-ramp-kind",
        choices=("linear", "circular_hard_to_soft"),
        default="circular_hard_to_soft",
        help="Primary radial-ramp profile. The circular option starts steep and fades with shift travel.",
    )
    parser.add_argument("--primary-ramp-angle-deg", type=float, default=30.0, help="Constant linear-ramp angle [deg].")
    parser.add_argument("--primary-ramp-start-angle-deg", type=float, default=38.0, help="Circular-ramp low-ratio tangent angle [deg].")
    parser.add_argument("--primary-ramp-end-angle-deg", type=float, default=30.0, help="Circular-ramp high-ratio tangent angle [deg].")
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument(
        "--solver-method",
        default="LSODA",
        help="solve_ivp method. LSODA is the practical default for longer slip/seat trajectories.",
    )
    parser.add_argument("--max-step-ms", type=float, default=20.0)
    parser.add_argument("--relative-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--absolute-tolerance", type=float, default=1.0e-7)
    parser.add_argument("--first-step-ms", type=float, default=None)
    parser.add_argument("--diagnostic-samples", type=int, default=1200)
    parser.add_argument("--maximum-transitions", type=int, default=60)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/tuned_launch"))
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    finite_fields = (
        "flyweight_mass_kg",
        "helix_angle_deg",
        "secondary_twist_deg",
        "secondary_preload_mm",
        "primary_ramp_angle_deg",
        "primary_ramp_start_angle_deg",
        "primary_ramp_end_angle_deg",
        "target_engagement_rpm",
        "initial_primary_rpm",
        "duration_s",
        "max_step_ms",
        "relative_tolerance",
        "absolute_tolerance",
    )
    for name in finite_fields:
        value = getattr(args, name)
        if not np.isfinite(value):
            parser.error(f"--{name.replace('_', '-')} must be finite.")
    if args.first_step_ms is not None and (
        not np.isfinite(args.first_step_ms) or args.first_step_ms <= 0.0
    ):
        parser.error("--first-step-ms must be finite and positive when supplied.")
    if args.duration_s <= 0.0 or args.max_step_ms <= 0.0:
        parser.error("duration and max step must be strictly positive.")
    if not 0.0 < args.primary_ramp_angle_deg < 89.0:
        parser.error("--primary-ramp-angle-deg must lie strictly between 0 and 89.")
    if not 0.0 < args.primary_ramp_start_angle_deg < 89.0:
        parser.error("--primary-ramp-start-angle-deg must lie strictly between 0 and 89.")
    if not 0.0 < args.primary_ramp_end_angle_deg < 89.0:
        parser.error("--primary-ramp-end-angle-deg must lie strictly between 0 and 89.")
    if (
        args.primary_ramp_kind == "circular_hard_to_soft"
        and args.primary_ramp_start_angle_deg < args.primary_ramp_end_angle_deg
    ):
        parser.error("A hard-to-soft circular ramp requires start angle >= end angle.")
    if args.relative_tolerance <= 0.0 or args.absolute_tolerance <= 0.0:
        parser.error("integration tolerances must be strictly positive.")
    if args.rank < 1:
        parser.error("--rank must be at least one.")
    if args.diagnostic_samples < 100:
        parser.error("--diagnostic-samples must be at least 100.")
    if args.maximum_transitions < 1:
        parser.error("--maximum-transitions must be at least one.")
    if not args.solver_method.strip():
        parser.error("--solver-method must be non-empty.")
    return args


def _candidate_from_csv(path: Path, rank: int) -> tuple[TuneCandidate, float]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    validity_column = "dynamic_valid" if rows and "dynamic_valid" in rows[0] else "static_valid"
    valid = [row for row in rows if row.get(validity_column) == "1"]
    if rank > len(valid):
        raise ValueError(
            f"Requested valid rank {rank}, but CSV contains only {len(valid)} valid rows "
            f"according to {validity_column}."
        )
    row = valid[rank - 1]
    return (
        TuneCandidate(
            flyweight_mass_kg=float(row["flyweight_mass_kg"]),
            helix_angle_degrees=float(row["helix_angle_degrees"]),
            secondary_torsional_pretension_degrees=float(
                row["secondary_torsional_pretension_degrees"]
            ),
            secondary_compression_preload_mm=float(row["secondary_compression_preload_mm"]),
            primary_ramp_kind=row.get("primary_ramp_kind") or "linear",
            primary_ramp_angle_degrees=float(row.get("primary_ramp_angle_degrees") or 30.0),
            primary_ramp_start_angle_degrees=float(row.get("primary_ramp_start_angle_degrees") or 42.0),
            primary_ramp_end_angle_degrees=float(row.get("primary_ramp_end_angle_degrees") or 12.0),
        ),
        float(row["target_engagement_rpm"]),
    )


def _optional_system_audit(*, system, result) -> tuple[bool | None, list[str]]:
    """Run the repository's system audit when the checkout exposes it."""

    test_path = _REPOSITORY_ROOT / "test" / "cinder"
    if not test_path.exists():
        return None, ["Physical audit unavailable: test/cinder/hybrid_system_checks.py was not found."]
    if str(test_path) not in sys.path:
        sys.path.insert(0, str(test_path))
    try:
        from hybrid_system_checks import CVTSystemCheckSettings, check_cvt_hybrid_result

        report = check_cvt_hybrid_result(
            system=system,
            result=result,
            settings=CVTSystemCheckSettings(maximum_samples_per_segment=96),
        )
        return report.passed, list(report.summary_lines())
    except Exception as error:
        return None, [f"Physical audit failed to execute: {type(error).__name__}: {error}"]


def _write_trace_csv(*, path: Path, trace) -> None:
    header = (
        "time_s",
        "primary_rpm",
        "secondary_rpm",
        "belt_speed_m_per_s",
        "shift_mm",
        "shift_speed_mm_per_s",
        "mode",
        "primary_torque_nm",
        "secondary_torque_nm",
        "primary_lambda",
        "secondary_lambda",
        "primary_normal_n",
        "secondary_normal_n",
        "primary_relative_speed_m_per_s",
        "secondary_relative_speed_m_per_s",
        "active_shift_boundary_reaction_n",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index, time in enumerate(trace.time):
            state = trace.state[:, index]
            writer.writerow(
                (
                    time,
                    state[0] * RPM_PER_RADIAN_PER_SECOND,
                    state[1] * RPM_PER_RADIAN_PER_SECOND,
                    state[2],
                    state[3] / MILLIMETRE,
                    state[4] / MILLIMETRE,
                    trace.mode_label[index],
                    trace.primary_torque[index],
                    trace.secondary_torque[index],
                    trace.primary_lambda[index],
                    trace.secondary_lambda[index],
                    trace.primary_normal[index],
                    trace.secondary_normal[index],
                    trace.primary_relative_speed[index],
                    trace.secondary_relative_speed[index],
                    trace.stop_reaction[index],
                )
            )


def _print_selected_tune(*, candidate: TuneCandidate, resolved, target_engagement: float, args) -> None:
    print("Selected tune")
    print("=" * 88)
    print(candidate.label())
    print(
        f"primary preload resolved to {resolved.resolved_primary_preload_mm:.3f} mm for "
        f"{target_engagement:.0f} rpm lower-stop release "
        f"(reaction={resolved.lower_stop_reaction_at_target_n:+.3e} N)."
    )
    print(
        f"Launch initial condition: primary={args.initial_primary_rpm:.0f} rpm, "
        "secondary=0 rpm, belt=0 m/s, lower stop."
    )
    print(
        f"Integration: {args.duration_s:.3g} s, {args.solver_method}, "
        f"max step={args.max_step_ms:.3g} ms, rtol={args.relative_tolerance:.1e}, "
        f"atol={args.absolute_tolerance:.1e}."
    )


def main() -> None:
    args = parse_arguments()
    if args.ranked_csv is not None:
        candidate, target_engagement = _candidate_from_csv(args.ranked_csv, args.rank)
    else:
        candidate = TuneCandidate(
            flyweight_mass_kg=args.flyweight_mass_kg,
            helix_angle_degrees=args.helix_angle_deg,
            secondary_torsional_pretension_degrees=args.secondary_twist_deg,
            secondary_compression_preload_mm=args.secondary_preload_mm,
            primary_ramp_kind=args.primary_ramp_kind,
            primary_ramp_angle_degrees=args.primary_ramp_angle_deg,
            primary_ramp_start_angle_degrees=args.primary_ramp_start_angle_deg,
            primary_ramp_end_angle_degrees=args.primary_ramp_end_angle_deg,
        )
        target_engagement = args.target_engagement_rpm

    resolved = resolve_primary_preload(candidate, target_engagement_rpm=target_engagement)
    _print_selected_tune(
        candidate=candidate,
        resolved=resolved,
        target_engagement=target_engagement,
        args=args,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        system, result = integrate_resolved_tune(
            resolved,
            duration_seconds=args.duration_s,
            initial_primary_rpm=args.initial_primary_rpm,
            maximum_step_seconds=args.max_step_ms * 1.0e-3,
            relative_tolerance=args.relative_tolerance,
            absolute_tolerance=args.absolute_tolerance,
            maximum_transitions=args.maximum_transitions,
            method=args.solver_method,
            first_step_seconds=(
                None if args.first_step_ms is None else args.first_step_ms * 1.0e-3
            ),
        )
    except Exception as error:
        failure = {
            "candidate": {
                "flyweight_mass_kg": candidate.flyweight_mass_kg,
                "helix_angle_degrees": candidate.helix_angle_degrees,
                "secondary_torsional_pretension_degrees": (
                    candidate.secondary_torsional_pretension_degrees
                ),
                "secondary_compression_preload_mm": candidate.secondary_compression_preload_mm,
                "primary_ramp_kind": candidate.primary_ramp_kind,
                "primary_ramp_angle_degrees": candidate.primary_ramp_angle_degrees,
                "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
                "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
                "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
            },
            "integration": {
                "duration_s": args.duration_s,
                "solver_method": args.solver_method,
                "maximum_transitions": args.maximum_transitions,
            },
            "error": f"{type(error).__name__}: {error}",
        }
        with (args.output_dir / "launch_failure.json").open("w", encoding="utf-8") as handle:
            json.dump(failure, handle, indent=2)
        print("\nHybrid integration did not reach the requested final time.")
        print(f"{failure['error']}")
        print(f"Wrote {args.output_dir / 'launch_failure.json'}.")
        return

    trace = sample_launch_trace(system=system, result=result, maximum_samples=args.diagnostic_samples)
    metrics = transition_metrics(result=result, trace=trace, resolved=resolved)
    metrics["physical_audit_passed"], audit_lines = _optional_system_audit(system=system, result=result)

    figure = plot_launch_diagnostics(
        trace=trace,
        result=result,
        resolved=resolved,
        static_lambda_limit=0.65,
    )
    figure.savefig(args.output_dir / "launch_diagnostics.png", dpi=180)
    ramp_figure = plot_primary_ramp_profile(resolved=resolved)
    ramp_figure.savefig(args.output_dir / "primary_ramp_profile.png", dpi=180)
    _write_trace_csv(path=args.output_dir / "launch_trace.csv", trace=trace)
    with (args.output_dir / "launch_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "candidate": {
                    "flyweight_mass_kg": candidate.flyweight_mass_kg,
                    "helix_angle_degrees": candidate.helix_angle_degrees,
                    "secondary_torsional_pretension_degrees": (
                        candidate.secondary_torsional_pretension_degrees
                    ),
                    "secondary_compression_preload_mm": candidate.secondary_compression_preload_mm,
                    "primary_ramp_kind": candidate.primary_ramp_kind,
                    "primary_ramp_angle_degrees": candidate.primary_ramp_angle_degrees,
                    "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
                    "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
                    "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
                },
                "integration": {
                    "duration_s": args.duration_s,
                    "solver_method": args.solver_method,
                    "max_step_ms": args.max_step_ms,
                    "relative_tolerance": args.relative_tolerance,
                    "absolute_tolerance": args.absolute_tolerance,
                },
                "metrics": metrics,
                "physical_audit": audit_lines,
            },
            handle,
            indent=2,
        )

    print("\nHybrid result")
    print("=" * 88)
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print("\nPhysical audit")
    for line in audit_lines:
        print(f"  {line}")
    if metrics["engagement_events"] > 1 or metrics["disengagement_events"] > 0:
        print(
            "\nWARNING: engagement/disengagement cycling was observed. Treat this as a "
            "transition diagnostic rather than a launch ranking."
        )
    print(
        f"\nWrote {args.output_dir / 'launch_diagnostics.png'}, "
        f"{args.output_dir / 'primary_ramp_profile.png'}, "
        f"{args.output_dir / 'launch_trace.csv'}, and {args.output_dir / 'launch_summary.json'}."
    )

    if not args.no_show:
        # Show the constrained-layout diagnostic directly; reopening its PNG in
        # a separate imshow axis was what made the 3x3 grid appear tiny.
        plt.show()
    else:
        plt.close(figure)
        plt.close(ramp_figure)


if __name__ == "__main__":
    main()
