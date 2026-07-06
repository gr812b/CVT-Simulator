"""CINDER-specific assembly of the normal-resultant 8x8 closure system."""

from __future__ import annotations

from cinder.model.cvt.closure import ClosureEquation

from .equation_context import TrialEquationContext
from .state_fixed_equations import StateFixedEquationBlock
from .trial_system import TrialClosureSystem
from .rows.primary_traction import build_primary_traction_equation
from .rows.secondary_traction import build_secondary_traction_equation
from .rows.tension_loop import build_tension_loop_equation


def build_closure_equations(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> tuple[ClosureEquation, ...]:
    """Return the eight equations in the canonical normal-resultant system.

    Unknown order is defined by :class:`cinder.model.cvt.closure.ClosureUnknown`:

        [alpha_p, alpha_s, v_b_dot, s_ddot,
         tau_p, tau_s, N_p, N_s].

    The first five rows are fully frozen by the ODE state and active
    shift constraint.  The fourth row is either the free primary axial balance
    or a fixed-shift kinematic constraint ``s_ddot = 0``. The last three are
    rebuilt for the current signed lambda trial:

        tau_p / r_tau,p - lambda_p N_p = 0,
        tau_s / r_tau,s - lambda_s N_s = 0,
        C_T(lambda_p, lambda_s) = 0.
    """

    return (
        *fixed_equations.as_tuple(),
        build_primary_traction_equation(context=trial_context),
        build_secondary_traction_equation(context=trial_context),
        build_tension_loop_equation(context=trial_context),
    )


def build_trial_closure_system(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> TrialClosureSystem:
    """Build one solver-ready 8x8 closure system for a lambda trial."""

    return TrialClosureSystem.from_equations(
        build_closure_equations(
            fixed_equations=fixed_equations,
            trial_context=trial_context,
        )
    )
