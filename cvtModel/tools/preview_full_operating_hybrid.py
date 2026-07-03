"""Preview the wired deadzone, lower stop, and engagement transitions.

This is a hybrid-regression diagnostic rather than a calibrated vehicle run.
It exercises the physical graph now implemented by ``CVTOperatingHybridSystem``:

    deadzone/free -> engaged/free,
    deadzone/free -> deadzone/lower stop -> deadzone/free,
    engaged/free -> deadzone/free (with belt-secondary capture).

Run from the repository root:

    python tools/preview_full_operating_hybrid.py
"""

from __future__ import annotations

from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialConstants, build_baja_trial_baseline  # noqa: E402
from cinder.contact import ContactTractionLaw  # noqa: E402
from cinder.dynamics import EngagedContactSolveSettings, LambdaSearchBounds  # noqa: E402
from cinder.integration import HybridIntegratorSettings  # noqa: E402
from cinder.integration.cvt_operating_hybrid import CVTOperatingHybridSystem  # noqa: E402
from cinder.integration.cvt_operating_limits import CVTShiftOperatingLimits  # noqa: E402


def build_system(constants: BajaTrialConstants) -> CVTOperatingHybridSystem:
    """Construct the common hybrid system used by each targeted scenario."""

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
            upper_stop_shift=constants.max_shift,
        ),
    )


def run_case(
    *,
    title: str,
    constants: BajaTrialConstants,
    state_name: str,
) -> None:
    """Integrate one short transition-focused diagnostic scenario."""

    baseline = build_baja_trial_baseline(constants)
    system = build_system(constants)
    state = getattr(baseline, state_name)
    result = system.integrate(
        time_span=(0.0, 0.040),
        initial_state=state,
        settings=HybridIntegratorSettings(
            relative_tolerance=1.0e-7,
            absolute_tolerance=1.0e-9,
            max_step=1.0e-4,
            maximum_transitions=60,
        ),
    )

    print(f"\n{title}")
    print("=" * 88)
    print(
        f"completed={result.completed}, reason={result.termination_reason}, "
        f"segments={len(result.segments)}, final_t={result.final_time:.6f} s"
    )
    for record in result.transitions:
        previous = record.previous_mode
        successor = record.transition.next_mode
        print(
            f"t={record.time:.6f} s | "
            f"{previous.engagement.value}/{previous.shift_constraint.value} | "
            f"events={record.fired_event_names} | "
            f"{record.transition.reason} -> {successor}"
        )
        if record.transition.metadata:
            print(f"  metadata={record.transition.metadata}")


def main() -> None:
    # A closing primary below engagement enters the engaged contact model.  The
    # entry classifier correctly limits launch to the primary-slip/secondary-
    # stick or stick-stick candidates because the deadzone lock gives v_rel,s=0.
    run_case(
        title="Deadzone launch into engaged contact",
        constants=BajaTrialConstants(primary_spring_initial_compression=0.020),
        state_name="deadzone_state",
    )

    # This spring-dominated case opens into the physical lower stop, holds with
    # R_low > 0, then releases once centrifugal actuation reverses the free
    # primary tendency.  The lower stop is not a state clamp.
    run_case(
        title="Deadzone lower-stop hold and release",
        constants=BajaTrialConstants(primary_spring_initial_compression=0.100),
        state_name="deadzone_state",
    )

    # The engaged model backshifts through the physical disengagement boundary.
    # The transition applies the explicit belt-secondary capture map and
    # continues with deadzone dynamics rather than terminating at s=s_engage.
    run_case(
        title="Engaged backshift into deadzone",
        constants=BajaTrialConstants(primary_spring_initial_compression=0.100),
        state_name="active_shift_state",
    )


if __name__ == "__main__":
    main()
