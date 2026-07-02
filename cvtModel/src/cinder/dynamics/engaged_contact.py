"""Reusable engaged-contact closure for stick and kinetic-slip branches.

Every engaged branch uses the same closure mechanical trial system:

    snapshot + (lambda_p, lambda_s) -> A z = b -> relative contact motion.

Only the outer lambda policy changes:

* stick--stick: solve both lambdas so both acceleration residuals vanish;
* primary-slip/secondary-stick: fix primary lambda kinetically, solve the
  secondary lambda so the secondary residual vanishes;
* primary-stick/secondary-slip: mirror the above;
* both-slip: fix both lambdas kinetically and evaluate the closure once.

``EngagedContactClosure.solve_bounded_stick_residuals`` is intentionally the
single reusable nonlinear solver for both the two-dimensional stick--stick
case and the two one-dimensional mixed cases. It evaluates only the selected
sticking residuals, so no branch duplicates root-solver mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Final, Mapping

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from cinder.contact import (
    ContactInterface,
    ContactKinematicTolerances,
    ContactRelativeMotion,
    EngagedContactMode,
    KineticSlipSpecification,
    evaluate_contact_relative_motion,
)
from cinder.dynamics.equation_context import TrialEquationContext
from cinder.dynamics.equations import build_trial_closure_system
from cinder.dynamics.result import TrialClosureResult
from cinder.dynamics.snapshot import DynamicsSnapshot
from cinder.dynamics.state import (
    CVTDynamicStateDerivative,
    TrialFrictionUtilization,
)
from cinder.dynamics.state_fixed_equations import (
    StateFixedEquationBlock,
    build_state_fixed_equations,
)

_DEFAULT_OPTIMIZER_TOLERANCE: Final[float] = 1.0e-12
_DEFAULT_MAXIMUM_FUNCTION_EVALUATIONS: Final[int] = 100
_BOUND_ACTIVITY_ABSOLUTE_TOLERANCE: Final[float] = 1.0e-10


@dataclass(frozen=True, slots=True)
class FrictionUtilizationBounds:
    """One-sided static-utilization intervals for the two lambda variables.

    Each interval must remain entirely positive or entirely negative until the
    analytical lambda-to-zero limiting forms are implemented. The current
    ``forward_drive`` constructor creates the familiar positive static box.
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
        """Build the present positive static box away from lambda = 0."""

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

    def lower_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.primary_lower
        if interface is ContactInterface.SECONDARY:
            return self.secondary_lower
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def upper_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.primary_upper
        if interface is ContactInterface.SECONDARY:
            return self.secondary_upper
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def contains_at(self, interface: ContactInterface, value: float) -> bool:
        return self.lower_at(interface) <= value <= self.upper_at(interface)

    def contains(self, utilization: TrialFrictionUtilization) -> bool:
        return (
            self.contains_at(ContactInterface.PRIMARY, utilization.primary_lambda)
            and self.contains_at(ContactInterface.SECONDARY, utilization.secondary_lambda)
        )


@dataclass(frozen=True, slots=True)
class EngagedContactSolveSettings:
    """Numerical policy shared by the 2D and 1D sticking-lambda solves."""

    static_bounds: FrictionUtilizationBounds
    initial_guess: TrialFrictionUtilization
    contact_tolerances: ContactKinematicTolerances = field(
        default_factory=ContactKinematicTolerances
    )
    optimizer_tolerance: float = _DEFAULT_OPTIMIZER_TOLERANCE
    maximum_function_evaluations: int = _DEFAULT_MAXIMUM_FUNCTION_EVALUATIONS
    maximum_closure_condition_number: float | None = None

    def __post_init__(self) -> None:
        if not self.static_bounds.contains(self.initial_guess):
            raise ValueError("initial_guess must lie inside the static lambda box.")
        if not isinstance(self.contact_tolerances, ContactKinematicTolerances):
            raise TypeError(
                "contact_tolerances must be a ContactKinematicTolerances instance."
            )
        _require_finite_positive(optimizer_tolerance=self.optimizer_tolerance)
        if self.maximum_function_evaluations < 1:
            raise ValueError("maximum_function_evaluations must be at least one.")
        if self.maximum_closure_condition_number is not None:
            _require_finite_positive(
                maximum_closure_condition_number=(
                    self.maximum_closure_condition_number
                )
            )

    def initial_guess_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.initial_guess.primary_lambda
        if interface is ContactInterface.SECONDARY:
            return self.initial_guess.secondary_lambda
        raise ValueError(f"Unsupported contact interface: {interface!r}.")


