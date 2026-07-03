"""State-frozen CVT mechanics, closure assembly, and branch-root solves."""

from cinder.closure import ClosureEquation

from .engaged_contact import (
    BothSlipResult,
    EngagedContactClosure,
    EngagedContactSolveResult,
    EngagedContactSolveSettings,
    EngagedContactTrial,
    LambdaSearchBounds,
    StickResidualContinuation,
    evaluate_both_slip,
    solve_primary_slip_secondary_stick,
    solve_primary_stick_secondary_slip,
    solve_stick_stick,
)
from .equation_context import TrialContactTerms, TrialEquationContext
from .equations import build_closure_equations, build_trial_closure_system
from .result import ClosureEquationResidual, TrialClosureResult
from .snapshot import CVTDynamicsModel, DynamicsSnapshot
from .state_fixed_equations import (
    StateFixedEquationBlock,
    build_state_fixed_equations,
)
from .trial_system import (
    TrialClosureConditionError,
    TrialClosureSolveError,
    TrialClosureSystem,
)

__all__ = [
    "BothSlipResult",
    "ClosureEquation",
    "ClosureEquationResidual",
    "CVTDynamicsModel",
    "DynamicsSnapshot",
    "EngagedContactClosure",
    "EngagedContactSolveResult",
    "EngagedContactSolveSettings",
    "EngagedContactTrial",
    "LambdaSearchBounds",
    "StickResidualContinuation",
    "StateFixedEquationBlock",
    "TrialContactTerms",
    "TrialEquationContext",
    "TrialClosureConditionError",
    "TrialClosureResult",
    "TrialClosureSolveError",
    "TrialClosureSystem",
    "build_closure_equations",
    "build_state_fixed_equations",
    "build_trial_closure_system",
    "evaluate_both_slip",
    "solve_primary_slip_secondary_stick",
    "solve_primary_stick_secondary_slip",
    "solve_stick_stick",
]
