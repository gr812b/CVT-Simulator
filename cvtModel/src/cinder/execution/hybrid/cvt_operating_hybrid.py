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

from dataclasses import dataclass, field, replace
from math import isclose
from typing import TYPE_CHECKING, Callable, TypeAlias

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import ContactRegime
from cinder.model.cvt.dynamics.deadzone import (
    DeadzoneDynamicsEvaluator,
    DeadzoneEvaluation,
)
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactSolveSettings
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system.evaluator import MechanicalCVTPlant
from cinder.model.system.runtime import RuntimeEvaluation
from cinder.model.system.ports import CVTShaftBoundaryValues

from .cvt_contact import CVTContactEvaluation, EngagedCVTContactEvaluator
from .cvt_contact_events import build_cvt_contact_events
from .cvt_contact_switching import CVTEventSwitchingTolerances
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
    primary_contact_separation_at_engagement,
    resolve_cvt_operating_transition,
)
from .hybrid import (
    HybridEvent,
    HybridIntegrationResult,
    HybridIntegratorSettings,
    HybridTransition,
    integrate_hybrid,
)
from .state import CVTState

if TYPE_CHECKING:
    from cinder.results import (
        CVTIntegrationResult,
        CVTIntegrationTrace,
        ReportingSettings,
    )

CVTRegimeEvaluation: TypeAlias = CVTContactEvaluation | DeadzoneEvaluation
ShaftBoundaryProvider: TypeAlias = Callable[
    [float, NDArray[np.float64]], CVTShaftBoundaryValues
]


