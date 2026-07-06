"""Compare a small set of screened CINDER tunes over the full 10 s launch.

This is the dynamic second stage after ``screen_launch_tuning.py``.  It reads
the valid static rows, runs only the requested top subset with LSODA, then
ranks them using *actual* hybrid events:

* one persistent engagement and no re-disengagement;
* low-ratio-seat release RPM as the real main-shift onset;
* 10--90 % active-shift duration after that release;
* main-shift speed after release, excluding the short engagement capture;
* no premature high-ratio stop impact.

It intentionally does not run the expensive physical audit for every trial.
Use ``run_tuned_launch.py --ranked-csv ...`` on the chosen result to produce
the complete plot, CSV, JSON, and audit.

Example:

    python tools/screen_launch_tuning.py --no-show
    python tools/preflight_launch_sweep.py --top-n 6 --duration-s 10 --no-show
    python tools/run_tuned_launch.py \
        --ranked-csv artifacts/launch_tuning/full_launch_ranked.csv --rank 1 \
        --duration-s 10 --no-show
"""

from __future__ import annotations

import argparse
import csv
import json
from math import isfinite
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
for _candidate in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    _REPOSITORY_ROOT / "tools",
):
    if str(_candidate) not in sys.path:
        sys.path.append(str(_candidate))

from cinder.results import ReportingGrid, ReportingSettings  # noqa: E402
from launch_tuning_common import (  # noqa: E402
    TuneCandidate,
    integrate_resolved_tune,
    resolve_primary_preload,
    sample_launch_trace,
    transition_metrics,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ranked-csv",
        type=Path,
        default=Path("artifacts/launch_tuning/ranked_tunes.csv"),
        help="Selected-contact static screen CSV.",
    )
    parser.add_argument("--top-n", type=int, default=6)
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--solver-method", default="LSODA")
    parser.add_argument("--max-step-ms", type=float, default=10.0)
    parser.add_argument("--relative-tolerance", type=float, default=3.0e-5)
    parser.add_argument("--absolute-tolerance", type=float, default=1.0e-7)
    parser.add_argument("--maximum-transitions", type=int, default=60)
    parser.add_argument("--diagnostic-samples", type=int, default=700)
    parser.add_argument("--target-main-shift-rpm", type=float, default=3000.0)
    parser.add_argument("--minimum-shift-10-to-90-s", type=float, default=2.5)
    parser.add_argument("--maximum-shift-10-to-90-s", type=float, default=6.0)
    parser.add_argument("--maximum-main-shift-speed-mm-per-s", type=float, default=80.0)
    parser.add_argument(
        "--target-primary-restick-time-s",
        type=float,
        default=3.0,
        help="Preferred maximum time after engagement before the primary re-sticks [s].",
    )
    parser.add_argument("--minimum-upper-stop-time-s", type=float, default=5.5)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/launch_tuning")
    )
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    for name in (
        "duration_s",
        "initial_primary_rpm",
        "max_step_ms",
        "relative_tolerance",
        "absolute_tolerance",
        "target_main_shift_rpm",
        "minimum_shift_10_to_90_s",
        "maximum_shift_10_to_90_s",
        "maximum_main_shift_speed_mm_per_s",
        "target_primary_restick_time_s",
        "minimum_upper_stop_time_s",
    ):
        value = getattr(args, name)
        if not isfinite(value) or value <= 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    if args.minimum_shift_10_to_90_s >= args.maximum_shift_10_to_90_s:
        parser.error("Require --minimum-shift-10-to-90-s < --maximum-shift-10-to-90-s.")
    if args.top_n < 1 or args.maximum_transitions < 1 or args.diagnostic_samples < 100:
        parser.error(
            "--top-n, --maximum-transitions, and --diagnostic-samples must be positive."
        )
    if not args.solver_method.strip():
        parser.error("--solver-method must be non-empty.")
    return args


def _candidate_from_row(row: dict[str, str]) -> tuple[TuneCandidate, float]:
    return (
        TuneCandidate(
            flyweight_mass_kg=float(row["flyweight_mass_kg"]),
            helix_angle_degrees=float(row["helix_angle_degrees"]),
            secondary_torsional_pretension_degrees=float(
                row["secondary_torsional_pretension_degrees"]
            ),
            secondary_compression_preload_mm=float(
                row["secondary_compression_preload_mm"]
            ),
            primary_ramp_kind=row.get("primary_ramp_kind") or "linear",
            primary_ramp_angle_degrees=float(
                row.get("primary_ramp_angle_degrees") or 30.0
            ),
            primary_ramp_start_angle_degrees=float(
                row.get("primary_ramp_start_angle_degrees") or 42.0
            ),
            primary_ramp_end_angle_degrees=float(
                row.get("primary_ramp_end_angle_degrees") or 12.0
            ),
        ),
        float(row["target_engagement_rpm"]),
    )


def _load_candidates(path: Path, top_n: int) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    valid = [row for row in rows if row.get("static_valid") == "1"]
    if not valid:
        raise ValueError(f"No static-valid candidates found in {path}.")
    return valid[:top_n]


