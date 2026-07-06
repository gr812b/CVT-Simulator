"""Benchmark native and dense-output CINDER reporting on the same hill-step case.

The benchmark separates four concerns:

1. native integration with no dense solution retained;
2. identical integration retaining SciPy's dense output;
3. uniform report reconstruction from that dense output; and
4. the total dense-report path.

Example:
    python launchTools/benchmark_hill_step_reporting.py --report-step-s 0.01
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

_TOOLS_DIRECTORY = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _TOOLS_DIRECTORY.parent
if str(_TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIRECTORY))
for candidate_path in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if str(candidate_path) not in sys.path:
        sys.path.append(str(candidate_path))

from cinder.execution.hybrid import CVTDynamicState, HybridIntegratorSettings  # noqa: E402
from cinder.results import CVTIntegrationTrace, CVTResultBuilder, ReportingGrid, ReportingSettings  # noqa: E402
from launch_tuning_common import launch_initial_state, resolve_primary_preload  # noqa: E402
from run_hill_step_response import (  # noqa: E402
    _DEFAULT_PRESET,
    load_reference,
    system_with_grade,
)


def _integrate_hill_step(*, args, settings: HybridIntegratorSettings):
    candidate, _ = load_reference(_DEFAULT_PRESET)
    resolved = resolve_primary_preload(candidate, target_engagement_rpm=2000.0)
    initial = launch_initial_state(primary_rpm=1800.0)
    flat_system = system_with_grade(resolved=resolved, grade_degrees=0.0)
    # Benchmark the raw and dense execution paths directly.  The public
    # hill-step tool uses ``run()`` for its standard report; this harness keeps
    # reporting separate so it can measure each cost independently.
    flat = flat_system.integrate(
        time_span=(0.0, args.flat_duration_s),
        initial_state=initial,
        settings=settings,
    )
    hill_system = system_with_grade(resolved=resolved, grade_degrees=args.hill_grade_deg)
    hill = hill_system.integrate(
        time_span=(args.flat_duration_s, args.flat_duration_s + args.hill_duration_s),
        initial_state=CVTDynamicState.from_vector(flat.final_state),
        settings=settings,
    )
    return flat_system, flat, hill_system, hill


def _time(callable_):
    started = perf_counter()
    result = callable_()
    return perf_counter() - started, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flat-duration-s", type=float, default=2.0)
    parser.add_argument("--hill-duration-s", type=float, default=2.0)
    parser.add_argument("--hill-grade-deg", type=float, default=20.0)
    parser.add_argument("--report-step-s", type=float, default=0.01)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--closure-audit", action="store_true")
    args = parser.parse_args()
    if args.flat_duration_s <= 0.0 or args.hill_duration_s <= 0.0:
        parser.error("Durations must be positive.")
    if args.report_step_s <= 0.0:
        parser.error("--report-step-s must be positive.")
    if args.repeats < 1:
        parser.error("--repeats must be at least one.")

    base_settings = HybridIntegratorSettings(
        method="LSODA",
        relative_tolerance=3.0e-5,
        absolute_tolerance=1.0e-7,
        max_step=0.005,
        maximum_transitions=80,
    )

    native_times: list[float] = []
    dense_times: list[float] = []
    report_times: list[float] = []
    flat_report = hill_report = None
    native_flat = native_hill = dense_flat = dense_hill = None

    for _ in range(args.repeats):
        native_seconds, native_runs = _time(
            lambda: _integrate_hill_step(args=args, settings=base_settings)
        )
        dense_settings = replace(base_settings, retain_dense_output=True)
        dense_seconds, dense_runs = _time(
            lambda: _integrate_hill_step(args=args, settings=dense_settings)
        )
        native_flat_system, native_flat, native_hill_system, native_hill = native_runs
        dense_flat_system, dense_flat, dense_hill_system, dense_hill = dense_runs

        report_settings = ReportingSettings(
            grid=ReportingGrid.uniform_time_step(args.report_step_s),
            include_closure_audit=args.closure_audit,
        )
        reporting_seconds, reports = _time(
            lambda: (
                CVTResultBuilder(system=dense_flat_system).build(
                    CVTIntegrationTrace(raw=dense_flat), settings=report_settings
                ),
                CVTResultBuilder(system=dense_hill_system).build(
                    CVTIntegrationTrace(raw=dense_hill), settings=report_settings
                ),
            )
        )
        flat_report, hill_report = reports

        native_final = native_hill.final_state
        dense_final = dense_hill.final_state
        if native_final.shape != dense_final.shape or not (native_final == dense_final).all():
            raise RuntimeError("Dense output changed the hill-step final state.")

        native_times.append(native_seconds)
        dense_times.append(dense_seconds)
        report_times.append(reporting_seconds)

    native_seconds = float(np.median(native_times))
    dense_seconds = float(np.median(dense_times))
    reporting_seconds = float(np.median(report_times))
    assert native_flat is not None and native_hill is not None
    assert flat_report is not None and hill_report is not None

    print("Hill-step dense-reporting benchmark")
    print("=" * 72)
    print(f"repeats (median): {args.repeats}")
    print(f"native integration only:      {native_seconds:.3f} s")
    print(f"dense integration only:       {dense_seconds:.3f} s")
    print(f"dense-output retention delta: {dense_seconds - native_seconds:+.3f} s")
    print(f"uniform report reconstruction:{reporting_seconds:.3f} s")
    print(f"uniform report total:         {dense_seconds + reporting_seconds:.3f} s")
    print(
        "raw native points: "
        f"flat={sum(segment.time.size for segment in native_flat.segments)}, "
        f"hill={sum(segment.time.size for segment in native_hill.segments)}"
    )
    print(
        "uniform report points: "
        f"flat={sum(segment.time.size for segment in flat_report.segments)}, "
        f"hill={sum(segment.time.size for segment in hill_report.segments)}"
    )
    print(f"report grid: {args.report_step_s:g} s")



if __name__ == "__main__":
    main()
