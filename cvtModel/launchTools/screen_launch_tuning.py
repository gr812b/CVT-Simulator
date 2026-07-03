"""Fast selected-contact screen for the slower 20 degree helix launch study.

The screen resolves primary preload for a 2000 rpm lower-stop release, then
samples free-shift acceleration just above the low-ratio engagement boundary.
Unlike the earlier version, it evaluates the branch chosen by CINDER's actual
contact policy; primary-slip candidates are therefore retained rather than
being incorrectly discarded for not forming a stick--stick closure.

The default coarse study is intentionally compact:

* helix around 20 deg;
* secondary torsional pretension high enough to oppose premature upshift;
* 0.50--0.55 kg flyweight range, including a slightly stronger primary-clamp reference;
* 2000 rpm engagement and 3000 rpm static onset targets.

Run a 10 s dynamic comparison of the top static candidates next with
``preflight_launch_sweep.py``.  The static onset remains a filter, not the
reported physical main-shift onset; that is the later low-ratio-seat release.
"""

from __future__ import annotations

import argparse
import csv
from itertools import product
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
    ScreenResult,
    TuneCandidate,
    build_operating_system,
    lower_stop_reaction,
    screen_tune,
)


def _float_list(values: list[str]) -> tuple[float, ...]:
    parsed = tuple(float(value) for value in values)
    if not parsed:
        raise argparse.ArgumentTypeError("at least one value is required")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument("--target-shift-onset-rpm", type=float, default=3000.0)
    parser.add_argument("--rpm-start", type=float, default=2400.0)
    parser.add_argument("--rpm-stop", type=float, default=3800.0)
    parser.add_argument("--rpm-step", type=float, default=200.0)
    parser.add_argument("--probe-fraction", type=float, default=0.02)
    parser.add_argument(
        "--flyweight-mass-kg",
        nargs="+",
        default=["0.75", "0.80", "0.85"],
        help="Equivalent flyweight masses [kg] for the traction-first circular-ramp study.",
    )
    parser.add_argument(
        "--helix-angle-deg",
        nargs="+",
        default=["20"],
        help="Secondary helix angles [deg].",
    )
    parser.add_argument(
        "--secondary-twist-deg",
        nargs="+",
        default=["260", "300"],
        help="Secondary torsional installed pretensions [deg].",
    )
    parser.add_argument(
        "--secondary-preload-mm",
        nargs="+",
        default=["100", "110"],
        help="Secondary compression installed preloads [mm].",
    )
    parser.add_argument(
        "--primary-ramp-kind",
        choices=("linear", "circular_hard_to_soft"),
        default="circular_hard_to_soft",
        help="Primary profile family. Circular starts steep and fades over shift travel.",
    )
    parser.add_argument(
        "--primary-ramp-angle-deg",
        type=float,
        default=30.0,
        help="Constant linear-ramp angle [deg].",
    )
    parser.add_argument(
        "--primary-ramp-start-angle-deg",
        nargs="+",
        default=["38", "40"],
        help="Circular low-ratio tangent angles [deg].",
    )
    parser.add_argument(
        "--primary-ramp-end-angle-deg",
        nargs="+",
        default=["28", "30"],
        help="Circular high-ratio tangent angles [deg].",
    )
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument(
        "--gentle-acceleration-limit",
        type=float,
        default=90.0,
        help="Penalty threshold for static free-shift acceleration at target + 200 rpm [m/s^2].",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/launch_tuning"))
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    args.flyweight_mass_kg = _float_list(args.flyweight_mass_kg)
    args.helix_angle_deg = _float_list(args.helix_angle_deg)
    args.secondary_twist_deg = _float_list(args.secondary_twist_deg)
    args.secondary_preload_mm = _float_list(args.secondary_preload_mm)
    args.primary_ramp_start_angle_deg = _float_list(args.primary_ramp_start_angle_deg)
    args.primary_ramp_end_angle_deg = _float_list(args.primary_ramp_end_angle_deg)
    for name in (
        "target_engagement_rpm",
        "target_shift_onset_rpm",
        "rpm_start",
        "rpm_stop",
        "rpm_step",
        "probe_fraction",
        "gentle_acceleration_limit",
        "primary_ramp_angle_deg",
    ):
        if not np.isfinite(getattr(args, name)):
            parser.error(f"--{name.replace('_', '-')} must be finite.")
    if args.target_engagement_rpm <= 0.0 or args.target_shift_onset_rpm <= 0.0:
        parser.error("Targets must be strictly positive.")
    if args.rpm_step <= 0.0 or args.rpm_stop <= args.rpm_start:
        parser.error("Require rpm-stop > rpm-start and rpm-step > 0.")
    if not 0.0 < args.probe_fraction < 1.0:
        parser.error("--probe-fraction must lie strictly between zero and one.")
    if args.top_n < 1:
        parser.error("--top-n must be at least one.")
    if not 0.0 < args.primary_ramp_angle_deg < 89.0:
        parser.error("--primary-ramp-angle-deg must lie strictly between 0 and 89.")
    if any(not 0.0 < value < 89.0 for value in args.primary_ramp_start_angle_deg):
        parser.error("--primary-ramp-start-angle-deg values must lie strictly between 0 and 89.")
    if any(not 0.0 < value < 89.0 for value in args.primary_ramp_end_angle_deg):
        parser.error("--primary-ramp-end-angle-deg values must lie strictly between 0 and 89.")
    if args.primary_ramp_kind == "circular_hard_to_soft" and any(
        start < end
        for start in args.primary_ramp_start_angle_deg
        for end in args.primary_ramp_end_angle_deg
    ):
        parser.error("A hard-to-soft circular ramp requires every start angle to be >= every end angle.")
    return args


def _screen_grid(args: argparse.Namespace) -> np.ndarray:
    count = int(np.floor((args.rpm_stop - args.rpm_start) / args.rpm_step)) + 1
    grid = args.rpm_start + args.rpm_step * np.arange(count + 1)
    grid = grid[grid <= args.rpm_stop + 1.0e-9]
    if grid[-1] < args.rpm_stop - 1.0e-9:
        grid = np.append(grid, args.rpm_stop)
    return grid


def _label(result: ScreenResult, rank: int) -> str:
    onset = "--" if result.estimated_shift_onset_rpm is None else f"{result.estimated_shift_onset_rpm:.0f}"
    modes = sorted({point.contact_mode for point in result.points if point.contact_mode})
    return f"#{rank}: onset={onset} rpm, {'/'.join(modes) or 'failed'}"


def _plot_screen(
    *,
    ranked: list[ScreenResult],
    target_engagement_rpm: float,
    target_shift_onset_rpm: float,
    output: Path,
) -> None:
    shown = [result for result in ranked if result.static_valid][: min(10, len(ranked))]
    if not shown:
        return
    figure, axes = plt.subplots(2, 1, figsize=(12, 10), constrained_layout=True)
    reaction_axis, shift_axis = axes

    reaction_rpm = np.linspace(target_engagement_rpm - 500.0, target_engagement_rpm + 500.0, 51)
    for rank, result in enumerate(shown, start=1):
        system, _ = build_operating_system(result.resolved.constants)
        reactions = [lower_stop_reaction(system, primary_rpm=float(rpm)) for rpm in reaction_rpm]
        reaction_axis.plot(reaction_rpm, reactions, label=f"#{rank}: {result.resolved.candidate.label()}")
    reaction_axis.axvline(target_engagement_rpm, linestyle="--", label="engagement target")
    reaction_axis.axhline(0.0, linestyle=":")
    reaction_axis.set_title("Primary lower-stop reaction: resolved engagement target")
    reaction_axis.set_xlabel("Primary speed [rpm]")
    reaction_axis.set_ylabel("Lower-stop reaction [N]")
    reaction_axis.grid(True, alpha=0.25)
    reaction_axis.legend(fontsize=7, loc="best")

    for rank, result in enumerate(shown, start=1):
        rpms = [point.primary_rpm for point in result.points]
        accelerations = [
            np.nan if point.shift_acceleration_m_per_s2 is None else point.shift_acceleration_m_per_s2
            for point in result.points
        ]
        shift_axis.plot(rpms, accelerations, marker="o", label=_label(result, rank))
    shift_axis.axvline(target_shift_onset_rpm, linestyle="--", label="static onset target")
    shift_axis.axhline(0.0, linestyle=":")
    shift_axis.set_title("Near-low-ratio selected-contact free-shift acceleration")
    shift_axis.set_xlabel("Primary speed [rpm]")
    shift_axis.set_ylabel(r"$\ddot{s}$ [m/s$^2$]")
    shift_axis.grid(True, alpha=0.25)
    shift_axis.legend(fontsize=8, loc="best")
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _write_csv(*, results: list[ScreenResult], output: Path) -> None:
    rows = [result.csv_row(rank=index) for index, result in enumerate(results, start=1)]
    if not rows:
        return
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_arguments()
    rpm_grid = _screen_grid(args)
    candidates = tuple(
        TuneCandidate(
            flyweight_mass_kg=mass,
            helix_angle_degrees=helix,
            secondary_torsional_pretension_degrees=twist,
            secondary_compression_preload_mm=preload,
            primary_ramp_kind=args.primary_ramp_kind,
            primary_ramp_angle_degrees=args.primary_ramp_angle_deg,
            primary_ramp_start_angle_degrees=start_angle,
            primary_ramp_end_angle_degrees=end_angle,
        )
        for mass, helix, twist, preload, start_angle, end_angle in product(
            args.flyweight_mass_kg,
            args.helix_angle_deg,
            args.secondary_twist_deg,
            args.secondary_preload_mm,
            args.primary_ramp_start_angle_deg,
            args.primary_ramp_end_angle_deg,
        )
    )
    print(
        f"Screening {len(candidates)} candidates | engagement target={args.target_engagement_rpm:.0f} rpm | "
        f"static onset target={args.target_shift_onset_rpm:.0f} rpm | static grid={rpm_grid.tolist()}"
    )
    results = [
        screen_tune(
            candidate,
            target_engagement_rpm=args.target_engagement_rpm,
            target_shift_onset_rpm=args.target_shift_onset_rpm,
            static_rpm_grid=rpm_grid,
            probe_fraction=args.probe_fraction,
            gentle_acceleration_limit_m_per_s2=args.gentle_acceleration_limit,
        )
        for candidate in candidates
    ]
    ranked = sorted(results, key=lambda result: (not result.static_valid, result.score))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(results=ranked, output=args.output_dir / "ranked_tunes.csv")
    _plot_screen(
        ranked=ranked,
        target_engagement_rpm=args.target_engagement_rpm,
        target_shift_onset_rpm=args.target_shift_onset_rpm,
        output=args.output_dir / "static_screen.png",
    )

    print("\nTop candidates")
    print("=" * 150)
    print(
        "rank | mass [kg] | ramp | helix [deg] | sec twist [deg] | sec preload [mm] | "
        "primary preload [mm] | static onset [rpm] | selected modes | a(target+200) [m/s^2] | score"
    )
    displayed = 0
    for rank, result in enumerate(ranked, start=1):
        if not result.static_valid:
            continue
        displayed += 1
        candidate = result.resolved.candidate
        onset = "--" if result.estimated_shift_onset_rpm is None else f"{result.estimated_shift_onset_rpm:>18.1f}"
        acceleration = "--" if result.acceleration_at_target_plus_200 is None else f"{result.acceleration_at_target_plus_200:>22.1f}"
        modes = "/".join(sorted({p.contact_mode for p in result.points if p.contact_mode}))
        print(
            f"{rank:>4} | {candidate.flyweight_mass_kg:>9.3f} | "
            f"{(('L' + format(candidate.primary_ramp_angle_degrees, '.0f')) if candidate.primary_ramp_kind == 'linear' else ('C' + format(candidate.primary_ramp_start_angle_degrees, '.0f') + '→' + format(candidate.primary_ramp_end_angle_degrees, '.0f'))):>7} | "
            f"{candidate.helix_angle_degrees:>11.1f} | "
            f"{candidate.secondary_torsional_pretension_degrees:>15.0f} | "
            f"{candidate.secondary_compression_preload_mm:>16.1f} | "
            f"{result.resolved.resolved_primary_preload_mm:>21.3f} | "
            f"{onset:>18} | {modes:>28} | {acceleration:>22} | {result.score:>5.3f}"
        )
        if displayed >= args.top_n:
            break
    if not displayed:
        print("No candidate produced a valid selected-contact static evaluation across the screen grid.")
        print("Inspect ranked_tunes.csv and broaden the candidate range or check the branch diagnostics.")

    rejected = sum(not result.static_valid for result in ranked)
    print(
        f"\nWrote {args.output_dir / 'ranked_tunes.csv'} and {args.output_dir / 'static_screen.png'} "
        f"({len(ranked) - rejected} selected-contact-valid, {rejected} rejected)."
    )
    if not args.no_show:
        image = plt.imread(args.output_dir / "static_screen.png")
        figure, axis = plt.subplots(figsize=(12, 10))
        axis.imshow(image)
        axis.axis("off")
        plt.show()


if __name__ == "__main__":
    main()
