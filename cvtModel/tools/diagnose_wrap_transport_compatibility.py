"""Prove the held-ratio conflict between CINDER rows 3 and 5.

Run from ``cvtModel/`` after placing this file in ``tools/``::

    python tools/diagnose_wrap_transport_compatibility.py
    python tools/diagnose_wrap_transport_compatibility.py --strict

This is an investigation tool.  It does not modify CINDER.

Why this test exists
--------------------
For one wrapped belt contact, integrating the local tangential segment balance
is correct:

    tau_b / r - [T_out - T_in] = m_wrap_contact * a_t.

Summing the two wrapped contacts gives the present row-5 form only when the
net tension change through the two *straight* spans is zero.  That is true in
the quasi-static limit, but not for an accelerating belt with finite straight-
span mass.

CINDER currently also contains row 3, the full-belt transport equation:

    tau_p / r_p - tau_s / r_s = m_total * v_b_dot.

At held ratio (s_dot = 0), row 5 says the same left side equals only the
wrapped-arc mass times v_b_dot.  Because the total belt includes two straight
spans, m_total != m_wrap.  The pair therefore forces v_b_dot = 0 and net belt
traction = 0, independently of the rest of the mechanics.

The script proves that structural consequence directly from the assembled
matrix, then shows the missing straight-span tension jump required by a
closed-loop belt balance.

It intentionally reuses ``build_diagnostic_baseline`` from the current
``preview_engaged_contact_modes.py`` tool so every number uses the exact same
baseline as the slip diagnostics.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT, Path(__file__).resolve().parent):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

try:
    from preview_engaged_contact_modes import build_diagnostic_baseline
except ImportError as error:  # pragma: no cover - friendly runtime message
    raise SystemExit(
        "This diagnostic reuses build_diagnostic_baseline from "
        "tools/preview_engaged_contact_modes.py. Keep that file beside this "
        "one while the closure investigation is active."
    ) from error

from cinder.closure import ClosureUnknown
from cinder.dynamics import EngagedContactClosure, TrialFrictionUtilization


KINETIC_UTILIZATION = 0.51
DEFAULT_SLIP_SPEED_OFFSET = 0.20


def main() -> int:
    args = _parse_arguments()

    baseline = build_diagnostic_baseline()
    base_state = baseline.quasi_static_state
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)

    # Deliberately use a held-ratio state.  This strips away r_dot v_b terms
    # and lets rows 3 and 5 be compared without any modelling interpretation.
    # The small established relative speeds reproduce the earlier both-slip
    # diagnostic state, but the proof below does not depend on their value.
    state = replace(
        base_state,
        primary_angular_speed=(
            base_state.belt_speed + args.slip_speed_offset
        ) / geometry.primary.effective,
        secondary_angular_speed=(
            base_state.belt_speed - args.slip_speed_offset
        ) / geometry.secondary.effective,
    )
    if abs(state.shift_speed) > 1.0e-14:
        raise RuntimeError("This proof requires a held-ratio state with s_dot = 0.")

    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    trial = closure.evaluate_trial(
        friction_utilization=TrialFrictionUtilization(
            primary_lambda=args.kinetic_utilization,
            secondary_lambda=args.kinetic_utilization,
        )
    )

    result = trial.six_by_six
    names = result.system.equation_names
    transport_index = names.index("belt_transport")
    wrap_index = names.index("global_tangent_wrap")
    belt_column = int(ClosureUnknown.BELT_ACCELERATION)
    primary_torque_column = int(ClosureUnknown.PRIMARY_TORQUE)
    secondary_torque_column = int(ClosureUnknown.SECONDARY_TORQUE)

    transport_row = result.matrix[transport_index]
    wrap_row = result.matrix[wrap_index]
    transport_rhs = result.right_hand_side[transport_index]
    wrap_rhs = result.right_hand_side[wrap_index]

    m_total = float(transport_row[belt_column])
    m_wrap = float(wrap_row[belt_column])
    m_straight = m_total - m_wrap
    torque_coefficients_match = bool(
        np.allclose(
            transport_row[[primary_torque_column, secondary_torque_column]],
            wrap_row[[primary_torque_column, secondary_torque_column]],
            rtol=0.0,
            atol=1.0e-13,
        )
    )
    known_terms_zero = bool(
        abs(transport_rhs) <= 1.0e-13 and abs(wrap_rhs) <= 1.0e-13
    )

    unknowns = result.unknowns
    traction_difference = (
        unknowns.primary_torque / geometry.primary.effective
        - unknowns.secondary_torque / geometry.secondary.effective
    )
    transport_balance = m_total * unknowns.belt_acceleration - traction_difference
    wrap_balance = m_wrap * unknowns.belt_acceleration - traction_difference
    difference_balance = m_straight * unknowns.belt_acceleration

    print("\n" + "=" * 116)
    print("Held-ratio audit: row 3 full-belt transport versus row 5 wrapped-arc compatibility")
    print(
        "The state has s_dot = 0, so every r_dot v_b term in the handwritten wrap derivation is exactly zero."
    )
    print(
        "The established +/-0.2 m/s relative slips merely reproduce the earlier both-slip test; "
        "the row conflict below exists for any torques or lambdas."
    )

    print("\n1. Exact assembled rows")
    print("  Unknown order: [alpha_p, alpha_s, v_b_dot, s_ddot, tau_p, tau_s]")
    print(f"  row 3 belt transport:      {np.array2string(transport_row, precision=8, suppress_small=True)}")
    print(f"  row 5 wrapped compatibility:{np.array2string(wrap_row, precision=8, suppress_small=True)}")
    print(f"  row 3 RHS={transport_rhs:+.3e}; row 5 RHS={wrap_rhs:+.3e}")

    print("\n2. Their physical meaning at held ratio")
    print("  Define q = tau_p/r_p - tau_s/r_s, the net tangential force applied to the belt.")
    print(f"  row 3: q = m_total * v_b_dot,       m_total = {m_total:.9f} kg")
    print(f"  row 5: q = m_wrap  * v_b_dot,       m_wrap  = {m_wrap:.9f} kg")
    print(f"  difference: 0 = m_straight * v_b_dot, m_straight = {m_straight:.9f} kg")
    print(
        "  Here m_straight is the mass of the two straight spans: total belt mass minus the two wrapped arcs."
    )

    print("\n3. Consequence forced by the present two rows")
    print(
        f"  Because m_straight = {m_straight:.9f} kg is nonzero, the rows force:"
    )
    print("    v_b_dot = 0")
    print("    q       = 0")
    print("  This is not an observed feature of the test state. It is an algebraic consequence of rows 3 and 5 together.")
    print("\n  Actual direct both-slip trial")
    print(f"    v_b_dot = {unknowns.belt_acceleration:+.12e} m/s^2")
    print(f"    q       = {traction_difference:+.12e} N")
    print(f"    row-3 residual reconstruction = {transport_balance:+.3e} N")
    print(f"    row-5 residual reconstruction = {wrap_balance:+.3e} N")
    print(f"    row3 - row5 difference         = {difference_balance:+.3e} N")
    print(
        f"    solved torques: tau_p={unknowns.primary_torque:+.6f} N m, "
        f"tau_s={unknowns.secondary_torque:+.6f} N m"
    )

    print("\n4. What is missing from the handwritten wrap sum")
    print(
        "  The integrated contact equations give the sum of tension changes across the WRAPPED arcs:"
    )
    print("    Delta_T_wrap = q - m_wrap * v_b_dot")
    print(
        "  The two straight spans have no contact force, but their finite mass still requires a tension change:"
    )
    print("    Delta_T_straight = -m_straight * v_b_dot")
    print("  Closed-loop tension continuity requires Delta_T_wrap + Delta_T_straight = 0.")
    print("  Substituting gives q = m_total * v_b_dot, exactly row 3.")
    print(
        "  Current row 5 instead sets Delta_T_wrap = 0 by identifying the wrap endpoints through "
        "constant straight-span tensions. That silently removes Delta_T_straight."
    )

    print("\n5. Numerical counterexample: an arbitrarily accelerating belt")
    print("  For any imposed v_b_dot, a full closed-loop balance requires a nonzero span tension jump.")
    print("  v_b_dot [m/s^2] | q full belt [N] | Delta_T_wrap [N] | Delta_T_straight [N] | row-3 residual if row-5 used [N]")
    print("  " + "-" * 112)
    for belt_acceleration in (-10.0, -2.0, 2.0, 10.0):
        q_full = m_total * belt_acceleration
        delta_wrap = q_full - m_wrap * belt_acceleration
        delta_straight = -m_straight * belt_acceleration
        q_if_current_row5 = m_wrap * belt_acceleration
        transport_residual_if_row5 = m_total * belt_acceleration - q_if_current_row5
        print(
            f"  {belt_acceleration:+17.3f} | {q_full:+15.6f} | {delta_wrap:+17.6f} | "
            f"{delta_straight:+21.6f} | {transport_residual_if_row5:+29.6f}"
        )

    print("\n6. Matrix-rank counterfactual")
    corrected_mass_matrix = np.array(result.matrix, dtype=float, copy=True)
    corrected_mass_matrix[transport_index, belt_column] = m_wrap
    original_rank = int(np.linalg.matrix_rank(result.matrix))
    corrected_mass_rank = int(np.linalg.matrix_rank(corrected_mass_matrix))
    original_condition = float(np.linalg.cond(result.matrix))
    corrected_condition = float(np.linalg.cond(corrected_mass_matrix))
    print(
        "  Replace only row 3's belt-mass coefficient with m_wrap. At held ratio rows 3 and 5 then become identical."
    )
    print(f"  present matrix:                 rank={original_rank}, cond={original_condition:.3e}")
    print(f"  mass-matched counterfactual:    rank={corrected_mass_rank}, cond={corrected_condition:.3e}")
    print(
        "  The present full rank is obtained because the model gives two different inertial masses to the same "
        "net tangential-force balance. It is not independent physical closure information."
    )

    structural_failure = (
        torque_coefficients_match
        and known_terms_zero
        and m_straight > 1.0e-12
        and original_rank == 6
        and corrected_mass_rank < original_rank
    )

    print("\n" + "=" * 116)
    print("Conclusion")
    if structural_failure:
        print(
            "  PROVED for the current held-ratio formulation: row 5 is not a valid independent dynamic equation "
            "while row 3 carries the full belt mass. Together they artificially enforce v_b_dot=q=0."
        )
        print(
            "  This is enough to invalidate dynamic-slip use of the present six-row closure. It is a necessary fix."
        )
        print(
            "  It does not yet prove that this is the only source of the anti-dissipative torque signs: the endpoint "
            "row also identifies tensions across straight spans and must be revisited with the same span dynamics."
        )
    else:
        print(
            "  The expected held-ratio structural conflict was not reproduced. Inspect the printed rows before changing mechanics."
        )

    if args.strict and not structural_failure:
        return 1
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove the held-ratio row-3/row-5 belt-mass conflict before changing CINDER mechanics."
    )
    parser.add_argument(
        "--kinetic-utilization",
        type=float,
        default=KINETIC_UTILIZATION,
        help="Fixed lambda used only to instantiate the existing both-slip trial.",
    )
    parser.add_argument(
        "--slip-speed-offset",
        type=float,
        default=DEFAULT_SLIP_SPEED_OFFSET,
        help="Established relative speed used only to reproduce the earlier both-slip state [m/s].",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero only when the expected structural conflict is not reproduced.",
    )
    args = parser.parse_args()
    if not np.isfinite(args.kinetic_utilization) or args.kinetic_utilization == 0.0:
        parser.error("--kinetic-utilization must be finite and nonzero.")
    if not np.isfinite(args.slip_speed_offset):
        parser.error("--slip-speed-offset must be finite.")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