def _score(
    metrics: dict[str, object], args: argparse.Namespace
) -> tuple[bool, float, str | None]:
    if metrics["completed"] != 1:
        return False, np.inf, "integration did not reach final time"
    if metrics["persistent_engagement"] != 1:
        return False, np.inf, "engagement was not persistent"
    if int(metrics["disengagement_events"]) != 0:
        return False, np.inf, "re-disengagement occurred"

    onset = metrics["main_shift_onset_primary_rpm"]
    duration = metrics["shift_10_to_90_s"]
    peak = metrics["maximum_main_shift_speed_mm_per_s"]
    if onset is None:
        return False, np.inf, "low-ratio seat did not release"
    if duration is None:
        return False, np.inf, "main shift did not reach 90% active travel"
    if peak is None:
        return False, np.inf, "main shift speed was unavailable"

    score = abs(float(onset) - args.target_main_shift_rpm) / 150.0
    if float(duration) < args.minimum_shift_10_to_90_s:
        score += (
            3.0
            * (args.minimum_shift_10_to_90_s - float(duration))
            / args.minimum_shift_10_to_90_s
        )
    if float(duration) > args.maximum_shift_10_to_90_s:
        score += (
            float(duration) - args.maximum_shift_10_to_90_s
        ) / args.maximum_shift_10_to_90_s
    if float(peak) > args.maximum_main_shift_speed_mm_per_s:
        score += (
            float(peak) - args.maximum_main_shift_speed_mm_per_s
        ) / args.maximum_main_shift_speed_mm_per_s

    primary_slip_duration = metrics.get("primary_slip_duration_s")
    if primary_slip_duration is None:
        score += 4.0
    elif float(primary_slip_duration) > args.target_primary_restick_time_s:
        score += (
            2.0
            * (float(primary_slip_duration) - args.target_primary_restick_time_s)
            / args.target_primary_restick_time_s
        )

    upper_stop = metrics["upper_stop_time_s"]
    if upper_stop is not None and float(upper_stop) < args.minimum_upper_stop_time_s:
        score += (
            3.0
            * (args.minimum_upper_stop_time_s - float(upper_stop))
            / args.minimum_upper_stop_time_s
        )
    return True, float(score), None


def _row_from_run(
    *,
    static_rank: int,
    candidate: TuneCandidate,
    resolved,
    metrics: dict[str, object] | None,
    dynamic_valid: bool,
    dynamic_score: float,
    rejection_reason: str | None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "static_rank": static_rank,
        "flyweight_mass_kg": candidate.flyweight_mass_kg,
        "helix_angle_degrees": candidate.helix_angle_degrees,
        "secondary_torsional_pretension_degrees": candidate.secondary_torsional_pretension_degrees,
        "secondary_compression_preload_mm": candidate.secondary_compression_preload_mm,
        "primary_ramp_kind": candidate.primary_ramp_kind,
        "primary_ramp_angle_degrees": candidate.primary_ramp_angle_degrees,
        "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
        "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
        "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
        "target_engagement_rpm": resolved.target_engagement_rpm,
        "dynamic_valid": int(dynamic_valid),
        "dynamic_score": dynamic_score,
        "dynamic_rejection_reason": rejection_reason,
    }
    if metrics is not None:
        row.update(metrics)
    return row


