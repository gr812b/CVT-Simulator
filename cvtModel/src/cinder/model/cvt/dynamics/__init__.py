"""State-frozen CVT mechanics, closure assembly, and branch-root solves."""

from cinder.model.cvt.closure import ClosureEquation

from .deadzone import (
    DeadzoneDynamicsEvaluator,
    DeadzoneEvaluation,
    DeadzoneSnapshot,
    LowerStopReaction,
    build_deadzone_snapshot,
    evaluate_deadzone_lower_stop,
)
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
from .shift_constraints import (
    EngagedShiftConstraint,
    LowRatioSeatReaction,
    UpperStopReaction,
    recover_low_ratio_seat_reaction,
    recover_upper_stop_reaction,
)
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
    "evaluate_deadzone_lower_stop",
    "build_deadzone_snapshot",
    "LowerStopReaction",
    "DeadzoneSnapshot",
    "DeadzoneEvaluation",
    "DeadzoneDynamicsEvaluator",
    "BothSlipResult",
    "ClosureEquation",
    "ClosureEquationResidual",
    "EngagedShiftConstraint",
    "EngagedContactClosure",
    "EngagedContactSolveResult",
    "EngagedContactSolveSettings",
    "EngagedContactTrial",
    "LambdaSearchBounds",
    "LowRatioSeatReaction",
    "UpperStopReaction",
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
    "recover_low_ratio_seat_reaction",
    "recover_upper_stop_reaction",
    "solve_primary_slip_secondary_stick",
    "solve_primary_stick_secondary_slip",
    "solve_stick_stick",
]