@dataclass(frozen=True, slots=True)
class EngagedContactTrial:
    """One fixed-lambda closure solve plus shared contact kinematics."""

    friction_utilization: TrialFrictionUtilization
    closure: TrialClosureResult
    relative_motion: ContactRelativeMotion
    state_derivative: CVTDynamicStateDerivative


@dataclass(frozen=True, slots=True)
class EngagedContactSolveResult:
    """Outcome of the shared bounded 1D/2D sticking-residual solver."""

    mode: EngagedContactMode
    trial: EngagedContactTrial
    sticking_interfaces: tuple[ContactInterface, ...]
    fixed_slip_specifications: tuple[KineticSlipSpecification, ...]
    settings: EngagedContactSolveSettings
    optimizer_success: bool
    optimizer_status: int
    optimizer_message: str
    function_evaluations: int
    optimizer_cost: float
    jacobian: NDArray[np.float64]
    jacobian_determinant: float
    jacobian_condition_number: float
    active_lower_bounds: tuple[bool, ...]
    active_upper_bounds: tuple[bool, ...]
    accepted: bool

    def __post_init__(self) -> None:
        if self.mode is EngagedContactMode.BOTH_SLIP:
            raise ValueError("EngagedContactSolveResult is only for branches with stick residuals.")
        if not self.sticking_interfaces:
            raise ValueError("A bounded stick-residual result needs at least one sticking interface.")
        if len(self.jacobian.shape) != 2 or self.jacobian.shape != (
            len(self.sticking_interfaces),
            len(self.sticking_interfaces),
        ):
            raise ValueError("jacobian shape must match the number of sticking interfaces.")
        if not np.all(np.isfinite(self.jacobian)):
            raise ValueError("jacobian must contain finite values.")
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
            raise ValueError("jacobian_condition_number must be non-negative.")
        object.__setattr__(self, "jacobian", _immutable_array(self.jacobian))

    @property
    def friction_utilization(self) -> TrialFrictionUtilization:
        return self.trial.friction_utilization

    @property
    def closure(self) -> TrialClosureResult:
        return self.trial.closure

    @property
    def relative_motion(self) -> ContactRelativeMotion:
        return self.trial.relative_motion

    @property
    def state_derivative(self) -> CVTDynamicStateDerivative:
        """Return the ODE derivative associated with this branch trial."""

        return self.trial.state_derivative

    @property
    def sticking_residuals(self) -> NDArray[np.float64]:
        return self.relative_motion.acceleration_residual_vector(self.sticking_interfaces)


@dataclass(frozen=True, slots=True)
class BothSlipResult:
    """Direct engaged closure result when both lambdas are kinetic-known."""

    trial: EngagedContactTrial
    primary_slip: KineticSlipSpecification
    secondary_slip: KineticSlipSpecification
    contact_tolerances: ContactKinematicTolerances

    def __post_init__(self) -> None:
        if self.primary_slip.interface is not ContactInterface.PRIMARY:
            raise ValueError("primary_slip must specify the primary interface.")
        if self.secondary_slip.interface is not ContactInterface.SECONDARY:
            raise ValueError("secondary_slip must specify the secondary interface.")

    @property
    def mode(self) -> EngagedContactMode:
        return EngagedContactMode.BOTH_SLIP

    @property
    def primary_direction_is_consistent(self) -> bool:
        return self.primary_slip.direction_is_consistent(
            self.trial.relative_motion,
            tolerances=self.contact_tolerances,
        )

    @property
    def secondary_direction_is_consistent(self) -> bool:
        return self.secondary_slip.direction_is_consistent(
            self.trial.relative_motion,
            tolerances=self.contact_tolerances,
        )


