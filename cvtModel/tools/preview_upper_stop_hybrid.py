"""Exercise free engaged travel into the physical upper-stop continuation.

This is a targeted hybrid-regression preview, not a tuned vehicle simulation.
It trims the existing Baja diagnostic baseline for an initial positive shift
acceleration, places a nearby high-ratio stop, and verifies the sequence

    engaged/free -> contact transition(s) -> upper impact -> engaged/upper-stop.

The resulting held-stop segment keeps ``s`` and ``s_dot`` exactly fixed while
shaft and belt states continue through the constrained closure.

Run from the repository root:

    python tools/preview_upper_stop_hybrid.py
"""

from __future__ import annotations

import argparse
from math import isfinite
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialConstants  # noqa: E402
from cinder.contact import ContactTractionLaw  # noqa: E402
from cinder.dynamics import (
    EngagedContactSolveSettings,
    LambdaSearchBounds,
)  # noqa: E402
from cinder.integration import HybridIntegratorSettings  # noqa: E402
from cinder.integration.cvt_operating_hybrid import (
    CVTOperatingHybridSystem,
)  # noqa: E402
from cinder.integration.cvt_operating_limits import (
    CVTShiftOperatingLimits,
)  # noqa: E402
from trim_shift_operating_point import solve_primary_preload_trim  # noqa: E402


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview upper-stop impact and constrained continuation."
    )
    parser.add_argument(
        "--target-s-ddot",
        type=float,
        default=20.0,
        help="Initial positive free-shift acceleration [m/s^2].",
    )
    parser.add_argument(
        "--upper-stop-offset-mm",
        type=float,
        default=0.20,
        help="Temporary high-stop distance above the trimmed state [mm].",
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=0.25,
        help="Integration duration [s].",
    )
    parser.add_argument(
        "--max-step-ms",
        type=float,
        default=1.0,
        help="Maximum solve_ivp step [ms].",
    )
    args = parser.parse_args()
    for name, value in (
        ("--target-s-ddot", args.target_s_ddot),
        ("--upper-stop-offset-mm", args.upper_stop_offset_mm),
        ("--duration-s", args.duration_s),
        ("--max-step-ms", args.max_step_ms),
    ):
        if not isfinite(value):
            parser.error(f"{name} must be finite.")
    if args.target_s_ddot <= 0.0:
        parser.error(
            "--target-s-ddot must be strictly positive for this arrival preview."
        )
    if args.upper_stop_offset_mm <= 0.0:
        parser.error("--upper-stop-offset-mm must be strictly positive.")
    if args.duration_s <= 0.0 or args.max_step_ms <= 0.0:
        parser.error("--duration-s and --max-step-ms must be strictly positive.")
    return args


def main() -> None:
    args = parse_arguments()
    constants = BajaTrialConstants()
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=0.65,
        secondary_static_lambda_limit=0.65,
        primary_kinetic_lambda_magnitude=0.55,
        secondary_kinetic_lambda_magnitude=0.55,
    )
    operating_point = solve_primary_preload_trim(
        reference_constants=constants,
        traction_law=traction_law,
        target_shift_acceleration=args.target_s_ddot,
        preload_min=0.0,
        preload_max=constants.primary_spring_initial_compression,
        scan_points=41,
    )
    upper_stop = (
        operating_point.state.shift_position + args.upper_stop_offset_mm * 1.0e-3
    )
    if upper_stop >= operating_point.baseline.model.geometry.spec.max_shift:
        raise RuntimeError(
            "Requested temporary upper stop lies outside the legal geometry interval."
        )

    system = CVTOperatingHybridSystem(
        model=operating_point.baseline.model,
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=2.0,
                secondary_half_width=2.0,
            ),
            initial_guess=operating_point.evaluation.traction_utilization,
            maximum_closure_condition_number=1.0e8,
        ),
        operating_limits=CVTShiftOperatingLimits(
            lower_stop_shift=0.0,
            engagement_shift=operating_point.baseline.constants.deadzone_shift,
            upper_stop_shift=upper_stop,
        ),
    )
    initial_mode = system.classify_initial_regime(operating_point.state)
    result = system.integrate(
        time_span=(0.0, args.duration_s),
        initial_state=operating_point.state,
        initial_regime=initial_mode,
        settings=HybridIntegratorSettings(
            method="RK45",
            relative_tolerance=1.0e-7,
            absolute_tolerance=1.0e-9,
            max_step=args.max_step_ms * 1.0e-3,
            maximum_transitions=40,
        ),
    )

    print("\nUpper-stop hybrid preview")
    print("=" * 88)
    print(
        f"Trim: preload={operating_point.preload * 1e3:.3f} mm, "
        f"initial s_ddot={operating_point.evaluation.state_derivative.shift_acceleration:+.3f} m/s^2"
    )
    print(f"Temporary upper stop: s={upper_stop * 1e3:.3f} mm")
    print(
        f"Result: completed={result.completed}, reason={result.termination_reason}, "
        f"segments={len(result.segments)}, final t={result.final_time:.6f} s"
    )
    for index, segment in enumerate(result.segments, start=1):
        print(
            f"segment {index}: {segment.mode.engagement.value}/{segment.mode.shift_constraint.value}/"
            f"{segment.mode.contact_regime.mode.value} | "
            f"[{segment.start_time:.6f}, {segment.end_time:.6f}] s | "
            f"events={segment.fired_event_names or ('none',)} | "
            f"s_end={segment.state[3, -1] * 1e3:.4f} mm, "
            f"s_dot_end={segment.state[4, -1] * 1e3:.4f} mm/s"
        )
    for record in result.transitions:
        next_mode = (
            "terminal"
            if record.transition.next_mode is None
            else (
                f"{record.transition.next_mode.engagement.value}/"
                f"{record.transition.next_mode.shift_constraint.value}/"
                f"{record.transition.next_mode.contact_regime.mode.value}"
            )
        )
        reaction = record.transition.metadata.get("upper_stop_reaction")
        reaction_text = "" if reaction is None else f", R_high={float(reaction):+.3f} N"
        print(
            f"transition @ {record.time:.6f} s: {record.transition.reason} -> {next_mode}"
            f"{reaction_text}"
        )

    visited_upper_stop = any(
        segment.mode.shift_constraint.value == "upper_stop"
        for segment in result.segments
    )
    if not visited_upper_stop:
        raise RuntimeError("Preview did not enter the upper-stop constrained regime.")


if __name__ == "__main__":
    main()
