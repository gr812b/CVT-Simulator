"""Exercise reduced deadzone/free and deadzone/lower-stop mechanics.

This diagnostic intentionally does not run the full operating hybrid system;
that wiring is the next patch. It verifies the two independently derived
neutral RHS cases first:

    deadzone/free,
    deadzone/lower stop.

Run from the repository root:

    python tools/preview_deadzone_dynamics.py
"""

from __future__ import annotations

from dataclasses import replace
from math import isclose

from scipy.integrate import solve_ivp
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import build_baja_trial_baseline  # noqa: E402
from cinder.dynamics import DeadzoneDynamicsEvaluator  # noqa: E402
from cinder.integration import apply_perfectly_inelastic_lower_stop_impact  # noqa: E402
from cinder.integration.cvt_regime_events import (
    build_lower_stop_release_event,
)  # noqa: E402
from cinder.integration.cvt_operating_limits import (
    CVTShiftOperatingLimits,
)  # noqa: E402


def main() -> None:
    baseline = build_baja_trial_baseline()
    model = baseline.model
    limits = CVTShiftOperatingLimits(
        lower_stop_shift=0.0,
        engagement_shift=model.geometry.spec.deadzone_shift,
        upper_stop_shift=model.geometry.spec.max_shift,
    )
    evaluator = DeadzoneDynamicsEvaluator(model=model)

    free = evaluator.evaluate_free(state=baseline.deadzone_state)
    derivative = free.state_derivative
    print("Deadzone dynamics diagnostic")
    print("=" * 88)
    print(f"state shift: {free.state.shift_position * 1e3:.4f} mm")
    print(f"locked r_s: {free.snapshot.belt_secondary_lock_radius * 1e3:.4f} mm")
    print(f"primary normal: {free.primary_normal_resultant:.3f} N")
    print(f"primary torque: {free.primary_transmitted_torque:.3f} N m")
    print(f"v_b - r_s omega_s: {free.belt_secondary_speed_residual:+.3e} m/s")
    print(
        f"v_b_dot - r_s alpha_s: {free.belt_secondary_acceleration_residual:+.3e} m/s^2"
    )
    print(f"alpha_p: {derivative.primary_angular_acceleration:+.6f} rad/s^2")
    print(f"alpha_s: {derivative.secondary_angular_acceleration:+.6f} rad/s^2")
    print(f"s_ddot: {derivative.shift_acceleration:+.6f} m/s^2")

    # Primary rotation and primary axial motion must not depend on secondary
    # speed/load under the reduced neutral assumptions.
    changed_secondary = replace(
        baseline.deadzone_state,
        secondary_angular_speed=(
            baseline.deadzone_state.secondary_angular_speed + 40.0
        ),
        belt_speed=(
            free.snapshot.belt_secondary_lock_radius
            * (baseline.deadzone_state.secondary_angular_speed + 40.0)
        ),
    )
    changed = evaluator.evaluate_free(state=changed_secondary)
    assert isclose(
        changed.state_derivative.primary_angular_acceleration,
        derivative.primary_angular_acceleration,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert isclose(
        changed.state_derivative.shift_acceleration,
        derivative.shift_acceleration,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )

    # Direct reduced-RHS integration: with an initially locked belt/secondary
    # state, both the speed and acceleration lock must remain invariant.
    solution = solve_ivp(
        fun=lambda _time, vector: evaluator.evaluate_free(
            state=type(baseline.deadzone_state).from_vector(vector)
        ).state_derivative.as_vector(),
        t_span=(0.0, 1.0e-3),
        y0=baseline.deadzone_state.as_vector(),
        rtol=1.0e-10,
        atol=1.0e-12,
        max_step=1.0e-5,
    )
    assert solution.success
    final_state = type(baseline.deadzone_state).from_vector(solution.y[:, -1])
    final_snapshot = evaluator.snapshot(state=final_state)
    assert abs(final_snapshot.belt_secondary_speed_residual) < 1.0e-10

    arrived = apply_perfectly_inelastic_lower_stop_impact(
        state=replace(baseline.deadzone_state, shift_speed=-0.02),
        lower_stop_shift=limits.lower_stop_shift,
    )
    held = evaluator.evaluate_lower_stop(
        state=arrived,
        lower_stop_shift=limits.lower_stop_shift,
    )
    assert held.lower_stop_reaction is not None
    assert isclose(held.state_derivative.shift_position_rate, 0.0, abs_tol=0.0)
    assert isclose(held.state_derivative.shift_acceleration, 0.0, abs_tol=0.0)
    assert abs(held.belt_secondary_acceleration_residual) < 1.0e-12

    # At sufficiently high primary speed the free tendency closes, so the
    # lower-stop reaction becomes negative and the stop must release.
    releasing_state = replace(arrived, primary_angular_speed=400.0)
    releasing = evaluator.evaluate_lower_stop(
        state=releasing_state,
        lower_stop_shift=limits.lower_stop_shift,
    )
    assert releasing.lower_stop_reaction is not None
    assert releasing.lower_stop_reaction.closing_direction_magnitude < 0.0
    release_event = build_lower_stop_release_event(
        closing_reaction=lambda _time, vector: evaluator.evaluate_lower_stop(
            state=type(arrived).from_vector(vector),
            lower_stop_shift=limits.lower_stop_shift,
        ).stop_reaction,
    )
    assert release_event.direction == -1.0
    assert release_event.function(0.0, releasing_state.as_vector()) < 0.0

    print("\nLower-stop diagnostic")
    print(
        f"impact state: s={arrived.shift_position * 1e3:.4f} mm, s_dot={arrived.shift_speed * 1e3:.4f} mm/s"
    )
    print(
        "R_low (closing positive): "
        f"{held.lower_stop_reaction.closing_direction_magnitude:+.6f} N"
    )
    print(
        f"lower stop admissible: {held.lower_stop_reaction.is_unilaterally_admissible}"
    )
    print(
        "release check at omega_p=400 rad/s: "
        f"R_low={releasing.lower_stop_reaction.closing_direction_magnitude:+.6f} N"
    )
    print(
        "checks: belt-secondary speed/acceleration lock, direct free integration, "
        "primary decoupling, lower-stop constraint, and release indicator passed"
    )


if __name__ == "__main__":
    main()