@dataclass(frozen=True, slots=True)
class EngagedContactClosure:
    """State-frozen common trial evaluator with rows 2--5 cached once."""

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
        maximum_closure_condition_number: float | None = None,
    ) -> EngagedContactTrial:
        """Build lambda-dependent rows, solve, and evaluate contact motion once."""

        context = TrialEquationContext(
            snapshot=self.snapshot,
            friction_utilization=friction_utilization,
        )
        closure = build_trial_closure_system(
            fixed_equations=self.fixed_equations,
            trial_context=context,
        ).solve(maximum_condition_number=maximum_closure_condition_number)
        return EngagedContactTrial(
            friction_utilization=friction_utilization,
            closure=closure,
            relative_motion=evaluate_contact_relative_motion(
                state=self.snapshot.state,
                geometry=self.snapshot.geometry,
                unknowns=closure.unknowns,
            ),
            state_derivative=CVTDynamicStateDerivative.from_engaged_closure(
                state=self.snapshot.state,
                unknowns=closure.unknowns,
            ),
        )

    def solve_bounded_stick_residuals(
        self,
        *,
        mode: EngagedContactMode,
        sticking_interfaces: tuple[ContactInterface, ...],
        fixed_lambdas: Mapping[ContactInterface, float],
        fixed_slip_specifications: tuple[KineticSlipSpecification, ...],
        settings: EngagedContactSolveSettings,
    ) -> EngagedContactSolveResult:
        """Run the one reusable bounded root solve for 2D or 1D stick closure.

        ``sticking_interfaces`` determines the nonlinear dimension. Two
        interfaces gives the stick--stick solve; one gives either mixed slip
        branch. Each free lambda is bounded by its static interval, while the
        slipping interface remains fixed at its signed kinetic lambda.
        """

        if not isinstance(mode, EngagedContactMode):
            raise TypeError("mode must be an EngagedContactMode.")
        if mode is EngagedContactMode.BOTH_SLIP:
            raise ValueError("Both-slip has no stick residuals and uses evaluate_both_slip().")
        if not isinstance(settings, EngagedContactSolveSettings):
            raise TypeError("settings must be an EngagedContactSolveSettings instance.")

        free_interfaces = _validate_branch_layout(
            mode=mode,
            sticking_interfaces=sticking_interfaces,
            fixed_lambdas=fixed_lambdas,
            fixed_slip_specifications=fixed_slip_specifications,
        )

        lower = np.asarray(
            [settings.static_bounds.lower_at(interface) for interface in free_interfaces],
            dtype=float,
        )
        upper = np.asarray(
            [settings.static_bounds.upper_at(interface) for interface in free_interfaces],
            dtype=float,
        )
        initial = np.asarray(
            [settings.initial_guess_at(interface) for interface in free_interfaces],
            dtype=float,
        )
        if np.any(initial < lower) or np.any(initial > upper):
            raise ValueError("initial free lambda guesses must lie inside their static bounds.")

        def utilization_from_free_values(values: NDArray[np.float64]) -> TrialFrictionUtilization:
            lambda_values = dict(fixed_lambdas)
            for interface, value in zip(free_interfaces, values, strict=True):
                lambda_values[interface] = float(value)
            return TrialFrictionUtilization(
                primary_lambda=lambda_values[ContactInterface.PRIMARY],
                secondary_lambda=lambda_values[ContactInterface.SECONDARY],
            )

        def residual_vector(values: NDArray[np.float64]) -> NDArray[np.float64]:
            trial = self.evaluate_trial(
                friction_utilization=utilization_from_free_values(values),
                maximum_closure_condition_number=(
                    settings.maximum_closure_condition_number
                ),
            )
            return trial.relative_motion.acceleration_residual_vector(
                sticking_interfaces
            )

        # Three-point central differences sample small plus/minus lambda
        # perturbations. That costs a few extra tiny closure solves but
        # gives a less biased local Jacobian slope estimate across the narrow
        # residual corridor than one-sided differences.
        optimized = least_squares(
            residual_vector,
            x0=initial,
            bounds=(lower, upper),
            method="trf",
            jac="3-point",
            x_scale="jac",
            ftol=settings.optimizer_tolerance,
            xtol=settings.optimizer_tolerance,
            gtol=settings.optimizer_tolerance,
            max_nfev=settings.maximum_function_evaluations,
        )

        utilization = utilization_from_free_values(np.asarray(optimized.x, dtype=float))
        trial = self.evaluate_trial(
            friction_utilization=utilization,
            maximum_closure_condition_number=(
                settings.maximum_closure_condition_number
            ),
        )
        jacobian = np.asarray(optimized.jac, dtype=float)
        expected_shape = (len(sticking_interfaces), len(free_interfaces))
        if jacobian.shape != expected_shape or not np.all(np.isfinite(jacobian)):
            raise ValueError(
                "Optimizer Jacobian does not match the selected stick residual layout."
            )

        active_lower, active_upper = _active_bounds(
            utilization=utilization,
            bounds=settings.static_bounds,
            interfaces=free_interfaces,
        )
        accepted = (
            bool(optimized.success)
            and trial.relative_motion.are_stick_compatible(
                sticking_interfaces,
                tolerances=settings.contact_tolerances,
            )
        )

        return EngagedContactSolveResult(
            mode=mode,
            trial=trial,
            sticking_interfaces=sticking_interfaces,
            fixed_slip_specifications=fixed_slip_specifications,
            settings=settings,
            optimizer_success=bool(optimized.success),
            optimizer_status=int(optimized.status),
            optimizer_message=str(optimized.message).replace("\n", " "),
            function_evaluations=int(optimized.nfev),
            optimizer_cost=float(optimized.cost),
            jacobian=jacobian,
            jacobian_determinant=float(np.linalg.det(jacobian)),
            jacobian_condition_number=float(np.linalg.cond(jacobian)),
            active_lower_bounds=active_lower,
            active_upper_bounds=active_upper,
            accepted=accepted,
        )

    def solve_stick_stick(
        self,
        *,
        settings: EngagedContactSolveSettings,
    ) -> EngagedContactSolveResult:
        """Solve both free static lambdas against both stick residuals."""

        return self.solve_bounded_stick_residuals(
            mode=EngagedContactMode.STICK_STICK,
            sticking_interfaces=(ContactInterface.PRIMARY, ContactInterface.SECONDARY),
            fixed_lambdas={},
            fixed_slip_specifications=(),
            settings=settings,
        )

    def solve_primary_slip_secondary_stick(
        self,
        *,
        primary_slip: KineticSlipSpecification,
        settings: EngagedContactSolveSettings,
    ) -> EngagedContactSolveResult:
        """Fix primary kinetic lambda and solve secondary stick residual only."""

        _require_slip_interface(primary_slip, ContactInterface.PRIMARY)
        return self.solve_bounded_stick_residuals(
            mode=EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK,
            sticking_interfaces=(ContactInterface.SECONDARY,),
            fixed_lambdas={ContactInterface.PRIMARY: primary_slip.signed_lambda},
            fixed_slip_specifications=(primary_slip,),
            settings=settings,
        )

    def solve_primary_stick_secondary_slip(
        self,
        *,
        secondary_slip: KineticSlipSpecification,
        settings: EngagedContactSolveSettings,
    ) -> EngagedContactSolveResult:
        """Fix secondary kinetic lambda and solve primary stick residual only."""

        _require_slip_interface(secondary_slip, ContactInterface.SECONDARY)
        return self.solve_bounded_stick_residuals(
            mode=EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP,
            sticking_interfaces=(ContactInterface.PRIMARY,),
            fixed_lambdas={ContactInterface.SECONDARY: secondary_slip.signed_lambda},
            fixed_slip_specifications=(secondary_slip,),
            settings=settings,
        )

    def evaluate_both_slip(
        self,
        *,
        primary_slip: KineticSlipSpecification,
        secondary_slip: KineticSlipSpecification,
        contact_tolerances: ContactKinematicTolerances,
        maximum_closure_condition_number: float | None = None,
    ) -> BothSlipResult:
        """Fix both kinetic lambdas and solve the shared closure once."""

        _require_slip_interface(primary_slip, ContactInterface.PRIMARY)
        _require_slip_interface(secondary_slip, ContactInterface.SECONDARY)
        if not isinstance(contact_tolerances, ContactKinematicTolerances):
            raise TypeError(
                "contact_tolerances must be a ContactKinematicTolerances instance."
            )
        trial = self.evaluate_trial(
            friction_utilization=TrialFrictionUtilization(
                primary_lambda=primary_slip.signed_lambda,
                secondary_lambda=secondary_slip.signed_lambda,
            ),
            maximum_closure_condition_number=maximum_closure_condition_number,
        )
        return BothSlipResult(
            trial=trial,
            primary_slip=primary_slip,
            secondary_slip=secondary_slip,
            contact_tolerances=contact_tolerances,
        )


