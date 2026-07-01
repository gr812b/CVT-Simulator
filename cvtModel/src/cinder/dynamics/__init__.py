"""State, snapshots, contact closures, and six-by-six assembly for CINDER."""

from cinder.closure import ClosureEquation

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
from .stick_stick import (
    EngagedStickStickEvaluation,
    FrictionUtilizationBounds,
    StickStickClosure,
    StickStickSolveResult,
    StickStickSolveSettings,
    StickStickTrial,
    evaluate_engaged_stick_stick,
    solve_stick_stick,
)
from .trial_system import (
    TrialSixBySixConditionError,
    TrialSixBySixSolveError,
    TrialSixBySixSystem,
)

__all__ = [
    "ClosureEquation",
    "ClosureEquationResidual",
    "CVTDynamicState",
    "CVTDynamicStateDerivative",
    "CVTDynamicsModel",
    "DynamicsSnapshot",
    "EngagedStickStickEvaluation",
    "FrictionUtilizationBounds",
    "StateFixedEquationBlock",
    "StickStickClosure",
    "StickStickSolveResult",
    "StickStickSolveSettings",
    "StickStickTrial",
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
    "evaluate_engaged_stick_stick",
    "solve_stick_stick",
]