@dataclass(frozen=True, slots=True)
class CVTOperatingSystemConfig:
    """Optional numerical policy for the CVT hybrid solver.

    Physical behavior is defined by the assembly: geometry, contact friction,
    actuators, couplers, and inertias. This config contains only numerical
    overrides. Omitted values are completed from the plant when the solver is
    built.
    """

    solve_settings: EngagedContactSolveSettings = field(
        default_factory=EngagedContactSolveSettings
    )
    switching_tolerances: CVTEventSwitchingTolerances = field(
        default_factory=CVTEventSwitchingTolerances
    )

    @property
    def switching_settings(self) -> CVTEventSwitchingTolerances:
        """Internal compatibility name used by the event resolver."""

        return self.switching_tolerances

    def __post_init__(self) -> None:
        if not isinstance(self.solve_settings, EngagedContactSolveSettings):
            raise TypeError(
                "solve_settings must be an EngagedContactSolveSettings instance."
            )
        if not isinstance(self.switching_tolerances, CVTEventSwitchingTolerances):
            raise TypeError(
                "switching_tolerances must be a CVTEventSwitchingTolerances instance."
            )

    def build(self, plant: MechanicalCVTPlant) -> "CVTOperatingHybridSystem":
        return CVTOperatingHybridSystem(
            model=plant,
            solve_settings=self.solve_settings,
            switching_settings=self.switching_tolerances,
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

    model: MechanicalCVTPlant
    solve_settings: EngagedContactSolveSettings = field(
        default_factory=EngagedContactSolveSettings
    )
    switching_settings: CVTEventSwitchingTolerances = field(
        default_factory=CVTEventSwitchingTolerances
    )
    operating_limits: CVTShiftOperatingLimits = field(init=False)
    evaluator: EngagedCVTContactEvaluator = field(init=False)
    deadzone_evaluator: DeadzoneDynamicsEvaluator = field(init=False)

    @property
    def traction_law(self):
        """Internal contact-capacity law derived from ``model.contact``."""

        return self.model.traction_law

    def __post_init__(self) -> None:
        if not isinstance(self.model, MechanicalCVTPlant):
            raise TypeError("model must be a MechanicalCVTPlant instance.")
        if not isinstance(self.solve_settings, EngagedContactSolveSettings):
            raise TypeError(
                "solve_settings must be an EngagedContactSolveSettings instance."
            )
        if not isinstance(self.switching_settings, CVTEventSwitchingTolerances):
            raise TypeError(
                "switching_settings must be a CVTEventSwitchingTolerances instance."
            )

        self.operating_limits = CVTShiftOperatingLimits.from_geometry_spec(
            self.model.geometry.spec
        )
        self.solve_settings = self.solve_settings.with_defaults_from_traction_law(
            self.traction_law
        )
        self.evaluator = EngagedCVTContactEvaluator(
            model=self.model,
            traction_law=self.traction_law,
            solve_settings=self.solve_settings,
        )
        self.deadzone_evaluator = DeadzoneDynamicsEvaluator(model=self.model)

    @staticmethod
    def _resolve_boundaries(
        *,
        time: float,
        state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues | None,
        boundary_provider: ShaftBoundaryProvider | None,
    ) -> CVTShaftBoundaryValues:
        if shaft_boundaries is not None and boundary_provider is not None:
            raise ValueError("Provide shaft_boundaries or boundary_provider, not both.")
        if boundary_provider is not None:
            value = boundary_provider(time, state)
            if not isinstance(value, CVTShaftBoundaryValues):
                raise TypeError("boundary_provider must return CVTShaftBoundaryValues.")
            return value
        if shaft_boundaries is None:
            return CVTShaftBoundaryValues.zero()
        if not isinstance(shaft_boundaries, CVTShaftBoundaryValues):
            raise TypeError("shaft_boundaries must be CVTShaftBoundaryValues.")
        return shaft_boundaries

    def _evaluate_physics(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> CVTRegimeEvaluation:
        """Evaluate active mechanics for runtime, events, or explicit inspection."""

        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("mode must be a CVTOperatingRegime instance.")

        resolved_boundaries = self._resolve_boundaries(
            time=time,
            state=state,
            shaft_boundaries=shaft_boundaries,
            boundary_provider=boundary_provider,
        )

        if mode.engagement is CVTEngagementState.DEADZONE:
            if not self.operating_limits.has_deadzone:
                raise RuntimeError(
                    "Deadzone mechanics are unreachable when lower_stop_shift equals "
                    "engagement_shift (zero-width deadzone)."
                )
            deadzone_state = CVTState.from_vector(state)
            if mode.shift_constraint is CVTShiftConstraint.FREE:
                return self.deadzone_evaluator.evaluate_free_at_time(
                    time=time,
                    state=deadzone_state,
                    shaft_boundaries=resolved_boundaries,
                )
            if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
                return self.deadzone_evaluator.evaluate_lower_stop_at_time(
                    time=time,
                    state=deadzone_state,
                    lower_stop_shift=self.operating_limits.lower_stop_shift,
                    shaft_boundaries=resolved_boundaries,
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
            shaft_boundaries=resolved_boundaries,
        )

    def evaluate_runtime(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> RuntimeEvaluation:
        """Return only what the continuous integrator needs to advance state."""

        physics = self._evaluate_physics(
            time=time,
            state=state,
            mode=mode,
            shaft_boundaries=shaft_boundaries,
            boundary_provider=boundary_provider,
        )
        return RuntimeEvaluation(state_derivative=physics.state_derivative)

    def inspect(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> CVTRegimeEvaluation:
        """Return detailed state mechanics for audit/report reconstruction.

        This is intentionally separate from :meth:`rhs`.  It exposes the
        existing closure/contact physics needed by CINDER's results layer, but
        callers should not invoke it per RHS stage.
        """

        return self._evaluate_physics(
            time=time,
            state=state,
            mode=mode,
            shaft_boundaries=shaft_boundaries,
            boundary_provider=boundary_provider,
        )

    def rhs(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
    ) -> NDArray[np.float64]:
        """Return the lean runtime derivative for the active physical regime."""

        return self.evaluate_runtime(
            time=time, state=state, mode=mode
        ).derivative_vector()

    def rhs_with_boundaries(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> NDArray[np.float64]:
        """Return the CVT derivative using externally supplied shaft boundaries."""

        return self.evaluate_runtime(
            time=time,
            state=state,
            mode=mode,
            shaft_boundaries=shaft_boundaries,
        ).derivative_vector()

    def rhs_with_boundary_provider(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        boundary_provider: ShaftBoundaryProvider,
    ) -> NDArray[np.float64]:
        """Return the CVT derivative using a state-dependent boundary provider."""

        return self.evaluate_runtime(
            time=time,
            state=state,
            mode=mode,
            boundary_provider=boundary_provider,
        ).derivative_vector()

    def events(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> tuple[HybridEvent, ...]:
        """Build exactly the physical events reachable from ``mode``."""

        del time, state
        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("mode must be a CVTOperatingRegime instance.")

        def boundaries_at(
            event_time: float, vector: NDArray[np.float64]
        ) -> CVTShaftBoundaryValues:
            return self._resolve_boundaries(
                time=event_time,
                state=vector,
                shaft_boundaries=shaft_boundaries,
                boundary_provider=boundary_provider,
            )

        if mode.engagement is CVTEngagementState.DEADZONE:
            if not self.operating_limits.has_deadzone:
                raise RuntimeError(
                    "Deadzone mode is unreachable when lower_stop_shift equals "
                    "engagement_shift (zero-width deadzone)."
                )
            if mode.shift_constraint is CVTShiftConstraint.FREE:
                return build_deadzone_free_boundary_events(limits=self.operating_limits)
            if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
                return (
                    build_lower_stop_release_event(
                        closing_reaction=lambda event_time, vector: self._lower_stop_reaction(
                            time=event_time,
                            vector=vector,
                            shaft_boundaries=boundaries_at(event_time, vector),
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
                shaft_boundaries=boundaries_at(event_time, vector),
            ),
            traction_law=self.traction_law,
            switching_settings=self.switching_settings,
            relative_speed_tolerance=self.solve_settings.contact_tolerances.relative_speed_tolerance,
            relative_acceleration_tolerance=self.solve_settings.contact_tolerances.relative_acceleration_tolerance,
            include_shift_boundary_events=False,
            include_primary_normal_floor=(
                mode.shift_constraint is not CVTShiftConstraint.LOW_RATIO_SEAT
            ),
        )

        if mode.shift_constraint is CVTShiftConstraint.FREE:
            return contact_events + build_engaged_free_boundary_events(
                limits=self.operating_limits
            )

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            return contact_events + build_low_ratio_seat_events(
                primary_separation=lambda event_time, vector: self._primary_separation_indicator(
                    time=event_time,
                    vector=vector,
                    contact_regime=mode.contact_regime,
                    shaft_boundaries=boundaries_at(event_time, vector),
                ),
                closing_reaction=lambda event_time, vector: self._low_ratio_seat_reaction(
                    time=event_time,
                    vector=vector,
                    contact_regime=mode.contact_regime,
                    shaft_boundaries=boundaries_at(event_time, vector),
                ),
                include_primary_separation=self.operating_limits.has_deadzone,
            )

        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            return contact_events + (
                build_upper_stop_release_event(
                    opening_reaction=lambda event_time, vector: self._upper_stop_reaction(
                        time=event_time,
                        vector=vector,
                        contact_regime=mode.contact_regime,
                        shaft_boundaries=boundaries_at(event_time, vector),
                    )
                ),
            )
        raise RuntimeError(
            f"Unsupported engaged shift constraint: {mode.shift_constraint!r}."
        )

    def events_with_boundaries(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> tuple[HybridEvent, ...]:
        return self.events(
            time=time,
            state=state,
            mode=mode,
            shaft_boundaries=shaft_boundaries,
        )

    def events_with_boundary_provider(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        boundary_provider: ShaftBoundaryProvider,
    ) -> tuple[HybridEvent, ...]:
        return self.events(
            time=time,
            state=state,
            mode=mode,
            boundary_provider=boundary_provider,
        )

    def transition(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        fired_event_names: tuple[str, ...],
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> HybridTransition[CVTOperatingRegime]:
        """Resolve event successors and explicit impact/capture resets."""

        resolved_boundaries = self._resolve_boundaries(
            time=time,
            state=state,
            shaft_boundaries=shaft_boundaries,
            boundary_provider=boundary_provider,
        )
        return resolve_cvt_operating_transition(
            evaluator=self.evaluator,
            deadzone_evaluator=self.deadzone_evaluator,
            time=time,
            vector=state,
            old_regime=mode,
            fired_event_names=fired_event_names,
            limits=self.operating_limits,
            switching_settings=self.switching_settings,
            shaft_boundaries=resolved_boundaries,
        )

    def transition_with_boundaries(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        fired_event_names: tuple[str, ...],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> HybridTransition[CVTOperatingRegime]:
        return self.transition(
            time=time,
            state=state,
            mode=mode,
            fired_event_names=fired_event_names,
            shaft_boundaries=shaft_boundaries,
        )

    def transition_with_boundary_provider(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: CVTOperatingRegime,
        fired_event_names: tuple[str, ...],
        boundary_provider: ShaftBoundaryProvider,
    ) -> HybridTransition[CVTOperatingRegime]:
        return self.transition(
            time=time,
            state=state,
            mode=mode,
            fired_event_names=fired_event_names,
            boundary_provider=boundary_provider,
        )

    def classify_initial_regime_at_time(
        self,
        *,
        time: float,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> CVTOperatingRegime:
        """Classify an initial state at an explicit simulation time."""

        if not isinstance(state, CVTState):
            raise TypeError("state must be a CVTState instance.")
        resolved_boundaries = self._resolve_boundaries(
            time=time,
            state=state.as_vector(),
            shaft_boundaries=shaft_boundaries,
            boundary_provider=boundary_provider,
        )
        mode = classify_initial_cvt_regime(
            evaluator=self.evaluator,
            time=time,
            state=state,
            limits=self.operating_limits,
            switching_settings=self.switching_settings,
            shaft_boundaries=resolved_boundaries,
        )
        self._validate_initial_mode_state(
            time=time,
            mode=mode,
            state=state,
            shaft_boundaries=resolved_boundaries,
        )
        return self._release_inadmissible_initial_stop(
            time=time,
            mode=mode,
            state=state,
            shaft_boundaries=resolved_boundaries,
        )

    def classify_initial_regime(
        self,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
        boundary_provider: ShaftBoundaryProvider | None = None,
    ) -> CVTOperatingRegime:
        """Classify a standalone initial state at the explicit local origin t=0."""

        return self.classify_initial_regime_at_time(
            time=0.0,
            state=state,
            shaft_boundaries=shaft_boundaries,
            boundary_provider=boundary_provider,
        )

    def integrate(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: CVTState,
        initial_regime: CVTOperatingRegime | None = None,
        settings: HybridIntegratorSettings = HybridIntegratorSettings(),
    ) -> HybridIntegrationResult[CVTOperatingRegime]:
        """Integrate all currently implemented operating regimes."""

        if not isinstance(initial_state, CVTState):
            raise TypeError("initial_state must be a CVTState instance.")
        start_time = float(time_span[0])
        mode = initial_regime or self.classify_initial_regime_at_time(
            time=start_time, state=initial_state
        )
        if not isinstance(mode, CVTOperatingRegime):
            raise TypeError("initial_regime must be a CVTOperatingRegime instance.")
        self._validate_initial_mode_state(
            time=start_time, mode=mode, state=initial_state
        )
        mode = self._release_inadmissible_initial_stop(
            time=start_time, mode=mode, state=initial_state
        )
        self._validate_initial_mode_state(
            time=start_time, mode=mode, state=initial_state
        )

        return integrate_hybrid(
            system=self,
            time_span=time_span,
            initial_state=initial_state.as_vector(),
            initial_mode=mode,
            settings=settings,
        )

    def integrate_trace(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: CVTState,
        initial_regime: CVTOperatingRegime | None = None,
        settings: HybridIntegratorSettings = HybridIntegratorSettings(),
    ) -> "CVTIntegrationTrace":
        """Return the raw segment-preserving trace without report materialization."""

        from cinder.results import CVTIntegrationTrace

        return CVTIntegrationTrace(
            raw=self.integrate(
                time_span=time_span,
                initial_state=initial_state,
                initial_regime=initial_regime,
                settings=settings,
            )
        )

    def run(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: CVTState,
        initial_regime: CVTOperatingRegime | None = None,
        settings: HybridIntegratorSettings = HybridIntegratorSettings(),
        reporting_settings: "ReportingSettings | None" = None,
    ) -> "CVTIntegrationResult":
        """Integrate once, then materialize a user-facing result.

        When ``reporting_settings`` is omitted, CINDER returns the standard
        10 ms uniform report grid while preserving the adaptive raw trace in
        ``result.trace``.  Use ``ReportingSettings.native()`` for an
        accepted-step report, or ``integrate_trace()`` for no report pass.
        """

        from cinder.results import CVTResultBuilder, ReportingSettings

        if reporting_settings is None:
            reporting_settings = ReportingSettings.standard()
        if not isinstance(reporting_settings, ReportingSettings):
            raise TypeError("reporting_settings must be a ReportingSettings instance.")
        integration_settings = settings
        if (
            reporting_settings.grid.requires_dense_output
            and not settings.retain_dense_output
        ):
            integration_settings = replace(settings, retain_dense_output=True)
        return CVTResultBuilder(system=self).build(
            self.integrate_trace(
                time_span=time_span,
                initial_state=initial_state,
                initial_regime=initial_regime,
                settings=integration_settings,
            ),
            settings=reporting_settings,
        )

    def _lower_stop_reaction(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> float:
        state = CVTState.from_vector(vector)
        evaluation = self.deadzone_evaluator.evaluate_lower_stop_at_time(
            time=time,
            state=state,
            lower_stop_shift=self.operating_limits.lower_stop_shift,
            shaft_boundaries=shaft_boundaries,
        )
        reaction = evaluation.stop_reaction
        if reaction is None:  # pragma: no cover - lower-stop evaluator invariant.
            raise RuntimeError("Lower-stop evaluation did not recover a stop reaction.")
        return reaction

    def _primary_separation_indicator(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        contact_regime: ContactRegime,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> float:
        """Return the low-seat primary unilateral separation indicator."""

        indicator, _normal, _opening_acceleration = (
            primary_contact_separation_at_engagement(
                evaluator=self.evaluator,
                time=time,
                vector=vector,
                contact_regime=contact_regime,
                limits=self.operating_limits,
                switching_settings=self.switching_settings,
                shaft_boundaries=shaft_boundaries,
            )
        )
        return indicator

    def _low_ratio_seat_reaction(
        self,
        *,
        time: float,
        vector: NDArray[np.float64],
        contact_regime: ContactRegime,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> float:
        evaluation = self.evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=contact_regime,
            shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
            shaft_boundaries=shaft_boundaries,
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
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> float:
        evaluation = self.evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=contact_regime,
            shift_constraint=EngagedShiftConstraint.UPPER_STOP,
            shaft_boundaries=shaft_boundaries,
        )
        reaction = evaluation.upper_stop_reaction
        if reaction is None:  # pragma: no cover - constrained evaluator invariant.
            raise RuntimeError("Upper-stop closure did not return a stop reaction.")
        return reaction

    def _release_inadmissible_initial_stop(
        self,
        *,
        time: float,
        mode: CVTOperatingRegime,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ) -> CVTOperatingRegime:
        """Return a free mode when an initial unilateral stop would pull.

        This does not reset state: the supplied initial condition is already
        at zero shift speed by the stop-state validation below.  The successor
        free RHS supplies the inward acceleration on its first integration
        stage.
        """

        if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
            reaction = self.deadzone_evaluator.evaluate_lower_stop_at_time(
                time=time,
                state=state,
                lower_stop_shift=self.operating_limits.lower_stop_shift,
                shaft_boundaries=shaft_boundaries,
            ).stop_reaction
            assert reaction is not None
            if reaction < 0.0:
                return CVTOperatingRegime.deadzone_free()
            return mode

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            assert mode.contact_regime is not None
            if self.operating_limits.has_deadzone:
                separation = self._primary_separation_indicator(
                    time=time,
                    vector=state.as_vector(),
                    contact_regime=mode.contact_regime,
                    shaft_boundaries=shaft_boundaries,
                )
                if separation <= 0.0:
                    return CVTOperatingRegime.deadzone_free()
            reaction = self._low_ratio_seat_reaction(
                time=time,
                vector=state.as_vector(),
                contact_regime=mode.contact_regime,
                shaft_boundaries=shaft_boundaries,
            )
            if reaction < 0.0:
                return CVTOperatingRegime.engaged_free(
                    contact_regime=mode.contact_regime,
                )
            return mode

        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            assert mode.contact_regime is not None
            reaction = self._upper_stop_reaction(
                time=time,
                vector=state.as_vector(),
                contact_regime=mode.contact_regime,
                shaft_boundaries=shaft_boundaries,
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
        time: float,
        mode: CVTOperatingRegime,
        state: CVTState,
        shaft_boundaries: CVTShaftBoundaryValues | None = None,
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
            if not self.operating_limits.has_deadzone:
                raise ValueError(
                    "A zero-width deadzone topology cannot start in DEADZONE mode."
                )
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
                self.deadzone_evaluator.snapshot_at_time(
                    time=time,
                    state=state,
                    shaft_boundaries=shaft_boundaries,
                )
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
                self.deadzone_evaluator.snapshot_at_time(
                    time=time,
                    state=state,
                    shaft_boundaries=shaft_boundaries,
                )
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