def solve_stick_stick(
    *,
    snapshot: DynamicsSnapshot,
    settings: EngagedContactSolveSettings,
) -> EngagedContactSolveResult:
    """Convenience wrapper for an engaged state known to be stick--stick."""

    return EngagedContactClosure(snapshot=snapshot).solve_stick_stick(settings=settings)


def solve_primary_slip_secondary_stick(
    *,
    snapshot: DynamicsSnapshot,
    primary_slip: KineticSlipSpecification,
    settings: EngagedContactSolveSettings,
) -> EngagedContactSolveResult:
    """Convenience wrapper for the primary-slip/secondary-stick branch."""

    return EngagedContactClosure(snapshot=snapshot).solve_primary_slip_secondary_stick(
        primary_slip=primary_slip,
        settings=settings,
    )


def solve_primary_stick_secondary_slip(
    *,
    snapshot: DynamicsSnapshot,
    secondary_slip: KineticSlipSpecification,
    settings: EngagedContactSolveSettings,
) -> EngagedContactSolveResult:
    """Convenience wrapper for the primary-stick/secondary-slip branch."""

    return EngagedContactClosure(snapshot=snapshot).solve_primary_stick_secondary_slip(
        secondary_slip=secondary_slip,
        settings=settings,
    )


def evaluate_both_slip(
    *,
    snapshot: DynamicsSnapshot,
    primary_slip: KineticSlipSpecification,
    secondary_slip: KineticSlipSpecification,
    contact_tolerances: ContactKinematicTolerances = ContactKinematicTolerances(),
    maximum_closure_condition_number: float | None = None,
) -> BothSlipResult:
    """Convenience wrapper for the direct both-slip branch evaluation."""

    return EngagedContactClosure(snapshot=snapshot).evaluate_both_slip(
        primary_slip=primary_slip,
        secondary_slip=secondary_slip,
        contact_tolerances=contact_tolerances,
        maximum_closure_condition_number=maximum_closure_condition_number,
    )


