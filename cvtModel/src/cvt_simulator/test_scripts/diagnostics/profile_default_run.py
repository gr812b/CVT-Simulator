"""Profile the default CVT simulation run.

This script runs the default SimulationArgs() path through cvt_simulator only,
captures cProfile stats, and prints a practical text breakdown:
- top cumulative-time functions
- caller/callee context for the hottest functions

It is intentionally self-contained so it can be rerun without creating a temp
script.
"""

from __future__ import annotations

import argparse
import cProfile
import re
import pstats
import time
from pathlib import Path

from cvt_simulator.main import simulate_cvt_model
from cvt_simulator.sim_utils.simulation_args import SimulationArgs


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile the default CVT run.")
    parser.add_argument(
        "--limit-seconds",
        type=float,
        default=120.0,
        help="Wall-clock time limit before aborting the run and printing partial stats.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("default_run.prof"),
        help="Path to the cProfile output file.",
    )
    parser.add_argument(
        "--stats-lines",
        type=int,
        default=30,
        help="Number of cumulative-time rows to print.",
    )
    parser.add_argument(
        "--call-context-lines",
        type=int,
        default=15,
        help="Number of caller/callee rows to print for hotspots.",
    )
    return parser


def _run_profile(limit_seconds: float) -> tuple[cProfile.Profile, float, bool, str]:
    profiler = cProfile.Profile()
    start = time.perf_counter()
    timed_out = False
    timeout_message = ""

    def progress_callback(percent: float, *_args):
        if time.perf_counter() - start >= limit_seconds:
            raise TimeoutError(f"profile cap reached at {percent:.1f}%")

    profiler.enable()
    try:
        simulate_cvt_model(
            SimulationArgs(),
            progress_callback=progress_callback,
        )
    except TimeoutError as exc:
        timed_out = True
        timeout_message = str(exc)
    finally:
        profiler.disable()

    elapsed = time.perf_counter() - start
    return profiler, elapsed, timed_out, timeout_message


def _print_breakdown(stats: pstats.Stats, stats_lines: int, context_lines: int) -> None:
    print("\n=== Top cProfile (cumtime) ===")
    stats.sort_stats("cumtime").print_stats(stats_lines)

    top_functions = stats.fcn_list[: min(3, len(stats.fcn_list))]
    if not top_functions:
        return

    print("\n=== Hotspot Callers / Callees ===")
    for func in top_functions:
        print(f"\n--- {func[2]} ({func[0]}:{func[1]}) ---")
        selection = re.escape(pstats.func_std_string(func))
        print("Callers:")
        stats.print_callers(selection)
        print("Callees:")
        stats.print_callees(selection)


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    profiler, elapsed, timed_out, timeout_message = _run_profile(args.limit_seconds)
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumtime")
    stats.dump_stats(str(args.output))

    print("=== Profile Summary ===")
    print(f"elapsed_s: {elapsed:.3f}")
    print(f"status: {'timeout' if timed_out else 'completed'}")
    print(f"profile_file: {args.output.resolve()}")
    if timed_out:
        print(f"message: {timeout_message}")

    _print_breakdown(stats, args.stats_lines, args.call_context_lines)


if __name__ == "__main__":
    main()
