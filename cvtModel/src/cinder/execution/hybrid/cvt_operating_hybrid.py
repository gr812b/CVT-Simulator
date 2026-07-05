"""Full operating-regime hybrid adapter for the reduced CVT model.

The continuous state is shared by every regime, but the governing equations are
not.  This adapter dispatches only between already-derived evaluators:

    deadzone/free <-> deadzone/lower stop
            <->
    engaged/free/contact branch <-> engaged/low-ratio-seat/contact branch
                                 <-> engaged/upper-stop/contact branch.

Deadzone remains a reduced primary-disengaged model; it does not call the
engaged lambda/tension closure.  Conversely, the upper stop remains an
engaged fixed-shift closure and retains the contact topology.  Event functions
are built only for boundaries reachable from the active physical regime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import ContactRegime, ContactTractionLaw
from cinder.model.cvt.dynamics.deadzone import DeadzoneDynamicsEvaluator, DeadzoneEvaluation
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactSolveSettings
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system.evaluator import CVTDynamicsModel

from .cvt_contact import CVTContactEvaluation, EngagedCVTContactEvaluator
from .cvt_contact_events import build_cvt_contact_events
from .cvt_contact_switching import CVTContactSwitchSettings
from .cvt_operating_limits import CVTShiftOperatingLimits
from .cvt_regime import (
    CVTEngagementState,
    CVTOperatingRegime,
    CVTShiftConstraint,
)
from .cvt_regime_events import (
    build_deadzone_free_boundary_events,
    build_engaged_free_boundary_events,
    build_lower_stop_release_event,
    build_low_ratio_seat_events,
    build_upper_stop_release_event,
)
from .cvt_regime_switching import (
    classify_initial_cvt_regime,
    primary_independent_clamping_force_at_engagement,
    resolve_cvt_operating_transition,
)
from .hybrid import (
    HybridEvent,
    HybridIntegrationResult,
    HybridIntegratorSettings,
    HybridTransition,
    integrate_hybrid,
)
from .state import CVTDynamicState

CVTRegimeEvaluation: TypeAlias = CVTContactEvaluation | DeadzoneEvaluation


@dataclass(frozen=True, slots=True)
class CVTOperatingSystemConfig:
    """Immutable execution settings used to build hybrid systems from cases.

    This keeps physical configuration in :class:`CVTSimulationCase` and all
    contact/hybrid numerical configuration in one separate object.  A route,
    engine, or output-boundary change therefore edits a case and builds one new
    runtime system through :meth:`build`; no runtime model is copied or edited.
    """

    traction_law: ContactTractionLaw
    solve_settings: EngagedContactSolveSettings
    operating_limits: CVTShiftOperatingLimits
    switching_settings: CVTContactSwitchSettings = field(
        default_factory=CVTContactSwitchSettings
    )

    def __post_init__(self) -> None:
        if not isinstance(self.traction_law, ContactTractionLaw):
            raise TypeError("traction_law must be a ContactTractionLaw instance.")
        if not isinstance(self.solve_settings, EngagedContactSolveSettings):
            raise TypeError("solve_settings must be an EngagedContactSolveSettings instance.")
        if not isinstance(self.operating_limits, CVTShiftOperatingLimits):
            raise TypeError("operating_limits must be a CVTShiftOperatingLimits instance.")
        if not isinstance(self.switching_settings, CVTContactSwitchSettings):
            raise TypeError("switching_settings must be a CVTContactSwitchSettings instance.")

    def build(self, case: "CVTSimulationCase") -> "CVTOperatingHybridSystem":
        return CVTOperatingHybridSystem.from_case(
            case,
            traction_law=self.traction_law,
            solve_settings=self.solve_settings,
            operating_limits=self.operating_limits,
            switching_settings=self.switching_settings,
        )


@dataclass(slots=True)
class CVTOperatingHybridSystem:
    """Segmented hybrid adapter over all currently derived CVT RHS regimes.

    The engaged evaluator owns lambda solves, contact branch algebra, and the
    low-ratio-seat / upper-stop constrained closures.  The deadzone evaluator owns neutral
    primary motion and the imposed belt-secondary lock.  This adapter only
    selects between those evaluators, exposes valid events, and delegates
    event transitions to the operating-regime resolver.
    """

    model: CVTDynamicsModel
    traction_law: ContactTractionLaw
    solve_settings: EngagedContactSolveSettings
    operating_limits: CVTShiftOperatingLimits
    switching_settings: CVTContactSwitchSettings = field(
        default_factory=CVTContactSwitchSettings
    )
    evaluator: EngagedCVTContactEvaluator = field(init=False)
    deadzone_evaluator: DeadzoneDynamicsEvaluator = field(init=False)

    @classmethod
    def from_case(
        cls,
        case: "CVTSimulationCase",
        *,
        traction_law: ContactTractionLaw,
        solve_settings: EngagedContactSolveSettings,
        operating_limits: CVTShiftOperatingLimits,
        switching_settings: CVTContactSwitchSettings | None = None,
    ) -> "CVTOperatingHybridSystem":
        """Construct one runtime system through the sole case-to-model path.

        The returned object deliberately stores only runtime mechanics and
        hybrid settings.  Any edit to road, engine, vehicle, or initial
        conditions is made by replacing a part of ``CVTSimulationCase`` and
        calling this factory again.
        """

        from cinder.model.system import CVTDynamicsModel, CVTSimulationCase

        if not isinstance(case, CVTSimulationCase):
            raise TypeError("case must be a CVTSimulationCase.")
        return cls(
            model=CVTDynamicsModel.from_case(case),
            traction_law=traction_law,
            solve_settings=solve_settings,
            operating_limits=operating_limits,
            switching_settings=(
                CVTContactSwitchSettings()
                if switching_settings is None
                else switching_settings
            ),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.model, CVTDynamicsModel):
            raise TypeError("model must be a CVTDynamicsModel instance.")
        if not isinstance(self.traction_law, ContactTractionLaw):
            raise TypeError("traction_law must be a ContactTractionLaw instance.")
        if not isinstance(self.solve_settings, EngagedContactSolveSettings):
            raise TypeError(
                "solve_settings must be an EngagedContactSolveSettings instance."
            )
        if not isinstance(self.operating_limits, CVTShiftOperatingLimits):
            raise TypeError(
                "operating_limits must be a CVTShiftOperatingLimits instance."
            )
        if not isinstance(self.switching_settings, CVTContactSwitchSettings):
            raise TypeError(
                "switching_settings must be a CVTContactSwitchSettings instance."
            )

        self.operating_limits.validate_against_geometry_spec(self.model.geometry.spec)
        self.evaluator = EngagedCVTContactEvaluator(
            model=self.model,
            traction_law=self.traction_law,
            solve_settings=self.solve_settings,
        )
        self.deadzone_evaluator = DeadzoneDynamicsEvaluator(model=self.model)

    def evaluate(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
    ) -> CVTRegimeEvaluation:
        """Evaluate the active physical regime without mixing its equations.

        ``time`` is consumed by the engaged contact evaluator's exact-state
        cache.  The current reduced deadzone equations are autonomous apart
        from their integrated state and intentionally do not need it.
        """

        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("mode must be a CVTOperatingRegime instance.")

        if mode.engagement is CVTEngagementState.DEADZONE:
            deadzone_state = CVTDynamicState.from_vector(state)
            if mode.shift_constraint is CVTShiftConstraint.FREE:
                return self.deadzone_evaluator.evaluate_free(state=deadzone_state)
            if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
                return self.deadzone_evaluator.evaluate_lower_stop(
                    state=deadzone_state,
                    lower_stop_shift=self.operating_limits.lower_stop_shift,
                )
            raise RuntimeError(
                f"Unsupported deadzone shift constraint: {mode.shift_constraint!r}."
            )

        constraint = self._engaged_constraint_for(mode)
        assert mode.contact_regime is not None
        return self.evaluator.evaluate_vector(
            time=time,
            vector=state,
            regime=mode.contact_regime,
            shift_constraint=constraint,
        )

    def rhs(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
    ) -> NDArray[np.float64]:
        """Return the derivative from the active regime-specific evaluator."""

        return self.evaluate(
            time=time, state=state, mode=mode
        ).state_derivative.as_vector()

    def events(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
    ) -> tuple[HybridEvent, ...]:
        """Build exactly the physical events reachable from ``mode``."""

        del time, state  # Event factories capture only mode-dependent mechanics.
        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("mode must be a CVTOperatingRegime instance.")

        if mode.engagement is CVTEngagementState.DEADZONE:
            if mode.shift_constraint is CVTShiftConstraint.FREE:
                return build_deadzone_free_boundary_events(limits=self.operating_limits)
            if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
                return (
                    build_lower_stop_release_event(
                        closing_reaction=lambda _time, vector: self._lower_stop_reaction(
                            vector=vector,
                        )
                    ),
                )
            raise RuntimeError(
                f"Unsupported deadzone shift constraint: {mode.shift_constraint!r}."
            )

        constraint = self._engaged_constraint_for(mode)
        assert mode.contact_regime is not None
        contact_events = build_cvt_contact_events(
            regime=mode.contact_regime,
            evaluate=lambda event_time, vector: self.evaluator.evaluate_vector(
                time=event_time,
                vector=vector,
                regime=mode.contact_regime,
                shift_constraint=constraint,
            ),
            traction_law=self.traction_law,
            switching_settings=self.switching_settings,
            relative_speed_tolerance=self.solve_settings.contact_tolerances.relative_speed_tolerance,
            relative_acceleration_tolerance=self.solve_settings.contact_tolerances.relative_acceleration_tolerance,
            include_shift_boundary_events=False,
        )

        if mode.shift_constraint is CVTShiftConstraint.FREE:
            return contact_events + build_engaged_free_boundary_events(
                limits=self.operating_limits
            )

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            return contact_events + build_low_ratio_seat_events(
                primary_clamping_force=lambda event_time, vector: self._primary_clamping_force(
                    time=event_time,
                    vector=vector,
                ),
                closing_reaction=lambda event_time, vector: self._low_ratio_seat_reaction(
                    time=event_time,
                    vector=vector,
                    contact_regime=mode.contact_regime,
                ),
            )

        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            return contact_events + (
                build_upper_stop_release_event(
                    opening_reaction=lambda event_time, vector: self._upper_stop_reaction(
                        time=event_time,
                        vector=vector,
                        contact_regime=mode.contact_regime,
                    )
                ),
            )
        raise RuntimeError(
            f"Unsupported engaged shift constraint: {mode.shift_constraint!r}."
        )

    def transition(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[CVTOperatingRegime]:
        """Resolve event successors and explicit impact/capture resets."""

        return resolve_cvt_operating_transition(
            evaluator=self.evaluator,
            deadzone_evaluator=self.deadzone_evaluator,
            time=time,
            vector=state,
            old_regime=mode,
            fired_event_names=fired_event_names,
            limits=self.operating_limits,
            switching_settings=self.switching_settings,
        )

    def classify_initial_regime(self, state: CVTDynamicState) -> CVTOperatingRegime:
        """Classify an initial state across deadzone and engaged operation.

        A state placed exactly at a unilateral stop is checked against that
        stop's recovered reaction.  An inadmissible stop is started as its
        corresponding free mode, never as a silently tensile constraint.
        """

        if not isinstance(state, CVTDynamicState):
            raise TypeError("state must be a CVTDynamicState instance.")
        mode = classify_initial_cvt_regime(
            evaluator=self.evaluator,
            state=state,
            limits=self.operating_limits,
            switching_settings=self.switching_settings,
        )
        self._validate_initial_mode_state(mode=mode, state=state)
        return self._release_inadmissible_initial_stop(mode=mode, state=state)

    def integrate(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: CVTDynamicState,
        initial_regime: CVTOperatingRegime | None = None,
        settings: HybridIntegratorSettings = HybridIntegratorSettings(),
    ) -> HybridIntegrationResult[CVTOperatingRegime]:
        """Integrate all currently implemented operating regimes."""

        if not isinstance(initial_state, CVTDynamicState):
            raise TypeError("initial_state must be a CVTDynamicState instance.")
        mode = initial_regime or self.classify_initial_regime(initial_state)
        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("initial_regime must be a CVTOperatingRegime instance.")
        self._validate_initial_mode_state(mode=mode, state=initial_state)
        mode = self._release_inadmissible_initial_stop(mode=mode, state=initial_state)
        self._validate_initial_mode_state(mode=mode, state=initial_state)

        return integrate_hybrid(
            system=self,
            time_span=time_span,
            initial_state=initial_state.as_vector(),
            initial_mode=mode,
            settings=settings,
        )

    def _lower_stop_reaction(self, *, vector: NDArray[np.float64]) -> float:
        state = CVTDynamicState.from_vector(vector)
        evaluation = self.deadzone_evaluator.evaluate_lower_stop(
            state=state,
            lower_stop_shift=self.operating_limits.lower_stop_shift,
        )
        reaction = evaluation.stop_reaction
        if reaction is None:  # pragma: no cover - lower-stop evaluator invariant.
            raise RuntimeError("Lower-stop evaluation did not recover a stop reaction.")
        return reaction

    def _primary_clamping_force(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
    ) -> float:
        """Return the primary mechanism's own signed clamp at engagement."""

        del time
        return primary_independent_clamping_force_at_engagement(
            evaluator=self.evaluator,
            state=CVTDynamicState.from_vector(vector),
            limits=self.operating_limits,
        )

    def _low_ratio_seat_reaction(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        contact_regime: ContactRegime,
    ) -> float:
        evaluation = self.evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=contact_regime,
            shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
        )
        reaction = evaluation.low_ratio_seat_reaction
        if reaction is None:  # pragma: no cover - constrained evaluator invariant.
            raise RuntimeError("Low-ratio seat closure did not return a seat reaction.")
        return reaction

    def _upper_stop_reaction(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        contact_regime: ContactRegime,
    ) -> float:
        evaluation = self.evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=contact_regime,
            shift_constraint=EngagedShiftConstraint.UPPER_STOP,
        )
        reaction = evaluation.upper_stop_reaction
        if reaction is None:  # pragma: no cover - constrained evaluator invariant.
            raise RuntimeError("Upper-stop closure did not return a stop reaction.")
        return reaction

    def _release_inadmissible_initial_stop(
        self,
        *,
        mode: CVTOperatingRegime,
        state: CVTDynamicState,
    ) -> CVTOperatingRegime:
        """Return a free mode when an initial unilateral stop would pull.

        This does not reset state: the supplied initial condition is already
        at zero shift speed by the stop-state validation below.  The successor
        free RHS supplies the inward acceleration on its first integration
        stage.
        """

        if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
            reaction = self.deadzone_evaluator.evaluate_lower_stop(
                state=state,
                lower_stop_shift=self.operating_limits.lower_stop_shift,
            ).stop_reaction
            assert reaction is not None
            if reaction < 0.0:
                return CVTOperatingRegime.deadzone_free()
            return mode

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            assert mode.contact_regime is not None
            clamp = self._primary_clamping_force(time=0.0, vector=state.as_vector())
            if clamp < 0.0:
                return CVTOperatingRegime.deadzone_free()
            reaction = self._low_ratio_seat_reaction(
                time=0.0,
                vector=state.as_vector(),
                contact_regime=mode.contact_regime,
            )
            if reaction < 0.0:
                return CVTOperatingRegime.engaged_free(
                    contact_regime=mode.contact_regime,
                )
            return mode

        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            assert mode.contact_regime is not None
            reaction = self._upper_stop_reaction(
                time=0.0,
                vector=state.as_vector(),
                contact_regime=mode.contact_regime,
            )
            if reaction < 0.0:
                return CVTOperatingRegime.engaged_free(
                    contact_regime=mode.contact_regime,
                )
        return mode

    @staticmethod
    def _engaged_constraint_for(mode: CVTOperatingRegime) -> EngagedShiftConstraint:
        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("mode must be a CVTOperatingRegime instance.")
        if mode.engagement is not CVTEngagementState.ENGAGED:
            raise ValueError(
                "An engaged shift constraint was requested for a deadzone mode."
            )
        if mode.shift_constraint is CVTShiftConstraint.FREE:
            return EngagedShiftConstraint.FREE
        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            return EngagedShiftConstraint.LOW_RATIO_SEAT
        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            return EngagedShiftConstraint.UPPER_STOP
        raise RuntimeError(
            f"Unsupported engaged shift constraint: {mode.shift_constraint!r}."
        )

    def _validate_initial_mode_state(
        self,
        *,
        mode: CVTOperatingRegime,
        state: CVTDynamicState,
    ) -> None:
        """Validate the state against the specific RHS it is about to enter."""

        lower = self.operating_limits.lower_stop_shift
        engagement = self.operating_limits.engagement_shift
        upper = self.operating_limits.upper_stop_shift
        tolerance = 1.0e-12

        if (
            state.shift_position < lower - tolerance
            or state.shift_position > upper + tolerance
        ):
            raise ValueError(
                "Initial shift position lies outside physical operating limits."
            )

        if mode.engagement is CVTEngagementState.DEADZONE:
            if mode.shift_constraint is CVTShiftConstraint.FREE:
                at_engagement_opening = (
                    isclose(
                        state.shift_position,
                        engagement,
                        rel_tol=0.0,
                        abs_tol=tolerance,
                    )
                    and state.shift_speed < 0.0
                )
                if not (state.shift_position < engagement or at_engagement_opening):
                    raise ValueError(
                        "A free deadzone segment must start below engagement_shift, or exactly "
                        "at engagement_shift while opening."
                    )
                if state.shift_position < lower - tolerance:
                    raise ValueError(
                        "A deadzone state must not lie below lower_stop_shift."
                    )
                # Validate the imposed neutral lock only after confirming this
                # is a legal deadzone coordinate; stage-safe geometry must not
                # mask an invalid initial operating regime.
                self.deadzone_evaluator.snapshot(state=state)
                return

            if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
                if not isclose(
                    state.shift_position,
                    lower,
                    rel_tol=0.0,
                    abs_tol=tolerance,
                ):
                    raise ValueError(
                        "A lower-stop segment must start at lower_stop_shift."
                    )
                if not isclose(state.shift_speed, 0.0, rel_tol=0.0, abs_tol=tolerance):
                    raise ValueError(
                        "A lower-stop segment must start with zero shift_speed."
                    )
                self.deadzone_evaluator.snapshot(state=state)
                return

            raise RuntimeError(
                f"Unsupported deadzone shift constraint: {mode.shift_constraint!r}."
            )

        if mode.shift_constraint is CVTShiftConstraint.FREE:
            at_engagement_closing = (
                isclose(
                    state.shift_position,
                    engagement,
                    rel_tol=0.0,
                    abs_tol=tolerance,
                )
                and state.shift_speed >= 0.0
            )
            if not (state.shift_position > engagement or at_engagement_closing):
                raise ValueError(
                    "A free engaged segment must start above engagement_shift, or exactly "
                    "at engagement_shift while closing/stationary."
                )
            at_upper_stop_after_release = isclose(
                state.shift_position,
                upper,
                rel_tol=0.0,
                abs_tol=tolerance,
            ) and isclose(state.shift_speed, 0.0, rel_tol=0.0, abs_tol=tolerance)
            if not (state.shift_position < upper or at_upper_stop_after_release):
                raise ValueError(
                    "A free engaged segment must start below upper_stop_shift, or exactly "
                    "at the upper stop with zero shift speed immediately after release."
                )
            return

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            if not isclose(
                state.shift_position,
                engagement,
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                raise ValueError(
                    "A low-ratio-seat segment must start at engagement_shift."
                )
            if not isclose(state.shift_speed, 0.0, rel_tol=0.0, abs_tol=tolerance):
                raise ValueError(
                    "A low-ratio-seat segment must start with zero shift_speed."
                )
            return

        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            if not isclose(
                state.shift_position,
                upper,
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                raise ValueError(
                    "An upper-stop segment must start at upper_stop_shift."
                )
            if not isclose(state.shift_speed, 0.0, rel_tol=0.0, abs_tol=tolerance):
                raise ValueError(
                    "An upper-stop segment must start with zero shift_speed."
                )
            return

        raise RuntimeError(
            f"Unsupported initial shift constraint: {mode.shift_constraint!r}."
        )
