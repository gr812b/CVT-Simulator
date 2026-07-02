"""CINDER-specific assembly of the normal-resultant 8x8 closure system."""

from __future__ import annotations

from cinder.closure import ClosureEquation

from .equation_context import TrialEquationContext
from .state_fixed_equations import StateFixedEquationBlock
from .trial_system import TrialClosureSystem
from .rows.primary_axial import build_primary_axial_equation
from .rows.secondary_axial import build_secondary_axial_equation
from .rows.tension_loop import build_tension_loop_equation
from .rows.primary_traction import build_primary_traction_equation
from .rows.secondary_traction import build_secondary_traction_equation


def build_closure_equations(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> tuple[ClosureEquation, ...]:
    """Return the eight equations in the canonical normal-resultant system.

    Unknown order is defined by :class:`cinder.closure.ClosureUnknown`:

        [alpha_p, alpha_s, v_b_dot, s_ddot,
         tau_p, tau_s, N_p, N_s].

    Rows:

    1. primary shaft rotation;
    2. whole-belt tangential momentum;
    3. secondary shaft rotation;
    4. primary physical axial balance;
    5. secondary physical axial balance mapped through ``x_s(s)``;
    6. primary integrated traction resultant;
    7. secondary integrated traction resultant;
    8. closed tension-loop compatibility.
    """

    return (
        fixed_equations.primary_rotation,
        fixed_equations.belt_transport,
        fixed_equations.secondary_rotation,
        build_primary_axial_equation(context=trial_context),
        build_secondary_axial_equation(context=trial_context),
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