def _write_csv(rows: list[dict[str, object]], output: Path) -> None:
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot_overview(
    rows: list[dict[str, object]], args: argparse.Namespace, output: Path
) -> None:
    valid = [row for row in rows if row.get("dynamic_valid") == 1]
    if not valid:
        return
    figure, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    onset_axis, stop_axis = axes
    for rank, row in enumerate(valid, start=1):
        onset = float(row["main_shift_onset_primary_rpm"])
        duration = float(row["shift_10_to_90_s"])
        onset_axis.scatter([onset], [duration])
        onset_axis.annotate(
            str(rank), xy=(onset, duration), xytext=(4, 4), textcoords="offset points"
        )
    onset_axis.axvline(
        args.target_main_shift_rpm, linestyle="--", label="main-shift target"
    )
    onset_axis.axhspan(
        args.minimum_shift_10_to_90_s,
        args.maximum_shift_10_to_90_s,
        alpha=0.12,
        label="preferred 10-90 window",
    )
    onset_axis.set_title("Dynamic main-shift behavior")
    onset_axis.set_xlabel("Low-ratio-seat release primary speed [rpm]")
    onset_axis.set_ylabel("Main-shift 10-90% duration [s]")
    onset_axis.grid(True, alpha=0.25)
    onset_axis.legend(loc="best")

    ranks = np.arange(1, len(valid) + 1)
    upper_times = [
        (
            args.duration_s
            if row.get("upper_stop_time_s") in (None, "")
            else float(row["upper_stop_time_s"])
        )
        for row in valid
    ]
    stop_axis.scatter(ranks, upper_times)
    stop_axis.axhline(
        args.minimum_upper_stop_time_s,
        linestyle="--",
        label="minimum desirable stop time",
    )
    stop_axis.axhline(args.duration_s, linestyle=":", label="launch-window end")
    stop_axis.set_title("High-ratio stop timing")
    stop_axis.set_xlabel("Dynamic rank")
    stop_axis.set_ylabel("Upper-stop time [s]; window end means not reached")
    stop_axis.set_xticks(ranks)
    stop_axis.grid(True, alpha=0.25)
    stop_axis.legend(loc="best")
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    args = parse_arguments()
    selected = _load_candidates(args.ranked_csv, args.top_n)
    print(
        f"Running {len(selected)} screened candidates for {args.duration_s:.3g} s "
        f"with {args.solver_method}."
    )
    rows: list[dict[str, object]] = []
    details_dir = args.output_dir / "preflight_details"
    details_dir.mkdir(parents=True, exist_ok=True)

    for static_rank, static_row in enumerate(selected, start=1):
        candidate, engagement_target = _candidate_from_row(static_row)
        print(f"\n[{static_rank}/{len(selected)}] {candidate.label()}")
        resolved = resolve_primary_preload(
            candidate, target_engagement_rpm=engagement_target
        )
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
                reporting_settings=ReportingSettings(
                    grid=ReportingGrid.uniform_count(args.diagnostic_samples),
                ),
            )
            trace = sample_launch_trace(
                system=system,
                result=result,
                maximum_samples=args.diagnostic_samples,
            )
            metrics = transition_metrics(result=result, trace=trace, resolved=resolved)
            dynamic_valid, dynamic_score, rejection_reason = _score(metrics, args)
            print(
                f"  main onset={metrics['main_shift_onset_primary_rpm']} rpm, "
                f"re-stick={metrics.get('primary_restuck_time_s')} s, "
                f"10-90={metrics['shift_10_to_90_s']} s, "
                f"upper={metrics['upper_stop_time_s']} s, "
                f"valid={int(dynamic_valid)}, score={dynamic_score:.3f}"
            )
            detail = {
                "candidate": {
                    "flyweight_mass_kg": candidate.flyweight_mass_kg,
                    "helix_angle_degrees": candidate.helix_angle_degrees,
                    "secondary_torsional_pretension_degrees": candidate.secondary_torsional_pretension_degrees,
                    "secondary_compression_preload_mm": candidate.secondary_compression_preload_mm,
                    "primary_ramp_kind": candidate.primary_ramp_kind,
                    "primary_ramp_angle_degrees": candidate.primary_ramp_angle_degrees,
                    "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
                    "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
                    "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
                },
                "metrics": metrics,
                "dynamic_valid": dynamic_valid,
                "dynamic_score": dynamic_score,
                "dynamic_rejection_reason": rejection_reason,
            }
            with (details_dir / f"static_rank_{static_rank:02d}.json").open(
                "w", encoding="utf-8"
            ) as handle:
                json.dump(detail, handle, indent=2)
            rows.append(
                _row_from_run(
                    static_rank=static_rank,
                    candidate=candidate,
                    resolved=resolved,
                    metrics=metrics,
                    dynamic_valid=dynamic_valid,
                    dynamic_score=dynamic_score,
                    rejection_reason=rejection_reason,
                )
            )
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            print(f"  FAILED: {reason}")
            rows.append(
                _row_from_run(
                    static_rank=static_rank,
                    candidate=candidate,
                    resolved=resolved,
                    metrics=None,
                    dynamic_valid=False,
                    dynamic_score=np.inf,
                    rejection_reason=reason,
                )
            )

    ranked = sorted(
        rows, key=lambda row: (row["dynamic_valid"] != 1, float(row["dynamic_score"]))
    )
    for rank, row in enumerate(ranked, start=1):
        row["dynamic_rank"] = rank
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "full_launch_ranked.csv"
    _write_csv(ranked, csv_path)
    overview_path = args.output_dir / "full_launch_overview.png"
    _plot_overview(ranked, args, overview_path)

    print("\nDynamic ranking")
    print("=" * 120)
    print(
        "rank | valid | onset rpm | 10-90 s | peak main speed mm/s | upper stop s | candidate"
    )
    for row in ranked:
        print(
            f"{int(row['dynamic_rank']):>4} | {int(row['dynamic_valid']):>5} | "
            f"{str(row.get('main_shift_onset_primary_rpm')):>9} | "
            f"{str(row.get('shift_10_to_90_s')):>8} | "
            f"{str(row.get('maximum_main_shift_speed_mm_per_s')):>21} | "
            f"{str(row.get('upper_stop_time_s')):>12} | "
            f"m={float(row['flyweight_mass_kg']):.3f}, h={float(row['helix_angle_degrees']):.1f}, "
            f"twist={float(row['secondary_torsional_pretension_degrees']):.0f}, "
            f"sec={float(row['secondary_compression_preload_mm']):.1f}"
        )
    print(f"\nWrote {csv_path}, {overview_path}, and {details_dir}.")

    if not args.no_show and overview_path.exists():
        plt.show()


if __name__ == "__main__":
    main()
