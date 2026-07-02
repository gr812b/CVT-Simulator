"""State, snapshots, engaged contact closure, and six-by-six assembly."""

from cinder.closure import ClosureEquation

from .engaged_contact import (
    BothSlipResult,
    EngagedContactClosure,
    EngagedContactSolveResult,
    EngagedContactSolveSettings,
    EngagedContactTrial,
    FrictionUtilizationBounds,
    evaluate_both_slip,
    solve_primary_slip_secondary_stick,
    solve_primary_stick_secondary_slip,
    solve_stick_stick,
)
from .equation_context import TrialContactTerms, TrialEquationContext
from .equations import build_six_equations, build_trial_six_by_six_system
from .result import ClosureEquationResidual, TrialSixBySixResult
from .snapshot import CVTDynamicsModel, DynamicsSnapshot
from .state import (
    CVTDynamicState,
    CVTDynamicStateDerivative,
    TrialFrictionUtilization,
)
from .state_fixed_equations import (
    StateFixedEquationBlock,
    build_state_fixed_equations,
)
from .trial_system import (
    TrialSixBySixConditionError,
    TrialSixBySixSolveError,
    TrialSixBySixSystem,
)

__all__ = [
    "BothSlipResult",
    "ClosureEquation",
    "ClosureEquationResidual",
    "CVTDynamicState",
    "CVTDynamicStateDerivative",
    "CVTDynamicsModel",
    "DynamicsSnapshot",
    "EngagedContactClosure",
    "EngagedContactSolveResult",
    "EngagedContactSolveSettings",
    "EngagedContactTrial",
    "FrictionUtilizationBounds",
    "StateFixedEquationBlock",
    "TrialContactTerms",
    "TrialEquationContext",
    "TrialFrictionUtilization",
    "TrialSixBySixConditionError",
    "TrialSixBySixResult",
    "TrialSixBySixSolveError",
    "TrialSixBySixSystem",
    "build_six_equations",
    "build_state_fixed_equations",
    "build_trial_six_by_six_system",
    "evaluate_both_slip",
    "solve_primary_slip_secondary_stick",
    "solve_primary_stick_secondary_slip",
    "solve_stick_stick",
]
