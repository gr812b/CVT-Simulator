"""CINDER-specific composition of the six instantaneous closure equations."""

from __future__ import annotations

from cinder.closure import ClosureEquation

from .equation_context import TrialEquationContext
from .state_fixed_equations import StateFixedEquationBlock
from .trial_system import TrialSixBySixSystem
from .rows.shift import build_shift_equation
from .rows.wrap_endpoint import build_wrap_endpoint_equation


def build_six_equations(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> tuple[ClosureEquation, ...]:
    """Return the six equations in the same order as the derivation.

    Row order:

    1. global shift dynamics;
    2. primary rotational dynamics;
    3. belt transport;
    4. secondary rotational dynamics;
    5. global tangential wrap compatibility;
    6. closed-loop wrap endpoint compatibility.
    """

    return (
        build_shift_equation(context=trial_context),
        fixed_equations.primary_rotation,
        fixed_equations.belt_transport,
        fixed_equations.secondary_rotation,
        fixed_equations.global_tangent_wrap,
        build_wrap_endpoint_equation(context=trial_context),
    )


def build_trial_six_by_six_system(
    *,
    fixed_equations: StateFixedEquationBlock,
    trial_context: TrialEquationContext,
) -> TrialSixBySixSystem:
    """Build one generic solver-ready six-by-six system for a lambda trial."""

    return TrialSixBySixSystem.from_equations(
        build_six_equations(
            fixed_equations=fixed_equations,
            trial_context=trial_context,
        )
    )
