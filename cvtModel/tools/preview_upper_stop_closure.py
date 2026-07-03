"""Compare free engaged closure against high-ratio constrained closure.

This is a diagnostic, not the full regime dispatcher.  It solves the exact
same selected contact topology twice at ``s = s_upper``: once with free shift
and once with the upper-stop row replacing the primary axial row.  It prints
and plots the recovered unilateral stop reaction.
"""

from __future__ import annotations

from pathlib import Path
import sys
from math import isclose

# Support the common repository layouts where the shared Baja baseline lives
# either beside this script or at the repository root.
_repository_root = Path(__file__).resolve().parents[1]
if str(_repository_root) not in sys.path:
    sys.path.insert(0, str(_repository_root))

from baja_trial_baseline import build_baja_trial_baseline
from cinder.contact import ContactRegime, ContactTractionLaw
from cinder.dynamics import (
    EngagedContactClosure,
    EngagedContactSolveSettings,
    EngagedShiftConstraint,
    LambdaSearchBounds,
)
from cinder.integration import (
    CVTDynamicState,
    apply_perfectly_inelastic_upper_stop_impact,
)


def _solve(closure: EngagedContactClosure, settings: EngagedContactSolveSettings):
    return closure.solve_stick_stick(settings=settings)


def main() -> None:
    baseline = build_baja_trial_baseline()
    model = baseline.model
    upper = model.geometry.spec.max_shift
    geometry = model.geometry.evaluate(upper)
    # Chosen to make the high-ratio stop physically loaded for the current
    # provisional baseline. The diagnostic is about the constrained closure,
    # not a calibrated operating point.
    secondary_speed = 380.0
    belt_speed = geometry.secondary.effective * secondary_speed
    state = CVTDynamicState(
        primary_angular_speed=belt_speed / geometry.primary.effective,
        secondary_angular_speed=secondary_speed,
        belt_speed=belt_speed,
        shift_position=upper,
        shift_speed=0.0,
        secondary_shaft_angle=baseline.quasi_static_state.secondary_shaft_angle,
    )
    # Demonstrate the isolated future event reset as well.
    state = apply_perfectly_inelastic_upper_stop_impact(
        state=state,
        upper_stop_shift=upper,
    )
    snapshot = model.snapshot(state=state)
    settings = EngagedContactSolveSettings(
        lambda_search_bounds=LambdaSearchBounds.symmetric(
            primary_half_width=3.0,
            secondary_half_width=3.0,
        ),
        initial_guess=baseline.default_trial,
    )

    free = _solve(
        EngagedContactClosure(
            snapshot=snapshot,
            shift_constraint=EngagedShiftConstraint.FREE,
        ),
        settings,
    )
    stop = _solve(
        EngagedContactClosure(
            snapshot=snapshot,
            shift_constraint=EngagedShiftConstraint.UPPER_STOP,
        ),
        settings,
    )

    free_trial = free.trial
    stop_trial = stop.trial
    assert stop_trial.upper_stop_reaction is not None
    assert isclose(stop_trial.closure.unknowns.shift_acceleration, 0.0, abs_tol=1.0e-12)
    assert isclose(stop_trial.state_derivative.shift_position_rate, 0.0, abs_tol=0.0)
    assert isclose(stop_trial.state_derivative.shift_acceleration, 0.0, abs_tol=0.0)

    print("Upper-stop closure diagnostic")
    print(f"shift position: {upper * 1e3:.6f} mm")
    print(f"free s_ddot: {free_trial.closure.unknowns.shift_acceleration:.6f} m/s^2")
    print(f"stop s_ddot: {stop_trial.closure.unknowns.shift_acceleration:.6f} m/s^2")
    print(f"stop reaction (opening positive): {stop_trial.upper_stop_reaction:.6f} N")
    print(f"stop admissible: {stop_trial.upper_stop_reaction >= 0.0}")
    print(f"free lambdas:  {free.traction_utilization}")
    print(f"stop lambdas:  {stop.traction_utilization}")
    print(f"free torques:  {free_trial.closure.unknowns.primary_torque:.6f}, "
          f"{free_trial.closure.unknowns.secondary_torque:.6f} N m")
    print(f"stop torques:  {stop_trial.closure.unknowns.primary_torque:.6f}, "
          f"{stop_trial.closure.unknowns.secondary_torque:.6f} N m")


if __name__ == "__main__":
    main()
