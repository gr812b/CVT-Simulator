"""Bounded outer solve and integration-facing result for engaged stick--stick contact.

For one state-frozen :class:`DynamicsSnapshot`, rows 2--5 are assembled once.
A trial pair ``(lambda_p, lambda_s)`` rebuilds only rows 1 and 6, solves the
six-by-six affine system, and evaluates the shared acceleration-level contact
residuals.  The outer solver drives both residuals to zero.

``scipy.optimize.least_squares(method="trf")`` is used deliberately even
though this is a square two-residual/two-variable problem:

* lambda values must remain inside a static-utilization box;
* the present wrap equations are singular at lambda = 0, so an unconstrained
  Newton/root method must not cross that boundary;
* when no stick root exists, bounded least squares returns the best admissible
  trial for later branch selection instead of failing obscurely.

# Central differences evaluate the residual at small positive and negative
# lambda perturbations. This costs a few extra tiny 6x6 solves per iteration,
# but gives a less biased local Jacobian estimate across the narrow stick
# residual corridor.
jac="3-point",
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from cinder.contact import (
    ContactKinematicTolerances,
    ContactRelativeMotion,
    evaluate_contact_relative_motion,
)

from .equation_context import TrialEquationContext
from .equations import build_trial_six_by_six_system
from .result import TrialSixBySixResult
from .snapshot import DynamicsSnapshot
from .state import CVTDynamicStateDerivative, TrialFrictionUtilization
from .state_fixed_equations import (
    StateFixedEquationBlock,
    build_state_fixed_equations,
)

_DEFAULT_OPTIMIZER_TOLERANCE: Final[float] = 1.0e-12
_DEFAULT_MAXIMUM_FUNCTION_EVALUATIONS: Final[int] = 100
_BOUND_ACTIVITY_ABSOLUTE_TOLERANCE: Final[float] = 1.0e-10


@dataclass(frozen=True, slots=True)
class FrictionUtilizationBounds:
    """Strictly one-sided bounds for the two outer stick variables.

    Exact zero cannot lie in either interval while rows 1 and 6 contain
    explicit ``1 / lambda`` terms.  A positive box is the present forward-drive
    convention; a future reverse-drive branch can supply negative intervals
    without changing the solver implementation.
    """

    primary_lower: float
    primary_upper: float
    secondary_lower: float
    secondary_upper: float

    def __post_init__(self) -> None:
        _validate_one_sided_interval(
            name="primary lambda bounds",
            lower=self.primary_lower,
            upper=self.primary_upper,
        )
        _validate_one_sided_interval(
            name="secondary lambda bounds",
            lower=self.secondary_lower,
            upper=self.secondary_upper,
        )

    @classmethod
    def forward_drive(
        cls,
        *,
        primary_static_limit: float,
        secondary_static_limit: float,
        minimum_utilization: float = 1.0e-3,
    ) -> "FrictionUtilizationBounds":
        """Construct the current positive forward-drive static box.

        ``minimum_utilization`` is numerical only.  It keeps the solver away
        from the current zero-utilization singularity; it is not a physical
        lower friction limit and should be revisited with the lambda->0 limit.
        """

        _require_finite_positive(
            primary_static_limit=primary_static_limit,
            secondary_static_limit=secondary_static_limit,
            minimum_utilization=minimum_utilization,
        )
        return cls(
            primary_lower=minimum_utilization,
            primary_upper=primary_static_limit,
            secondary_lower=minimum_utilization,
            secondary_upper=secondary_static_limit,
        )

    @property
    def lower_vector(self) -> NDArray[np.float64]:
        return _immutable_array(
            np.array((self.primary_lower, self.secondary_lower), dtype=float)
        )

    @property
    def upper_vector(self) -> NDArray[np.float64]:
        return _immutable_array(
            np.array((self.primary_upper, self.secondary_upper), dtype=float)
        )

    def contains(self, utilization: TrialFrictionUtilization) -> bool:
        """Return whether a trial lies inside the inclusive static box."""

        return (
            self.primary_lower <= utilization.primary_lambda <= self.primary_upper
            and self.secondary_lower
            <= utilization.secondary_lambda
            <= self.secondary_upper
        )


@dataclass(frozen=True, slots=True)
class StickStickSolveSettings:
    """Numerical and kinematic policy for one engaged stick--stick solve.

    ``contact_tolerances`` belongs to shared contact logic because the same
    no-slip residual definitions are used by one-contact stick/slip branches.
    The remaining fields control only SciPy's numerical search.
    """

    bounds: FrictionUtilizationBounds
    initial_guess: TrialFrictionUtilization
    contact_tolerances: ContactKinematicTolerances = field(
        default_factory=ContactKinematicTolerances
    )
    optimizer_tolerance: float = _DEFAULT_OPTIMIZER_TOLERANCE
    maximum_function_evaluations: int = _DEFAULT_MAXIMUM_FUNCTION_EVALUATIONS
    maximum_six_by_six_condition_number: float | None = None

    def __post_init__(self) -> None:
        if not self.bounds.contains(self.initial_guess):
            raise ValueError("initial_guess must lie inside the supplied lambda bounds.")
        if not isinstance(self.contact_tolerances, ContactKinematicTolerances):
            raise TypeError(
                "contact_tolerances must be a ContactKinematicTolerances instance."
            )
        _require_finite_positive(optimizer_tolerance=self.optimizer_tolerance)
        if self.maximum_function_evaluations < 1:
            raise ValueError("maximum_function_evaluations must be at least one.")
        if self.maximum_six_by_six_condition_number is not None:
            _require_finite_positive(
                maximum_six_by_six_condition_number=(
                    self.maximum_six_by_six_condition_number
                ),
            )

    @property
    def initial_guess_tuple(self) -> tuple[float, float]:
        """Return the outer-variable seed in primary, secondary order."""

        return (
            self.initial_guess.primary_lambda,
            self.initial_guess.secondary_lambda,
        )


@dataclass(frozen=True, slots=True)
class StickStickTrial:
    """One six-by-six trial and its shared contact-relative-motion result."""

    friction_utilization: TrialFrictionUtilization
    six_by_six: TrialSixBySixResult
    contact_relative_motion: ContactRelativeMotion

    @property
    def no_slip_residuals(self) -> ContactRelativeMotion:
        """Compatibility alias for callers focused on stick residuals only."""

        return self.contact_relative_motion


@dataclass(frozen=True, slots=True)
class StickStickSolveResult:
    """Auditable outcome of the bounded outer stick--stick solve.

    ``accepted`` means a numerically converged result whose shared
    acceleration-level contact residual norm is below
    ``settings.contact_tolerances.stick_acceleration_norm_tolerance``.  It
    does *not* decide later transition hysteresis at a traction boundary;
    active bounds remain explicit for the future regime selector.
    """

    trial: StickStickTrial
    settings: StickStickSolveSettings
    optimizer_success: bool
    optimizer_status: int
    optimizer_message: str
    function_evaluations: int
    optimizer_cost: float
    jacobian: NDArray[np.float64]
    jacobian_determinant: float
    jacobian_condition_number: float
    active_lower_bounds: tuple[bool, bool]
    active_upper_bounds: tuple[bool, bool]
    accepted: bool

    def __post_init__(self) -> None:
        if self.function_evaluations < 0:
            raise ValueError("function_evaluations must be non-negative.")
        _require_finite(
            optimizer_cost=self.optimizer_cost,
            jacobian_determinant=self.jacobian_determinant,
        )
        if self.optimizer_cost < 0.0:
            raise ValueError("optimizer_cost must be non-negative.")
        if (
            not isfinite(self.jacobian_condition_number)
            and self.jacobian_condition_number != float("inf")
        ) or self.jacobian_condition_number < 0.0:
            raise ValueError(
                "jacobian_condition_number must be non-negative and finite or infinity."
            )
        _validate_matrix(self.jacobian, name="jacobian", expected_shape=(2, 2))
        object.__setattr__(self, "jacobian", _immutable_array(self.jacobian))

    @property
    def friction_utilization(self) -> TrialFrictionUtilization:
        return self.trial.friction_utilization

    @property
    def six_by_six(self) -> TrialSixBySixResult:
        return self.trial.six_by_six

    @property
    def contact_relative_motion(self) -> ContactRelativeMotion:
        return self.trial.contact_relative_motion

    @property
    def no_slip_residuals(self) -> ContactRelativeMotion:
        """Compatibility alias for the shared contact-relative-motion result."""

        return self.contact_relative_motion


@dataclass(frozen=True, slots=True)
class EngagedStickStickEvaluation:
    """Branch-ready evaluation of the engaged stick--stick candidate.

    ``state_derivative`` is populated only when stick is accepted.  A rejected
    evaluation still returns the best bounded trial and relative-motion data,
    which the future regime selector will use to choose one-contact or
    two-contact slip.  Deadzone/disengaged handling is intentionally outside
    this type: it is a separate fifth regime and must not call this engaged
    contact closure.
    """

    snapshot: DynamicsSnapshot
    stick_solution: StickStickSolveResult
    state_derivative: CVTDynamicStateDerivative | None

    @property
    def accepted(self) -> bool:
        return self.stick_solution.accepted

    @property
    def contact_relative_motion(self) -> ContactRelativeMotion:
        return self.stick_solution.contact_relative_motion


@dataclass(frozen=True, slots=True)
class StickStickClosure:
    """State-frozen outer stick closure with rows 2--5 cached once."""

    snapshot: DynamicsSnapshot
    fixed_equations: StateFixedEquationBlock = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, DynamicsSnapshot):
            raise TypeError("snapshot must be a DynamicsSnapshot instance.")
        object.__setattr__(
            self,
            "fixed_equations",
            build_state_fixed_equations(snapshot=self.snapshot),
        )

    def evaluate_trial(
        self,
        *,
        friction_utilization: TrialFrictionUtilization,
        maximum_six_by_six_condition_number: float | None = None,
    ) -> StickStickTrial:
        """Solve one fixed-lambda system and evaluate shared contact kinematics."""

        context = TrialEquationContext(
            snapshot=self.snapshot,
            friction_utilization=friction_utilization,
        )
        six_by_six = build_trial_six_by_six_system(
            fixed_equations=self.fixed_equations,
            trial_context=context,
        ).solve(
            maximum_condition_number=maximum_six_by_six_condition_number,
        )
        return StickStickTrial(
            friction_utilization=friction_utilization,
            six_by_six=six_by_six,
            contact_relative_motion=evaluate_contact_relative_motion(
                state=self.snapshot.state,
                geometry=self.snapshot.geometry,
                unknowns=six_by_six.unknowns,
            ),
        )

    def solve(self, *, settings: StickStickSolveSettings) -> StickStickSolveResult:
        """Find the bounded lambda pair that makes both contacts stick."""

        if not isinstance(settings, StickStickSolveSettings):
            raise TypeError("settings must be a StickStickSolveSettings instance.")

        def residual_vector(lambdas: NDArray[np.float64]) -> NDArray[np.float64]:
            trial = self.evaluate_trial(
                friction_utilization=TrialFrictionUtilization(
                    primary_lambda=float(lambdas[0]),
                    secondary_lambda=float(lambdas[1]),
                ),
                maximum_six_by_six_condition_number=(
                    settings.maximum_six_by_six_condition_number
                ),
            )
            return trial.contact_relative_motion.acceleration_vector

        # Trust-region reflective least-squares is deliberate: it cannot leave
        # the one-sided static box or cross lambda = 0. Unlike an unconstrained
        # root method, it also yields the best bounded non-stick candidate for
        # the later slip-branch decision.
        optimized = least_squares(
            residual_vector,
            x0=np.asarray(settings.initial_guess_tuple, dtype=float),
            bounds=(settings.bounds.lower_vector, settings.bounds.upper_vector),
            method="trf",
            jac="3-point",
            x_scale="jac",
            ftol=settings.optimizer_tolerance,
            xtol=settings.optimizer_tolerance,
            gtol=settings.optimizer_tolerance,
            max_nfev=settings.maximum_function_evaluations,
        )

        utilization = TrialFrictionUtilization(
            primary_lambda=float(optimized.x[0]),
            secondary_lambda=float(optimized.x[1]),
        )
        trial = self.evaluate_trial(
            friction_utilization=utilization,
            maximum_six_by_six_condition_number=(
                settings.maximum_six_by_six_condition_number
            ),
        )
        jacobian = np.asarray(optimized.jac, dtype=float)
        _validate_matrix(jacobian, name="optimizer jacobian", expected_shape=(2, 2))

        active_lower_bounds, active_upper_bounds = _active_bounds(
            utilization=utilization,
            bounds=settings.bounds,
        )
        accepted = (
            bool(optimized.success)
            and trial.contact_relative_motion.is_stick_compatible(
                tolerances=settings.contact_tolerances
            )
            and settings.bounds.contains(utilization)
        )

        return StickStickSolveResult(
            trial=trial,
            settings=settings,
            optimizer_success=bool(optimized.success),
            optimizer_status=int(optimized.status),
            optimizer_message=str(optimized.message).replace("\n", " "),
            function_evaluations=int(optimized.nfev),
            optimizer_cost=float(optimized.cost),
            jacobian=jacobian,
            jacobian_determinant=float(np.linalg.det(jacobian)),
            jacobian_condition_number=float(np.linalg.cond(jacobian)),
            active_lower_bounds=active_lower_bounds,
            active_upper_bounds=active_upper_bounds,
            accepted=accepted,
        )


def solve_stick_stick(
    *,
    snapshot: DynamicsSnapshot,
    settings: StickStickSolveSettings,
) -> StickStickSolveResult:
    """Solve one state-frozen engaged stick--stick contact candidate."""

    return StickStickClosure(snapshot=snapshot).solve(settings=settings)


def evaluate_engaged_stick_stick(
    *,
    snapshot: DynamicsSnapshot,
    settings: StickStickSolveSettings,
) -> EngagedStickStickEvaluation:
    """Return the actual ODE derivative when the engaged stick closure holds.

    This is the integration-facing use of the outer root solve.  The future
    top-level RHS should call it only after selecting an engaged-contact regime:

    * accepted -> use ``state_derivative`` directly;
    * rejected -> pass ``stick_solution`` and ``contact_relative_motion`` to
      the later slip selector/branch builder;
    * deadzone -> never call this function; use the separate disengaged branch.
    """

    solution = solve_stick_stick(snapshot=snapshot, settings=settings)
    derivative = None
    if solution.accepted:
        derivative = CVTDynamicStateDerivative.from_engaged_closure(
            state=snapshot.state,
            unknowns=solution.six_by_six.unknowns,
        )
    return EngagedStickStickEvaluation(
        snapshot=snapshot,
        stick_solution=solution,
        state_derivative=derivative,
    )


def _active_bounds(
    *,
    utilization: TrialFrictionUtilization,
    bounds: FrictionUtilizationBounds,
) -> tuple[tuple[bool, bool], tuple[bool, bool]]:
    scale = max(
        1.0,
        abs(bounds.primary_lower),
        abs(bounds.primary_upper),
        abs(bounds.secondary_lower),
        abs(bounds.secondary_upper),
    )
    tolerance = _BOUND_ACTIVITY_ABSOLUTE_TOLERANCE * scale
    lower = (
        abs(utilization.primary_lambda - bounds.primary_lower) <= tolerance,
        abs(utilization.secondary_lambda - bounds.secondary_lower) <= tolerance,
    )
    upper = (
        abs(utilization.primary_lambda - bounds.primary_upper) <= tolerance,
        abs(utilization.secondary_lambda - bounds.secondary_upper) <= tolerance,
    )
    return lower, upper


def _validate_one_sided_interval(*, name: str, lower: float, upper: float) -> None:
    _require_finite(lower=lower, upper=upper)
    if not lower < upper:
        raise ValueError(f"{name} must satisfy lower < upper.")
    if lower <= 0.0 <= upper:
        raise ValueError(
            f"{name} must remain strictly on one side of zero while the "
            "current closure rows contain 1/lambda terms."
        )


def _require_finite_positive(**values: float) -> None:
    _require_finite(**values)
    for name, value in values.items():
        if value <= 0.0:
            raise ValueError(f"{name} must be strictly positive.")


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")


def _validate_matrix(
    values: NDArray[np.float64] | np.ndarray,
    *,
    name: str,
    expected_shape: tuple[int, int],
) -> None:
    array = np.asarray(values, dtype=float)
    if array.shape != expected_shape:
        raise ValueError(f"{name} must have shape {expected_shape}, got {array.shape}.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")


def _immutable_array(values: NDArray[np.float64] | np.ndarray) -> NDArray[np.float64]:
    array = np.array(values, dtype=float, copy=True)
    array.setflags(write=False)
    return array
