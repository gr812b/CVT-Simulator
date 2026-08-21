"""CVT-specific adapter from an engaged contact regime to generic hybrid hooks."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import (
    ContactInterface,
    ContactRegime,
    ContactRelativeMotion,
    ContactTractionLaw,
    ContactTractionUtilization,
    EngagedContactMode,
)
from cinder.model.cvt.dynamics.engaged_contact import (
    BothSlipResult,
    EngagedContactClosure,
    EngagedContactSolveResult,
    EngagedContactSolveSettings,
    StickResidualContinuation,
)
from cinder.model.system.evaluator import MechanicalCVTPlant, DynamicsSnapshot
from cinder.model.system.ports import CVTShaftBoundaryValues
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint

from .state import CVTState, CVTStateDerivative

if TYPE_CHECKING:
    from .cvt_contact_switching import CVTContactSwitchSettings


@dataclass(frozen=True, slots=True)
class CVTContactEvaluation:
    """One branch evaluation at one state, including closure diagnostics."""

    regime: ContactRegime
    state: CVTState
    snapshot: DynamicsSnapshot
    branch_result: EngagedContactSolveResult | BothSlipResult
    shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE

    def __post_init__(self) -> None:
        if not isinstance(self.shift_constraint, EngagedShiftConstraint):
            raise TypeError("shift_constraint must be an EngagedShiftConstraint.")

    @property
    def mode(self) -> EngagedContactMode:
        return self.regime.mode

    @property
    def traction_utilization(self) -> ContactTractionUtilization:
        if isinstance(self.branch_result, EngagedContactSolveResult):
            return self.branch_result.traction_utilization
        return self.branch_result.trial.traction_utilization

    @property
    def relative_motion(self) -> ContactRelativeMotion:
        if isinstance(self.branch_result, EngagedContactSolveResult):
            return self.branch_result.relative_motion
        return self.branch_result.trial.relative_motion

    @property
    def state_derivative(self) -> CVTStateDerivative:
        if isinstance(self.branch_result, EngagedContactSolveResult):
            return self.branch_result.state_derivative
        return self.branch_result.trial.state_derivative

    @property
    def closure_unknowns(self):
        if isinstance(self.branch_result, EngagedContactSolveResult):
            return self.branch_result.closure.unknowns
        return self.branch_result.trial.closure.unknowns

    @property
    def low_ratio_seat_reaction(self) -> float | None:
        """Return the recovered closing reaction at the low-ratio seat."""

        if isinstance(self.branch_result, EngagedContactSolveResult):
            return self.branch_result.trial.low_ratio_seat_reaction
        return self.branch_result.trial.low_ratio_seat_reaction

    @property
    def upper_stop_reaction(self) -> float | None:
        """Return the recovered high-ratio stop reaction when constrained."""

        if isinstance(self.branch_result, EngagedContactSolveResult):
            return self.branch_result.trial.upper_stop_reaction
        return self.branch_result.trial.upper_stop_reaction

    @property
    def normal_primary(self) -> float:
        return self.closure_unknowns.primary_normal_resultant

    @property
    def normal_secondary(self) -> float:
        return self.closure_unknowns.secondary_normal_resultant

    def normal_at(self, interface: ContactInterface) -> float:
        if interface is ContactInterface.PRIMARY:
            return self.normal_primary
        if interface is ContactInterface.SECONDARY:
            return self.normal_secondary
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def static_margin_at(
        self,
        interface: ContactInterface,
        *,
        traction_law: ContactTractionLaw,
    ) -> float:
        """Return static traction margin at a contact declared sticking."""

        if not isinstance(self.branch_result, EngagedContactSolveResult):
            raise ValueError("Both-slip contains no static lambda requirement.")
        return self.branch_result.required_static_margin_at(
            interface,
            traction_law=traction_law,
        )

    def sticks_are_admissible(
        self,
        *,
        traction_law: ContactTractionLaw,
        required_margin: float,
    ) -> bool:
        """Return whether all active sticking contacts have the requested reserve."""

        if not isinstance(self.branch_result, EngagedContactSolveResult):
            return True
        return self.branch_result.accepted and all(
            self.static_margin_at(interface, traction_law=traction_law)
            >= required_margin
            for interface in self.regime.mode.sticking_interfaces
        )

    def slipped_directions_are_consistent(self) -> bool:
        """Return whether every imposed kinetic direction matches current motion."""

        if isinstance(self.branch_result, BothSlipResult):
            return (
                self.branch_result.primary_direction_is_consistent
                and self.branch_result.secondary_direction_is_consistent
            )
        return all(
            specification.direction_is_consistent(
                self.relative_motion,
                tolerances=self.branch_result.settings.contact_tolerances,
            )
            for specification in self.branch_result.fixed_slip_specifications
        )


@dataclass(slots=True)
class EngagedCVTContactEvaluator:
    """State-vector adapter around the existing 2D/1D/direct contact solvers.

    The evaluator has one small exact-state cache because solve_ivp commonly
    asks for the RHS and several event values at the same time/state.  The
    cache changes no physics and only avoids duplicated outer lambda solves.
    """

    model: MechanicalCVTPlant
    traction_law: ContactTractionLaw
    solve_settings: EngagedContactSolveSettings
    _cache_key: (
        tuple[
            float,
            tuple[float, ...],
            ContactRegime,
            EngagedShiftConstraint,
        ]
        | None
    ) = None
    _cache_value: CVTContactEvaluation | None = None
    _continuations: dict[
        tuple[ContactRegime, EngagedShiftConstraint],
        StickResidualContinuation,
    ] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.model, MechanicalCVTPlant):
            raise TypeError("model must be a MechanicalCVTPlant instance.")
        if not isinstance(self.traction_law, ContactTractionLaw):
            raise TypeError("traction_law must be a ContactTractionLaw instance.")
        if not isinstance(self.solve_settings, EngagedContactSolveSettings):
            raise TypeError(
                "solve_settings must be an EngagedContactSolveSettings instance."
            )

    def evaluate_vector(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        regime: ContactRegime,
        shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> CVTContactEvaluation:
        """Evaluate the selected branch from the generic integration vector."""

        if not isfinite(time):
            raise ValueError("time must be finite.")
        if not isinstance(shift_constraint, EngagedShiftConstraint):
            raise TypeError("shift_constraint must be an EngagedShiftConstraint.")
        state = CVTState.from_vector(vector)
        key = (
            float(time),
            tuple(float(value) for value in state.as_vector()),
            regime,
            shift_constraint,
            _boundary_cache_key(shaft_boundaries),
        )
        if key == self._cache_key and self._cache_value is not None:
            return self._cache_value

        # During solve_ivp event localization, an internal Runge--Kutta stage
        # can briefly lie beyond the mathematical geometry interval before the
        # terminal travel-stop event is located. Evaluate closure mechanics at
        # the nearest valid geometry point for that *rejected stage only*.
        # The raw vector is retained for event values, so accepted trajectories
        # still terminate exactly at the configured physical stop; this is not
        # a substitute for the future stop-reaction model.
        snapshot_state = self._geometry_safe_state(state)
        snapshot = self.model.snapshot_at_time(
            time=time,
            state=snapshot_state,
            shaft_boundaries=shaft_boundaries,
            geometry_side="engaged",
        )
        closure = EngagedContactClosure(
            snapshot=snapshot,
            shift_constraint=shift_constraint,
        )
        continuation_key = (regime, shift_constraint)
        solve_settings = self._continuation_settings_for(continuation_key)
        continuation = self._continuations.get(continuation_key)
        if regime.mode is EngagedContactMode.STICK_STICK:
            result = closure.solve_stick_stick(
                settings=solve_settings,
                continuation=continuation,
            )
        elif regime.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
            primary_slip = self.traction_law.kinetic_slip_specification(
                interface=ContactInterface.PRIMARY,
                direction=regime.slip_direction_at(ContactInterface.PRIMARY),
            )
            result = closure.solve_primary_slip_secondary_stick(
                primary_slip=primary_slip,
                settings=solve_settings,
                continuation=continuation,
            )
        elif regime.mode is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
            secondary_slip = self.traction_law.kinetic_slip_specification(
                interface=ContactInterface.SECONDARY,
                direction=regime.slip_direction_at(ContactInterface.SECONDARY),
            )
            result = closure.solve_primary_stick_secondary_slip(
                secondary_slip=secondary_slip,
                settings=solve_settings,
                continuation=continuation,
            )
        elif regime.mode is EngagedContactMode.BOTH_SLIP:
            primary_slip = self.traction_law.kinetic_slip_specification(
                interface=ContactInterface.PRIMARY,
                direction=regime.slip_direction_at(ContactInterface.PRIMARY),
            )
            secondary_slip = self.traction_law.kinetic_slip_specification(
                interface=ContactInterface.SECONDARY,
                direction=regime.slip_direction_at(ContactInterface.SECONDARY),
            )
            result = closure.evaluate_both_slip(
                primary_slip=primary_slip,
                secondary_slip=secondary_slip,
                contact_tolerances=self.solve_settings.contact_tolerances,
                maximum_closure_condition_number=(
                    self.solve_settings.maximum_closure_condition_number
                ),
            )
        else:  # pragma: no cover - defensive enum exhaustiveness.
            raise ValueError(f"Unsupported engaged regime: {regime.mode!r}.")

        evaluation = CVTContactEvaluation(
            regime=regime,
            state=state,
            snapshot=snapshot,
            branch_result=result,
            shift_constraint=shift_constraint,
        )
        if isinstance(result, EngagedContactSolveResult) and result.accepted:
            # The required lambdas vary smoothly while an ODE segment remains
            # in one contact regime. Reusing the last accepted pair only changes
            # the nonlinear solver's initial guess; it does not alter the root
            # condition or branch physics. This continuation cache is essential
            # for practical long transient runs, where repeatedly starting each
            # stick solve from a global zero guess is unnecessarily expensive.
            self._continuations[continuation_key] = (
                StickResidualContinuation.from_result(result)
            )
        self._cache_key = key
        self._cache_value = evaluation
        return evaluation

    def _geometry_safe_state(self, state: CVTState) -> CVTState:
        """Project rejected integrator stages onto the active engaged domain.

        A trial stage can cross either the engagement surface or the upper
        travel stop before solve_ivp localizes the terminal event.  Closure for
        that rejected stage must still use the engaged-side tangent, so clip to
        ``[deadzone_shift, max_shift]`` while leaving the raw integration vector
        untouched for event localization.
        """

        spec = self.model.geometry.spec
        safe_shift = float(
            np.clip(state.shift_position, spec.deadzone_shift, spec.max_shift)
        )
        if safe_shift == state.shift_position:
            return state
        return replace(state, shift_position=safe_shift)

    def _continuation_settings_for(
        self,
        key: tuple[ContactRegime, EngagedShiftConstraint],
    ) -> EngagedContactSolveSettings:
        """Return solve settings warm-started from this regime's last root.

        The public ``solve_settings`` object stays immutable and remains the
        fallback source for a new regime or an inadmissible previous trial.
        """

        continuation = self._continuations.get(key)
        if continuation is None:
            return self.solve_settings
        guess = continuation.traction_utilization
        if not self.solve_settings.lambda_search_bounds.contains(guess):
            return self.solve_settings
        return replace(self.solve_settings, initial_guess=guess)

    def rhs_vector(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        regime: ContactRegime,
        shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> NDArray[np.float64]:
        """Return the six CINDER derivatives for the active contact regime."""

        return self.evaluate_vector(
            time=time,
            vector=vector,
            regime=regime,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        ).state_derivative.as_vector()

    def classify_initial_regime(
        self,
        *,
        state: CVTState,
        switching_settings: "CVTContactSwitchSettings",
        shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> ContactRegime:
        """Classify established slip or a stick candidate at initial time.

        This helper deliberately does not replace an application-specific
        clutch/engagement model.  It is only valid once both wraps are engaged.
        """

        from .cvt_contact_switching import resolve_initial_engaged_regime

        if not isinstance(shift_constraint, EngagedShiftConstraint):
            raise TypeError("shift_constraint must be an EngagedShiftConstraint.")
        return resolve_initial_engaged_regime(
            evaluator=self,
            time=0.0,
            state=state,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )


def _boundary_cache_key(boundaries: CVTShaftBoundaryValues | None):
    if boundaries is None:
        return None
    return (
        boundaries.primary.external_torque,
        boundaries.primary.equivalent_inertia,
        boundaries.secondary.external_torque,
        boundaries.secondary.equivalent_inertia,
    )