def _validate_branch_layout(
    *,
    mode: EngagedContactMode,
    sticking_interfaces: tuple[ContactInterface, ...],
    fixed_lambdas: Mapping[ContactInterface, float],
    fixed_slip_specifications: tuple[KineticSlipSpecification, ...],
) -> tuple[ContactInterface, ...]:
    expected_sticking = mode.sticking_interfaces
    if sticking_interfaces != expected_sticking:
        raise ValueError("sticking_interfaces must match the requested contact mode.")
    if len(set(sticking_interfaces)) != len(sticking_interfaces):
        raise ValueError("sticking_interfaces must not contain duplicates.")
    if set(fixed_lambdas) != set(mode.slipping_interfaces):
        raise ValueError("fixed_lambdas must cover exactly the slipping interfaces.")
    if any(not isfinite(value) or value == 0.0 for value in fixed_lambdas.values()):
        raise ValueError("fixed kinetic lambdas must be finite and non-zero.")
    if {spec.interface for spec in fixed_slip_specifications} != set(mode.slipping_interfaces):
        raise ValueError("fixed_slip_specifications must match the slipping interfaces.")
    if len({spec.interface for spec in fixed_slip_specifications}) != len(
        fixed_slip_specifications
    ):
        raise ValueError("fixed_slip_specifications must not contain duplicate interfaces.")

    free_interfaces = sticking_interfaces
    if set(free_interfaces) | set(fixed_lambdas) != {
        ContactInterface.PRIMARY,
        ContactInterface.SECONDARY,
    }:
        raise ValueError("Every engaged interface must be exactly free or fixed.")
    return free_interfaces


def _require_slip_interface(
    specification: KineticSlipSpecification,
    interface: ContactInterface,
) -> None:
    if not isinstance(specification, KineticSlipSpecification):
        raise TypeError("slip specification must be a KineticSlipSpecification.")
    if specification.interface is not interface:
        raise ValueError(f"Expected a {interface.value} slip specification.")


def _active_bounds(
    *,
    utilization: TrialFrictionUtilization,
    bounds: FrictionUtilizationBounds,
    interfaces: tuple[ContactInterface, ...],
) -> tuple[tuple[bool, ...], tuple[bool, ...]]:
    values = {
        ContactInterface.PRIMARY: utilization.primary_lambda,
        ContactInterface.SECONDARY: utilization.secondary_lambda,
    }
    scale = max(
        1.0,
        abs(bounds.primary_lower),
        abs(bounds.primary_upper),
        abs(bounds.secondary_lower),
        abs(bounds.secondary_upper),
    )
    tolerance = _BOUND_ACTIVITY_ABSOLUTE_TOLERANCE * scale
    return (
        tuple(
            abs(values[interface] - bounds.lower_at(interface)) <= tolerance
            for interface in interfaces
        ),
        tuple(
            abs(values[interface] - bounds.upper_at(interface)) <= tolerance
            for interface in interfaces
        ),
    )


def _validate_one_sided_interval(*, name: str, lower: float, upper: float) -> None:
    _require_finite(lower=lower, upper=upper)
    if not lower < upper:
        raise ValueError(f"{name} must satisfy lower < upper.")
    if lower <= 0.0 <= upper:
        raise ValueError(
            f"{name} must remain strictly on one side of zero while the current "
            "closure rows contain 1/lambda terms."
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


def _immutable_array(values: NDArray[np.float64] | np.ndarray) -> NDArray[np.float64]:
    array = np.array(values, dtype=float, copy=True)
    array.setflags(write=False)
    return array
