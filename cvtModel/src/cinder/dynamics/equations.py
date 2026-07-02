"""CINDER-specific assembly entry points for the instantaneous closure system."""

from __future__ import annotations

from cinder.closure import ClosureEquation

from .equation_context import TrialEquationContext
from .state_fixed_equations import StateFixedEquationBlock
from .trial_system import TrialClosureSystem
from .rows.shift import build_shift_equation
from .rows.wrap_endpoint import build_wrap_endpoint_equation


def build_closure_equations(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> tuple[ClosureEquation, ...]:
    """Return the currently implemented closure rows.

    This composition has deliberately not been padded or adapted after the
    canonical basis expanded to include the two wrap normal resultants. The
    normal-resultant rows and rebuilt contact/shift rows are the next physics
    patch. Until then, passing this incomplete tuple to
    :class:`TrialClosureSystem` correctly raises on the row-count mismatch
    instead of silently projecting the two new unknowns away.
    """

    return (
        build_shift_equation(context=trial_context),
        fixed_equations.primary_rotation,
        fixed_equations.belt_transport,
        fixed_equations.secondary_rotation,
        fixed_equations.global_tangent_wrap,
        build_wrap_endpoint_equation(context=trial_context),
    )


def build_trial_closure_system(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> TrialClosureSystem:
    """Build one generic solver-ready closure system for a lambda trial."""

    return TrialClosureSystem.from_equations(
        build_closure_equations(
            fixed_equations=fixed_equations,
            trial_context=trial_context,
        )
    )
