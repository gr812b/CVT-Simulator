"""Run scenario-level physical checks on the complete hybrid CVT simulator.

This is intentionally an executable system harness, not a unit-test suite.
Each scenario integrates the real operating-regime dispatcher, samples every
visited physical regime, and asserts invariants such as contact admissibility,
stop unilateralness, deadzone lock preservation, and non-negative kinetic
dissipation.

Run from the repository root:

    python test/cinder/run_hybrid_system_checks.py
    python test/cinder/run_hybrid_system_checks.py --scenario upper_stop
    python test/cinder/run_hybrid_system_checks.py --scenario one_second
    python test/cinder/run_hybrid_system_checks.py --save-dir artifacts/cvt_system_checks
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    _REPOSITORY_ROOT / "tools",
):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import (  # noqa: E402
    BajaTrialConstants,
    build_baja_trial_baseline,
)
from cinder.contact import ContactTractionLaw  # noqa: E402
from cinder.dynamics import (  # noqa: E402
    EngagedContactSolveSettings,
    LambdaSearchBounds,
)
from cinder.integration import CVTDynamicState, HybridIntegratorSettings  # noqa: E402

try:  # noqa: E402
    from .hybrid_system_checks import (
        CVTSystemCheckSettings,
        check_cvt_hybrid_result,
    )
except ImportError:  # Direct execution: python test/cinder/run_hybrid_system_checks.py
    from hybrid_system_checks import (
        CVTSystemCheckSettings,
        check_cvt_hybrid_result,
    )
from cinder.integration.cvt_operating_hybrid import (  # noqa: E402
    CVTOperatingHybridSystem,
)
from cinder.integration.cvt_operating_limits import (  # noqa: E402
    CVTShiftOperatingLimits,
)


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    description: str
    build: Callable[[], tuple[CVTOperatingHybridSystem, CVTDynamicState, float]]
    required_transition_fragments: tuple[str, ...]
    max_step: float = 1.0e-4


def _build_system(
    constants: BajaTrialConstants,
    *,
    upper_stop_shift: float | None = None,
) -> CVTOperatingHybridSystem:
    baseline = build_baja_trial_baseline(constants)
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=0.65,
        secondary_static_lambda_limit=0.65,
        primary_kinetic_lambda_magnitude=0.55,
        secondary_kinetic_lambda_magnitude=0.55,
    )
    return CVTOperatingHybridSystem(
        model=baseline.model,
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=2.0,
                secondary_half_width=2.0,
            ),
            initial_guess=baseline.default_trial,
            maximum_closure_condition_number=1.0e8,
        ),
        operating_limits=CVTShiftOperatingLimits(
            lower_stop_shift=0.0,
            engagement_shift=constants.deadzone_shift,
            upper_stop_shift=(
                constants.max_shift if upper_stop_shift is None else upper_stop_shift
            ),
        ),
    )


def _deadzone_launch() -> tuple[CVTOperatingHybridSystem, CVTDynamicState, float]:
    constants = BajaTrialConstants(primary_spring_initial_compression=0.020)
    baseline = build_baja_trial_baseline(constants)
    return _build_system(constants), baseline.deadzone_state, 0.040


def _lower_stop_release() -> tuple[CVTOperatingHybridSystem, CVTDynamicState, float]:
    constants = BajaTrialConstants(primary_spring_initial_compression=0.100)
    baseline = build_baja_trial_baseline(constants)
    return _build_system(constants), baseline.deadzone_state, 0.040


def _backshift_disengage_reengage() -> (
    tuple[CVTOperatingHybridSystem, CVTDynamicState, float]
):
    constants = BajaTrialConstants(primary_spring_initial_compression=0.100)
    baseline = build_baja_trial_baseline(constants)
    return _build_system(constants), baseline.active_shift_state, 0.040


def _upper_stop_hold() -> tuple[CVTOperatingHybridSystem, CVTDynamicState, float]:
    # This is the validated trim used by the upper-stop preview.  The stop is
    # intentionally near the active operating point so the scenario exercises
    # arrival, inelastic projection, and held constrained closure in one run.
    constants = BajaTrialConstants(primary_spring_initial_compression=0.021790)
    baseline = build_baja_trial_baseline(constants)
    state = baseline.active_shift_state
    upper_stop = state.shift_position + 0.20e-3
    if upper_stop >= constants.max_shift:
        raise RuntimeError("Temporary upper stop lies outside geometry travel.")
    return _build_system(constants, upper_stop_shift=upper_stop), state, 0.250


def _one_second_evolving_shafts() -> (
    tuple[CVTOperatingHybridSystem, CVTDynamicState, float]
):
    # Same physically coupled model as every other case.  This is not a fixed-
    # ratio fake: shaft speeds, belt speed, and shift coordinate are all free
    # to evolve and any resulting regime changes are checked.
    constants = BajaTrialConstants(primary_spring_initial_compression=0.029872)
    baseline = build_baja_trial_baseline(constants)
    return _build_system(constants), baseline.active_shift_state, 1.000


def _scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario(
            name="launch",
            description="Deadzone launch through primary engagement into an engaged contact branch.",
            build=_deadzone_launch,
            required_transition_fragments=("primary_closed_into_engaged_contact",),
        ),
        Scenario(
            name="lower_stop",
            description="Deadzone opening into the lower stop, followed by unilateral release.",
            build=_lower_stop_release,
            required_transition_fragments=(
                "deadzone_lower_stop_reached",
                "lower_stop_released",
            ),
        ),
        Scenario(
            name="backshift",
            description="Engaged backshift through disengagement, belt-secondary capture, and re-engagement.",
            build=_backshift_disengage_reengage,
            required_transition_fragments=(
                "primary_opened_through_disengagement_boundary",
                "primary_closed_into_engaged_contact",
            ),
        ),
        Scenario(
            name="upper_stop",
            description="Engaged free travel into a nearby upper stop and constrained hold.",
            build=_upper_stop_hold,
            required_transition_fragments=("upper_stop_reached",),
        ),
        Scenario(
            name="one_second",
            description="Longer coupled transient to inspect evolving shaft speeds and contact transitions.",
            build=_one_second_evolving_shafts,
            required_transition_fragments=(),
            max_step=1.0e-3,
        ),
    )


def _parse_args() -> argparse.Namespace:
    choices = tuple(scenario.name for scenario in _scenarios())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("core",) + choices,
        default="core",
        help="Scenario to run (default: core transition suite).",
    )
    parser.add_argument(
        "--max-samples-per-segment",
        type=int,
        default=72,
        help="Accepted solver samples to check per segment (default: 72).",
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=None,
        help="Optional directory for one compact trajectory plot per scenario.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open plots after checks complete.",
    )
    return parser.parse_args()


def _run_scenario(
    scenario: Scenario,
    *,
    max_samples_per_segment: int,
    save_dir: Path | None,
    show: bool,
) -> bool:
    system, initial_state, duration = scenario.build()
    result = system.integrate(
        time_span=(0.0, duration),
        initial_state=initial_state,
        settings=HybridIntegratorSettings(
            relative_tolerance=1.0e-7,
            absolute_tolerance=1.0e-9,
            max_step=scenario.max_step,
            maximum_transitions=100,
        ),
    )
    report = check_cvt_hybrid_result(
        system=system,
        result=result,
        settings=CVTSystemCheckSettings(
            maximum_samples_per_segment=max_samples_per_segment,
        ),
    )

    print(f"\n{scenario.name}: {scenario.description}")
    print("=" * 100)
    print(
        f"completed={result.completed}, reason={result.termination_reason}, "
        f"segments={len(result.segments)}, final_t={result.final_time:.6f} s"
    )
    for segment_index, segment in enumerate(result.segments, start=1):
        contact = (
            "none"
            if segment.mode.contact_regime is None
            else segment.mode.contact_regime.mode.value
        )
        print(
            f"  {segment_index:>2}: {segment.mode.engagement.value}/"
            f"{segment.mode.shift_constraint.value}/{contact} | "
            f"[{segment.start_time:.6f}, {segment.end_time:.6f}] s | "
            f"events={segment.fired_event_names or ('none',)}"
        )
    for record in result.transitions:
        print(f"  transition @ {record.time:.6f} s: " f"{record.transition.reason}")
    for line in report.summary_lines():
        print(f"  {line}")

    reasons = tuple(record.transition.reason for record in result.transitions)
    missing = tuple(
        fragment
        for fragment in scenario.required_transition_fragments
        if not any(fragment in reason for reason in reasons)
    )
    if missing:
        print(f"  required transition coverage: FAIL; missing={missing}")
        return False
    print("  required transition coverage: PASS")

    if save_dir is not None or show:
        figure = _plot_trajectory(name=scenario.name, result=result)
        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)
            output = save_dir / f"{scenario.name}.png"
            figure.savefig(output, dpi=160, bbox_inches="tight")
            print(f"  saved plot: {output}")
        if show:
            plt.show()
        plt.close(figure)

    if not report.passed:
        for failure in report.failures:
            print(f"  violation: {failure.format()}")
        return False
    return True


def _plot_trajectory(*, name: str, result) -> plt.Figure:
    time = result.concatenated_time()
    state = result.concatenated_state()
    figure, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(time, state[0] * 60.0 / (2.0 * np.pi), label="primary")
    axes[0].plot(time, state[1] * 60.0 / (2.0 * np.pi), label="secondary")
    axes[0].set_ylabel("shaft speed [rpm]")
    axes[0].legend()
    axes[1].plot(time, state[3] * 1e3, label="s")
    axes[1].plot(time, state[4] * 1e3, label="s_dot")
    axes[1].set_ylabel("shift [mm, mm/s]")
    axes[1].legend()
    axes[2].plot(time, state[2], label="belt speed")
    axes[2].set_ylabel("belt speed [m/s]")
    axes[2].set_xlabel("time [s]")
    axes[2].legend()
    for record in result.transitions:
        for axis in axes:
            axis.axvline(record.time, linestyle="--", linewidth=0.8)
    figure.suptitle(f"CVT hybrid system check: {name}")
    figure.tight_layout()
    return figure


def main() -> None:
    args = _parse_args()
    scenarios = _scenarios()
    selected = (
        scenarios[:3]
        if args.scenario == "core"
        else tuple(scenario for scenario in scenarios if scenario.name == args.scenario)
    )
    passed = True
    for scenario in selected:
        passed = (
            _run_scenario(
                scenario,
                max_samples_per_segment=args.max_samples_per_segment,
                save_dir=args.save_dir,
                show=not args.no_show,
            )
            and passed
        )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
