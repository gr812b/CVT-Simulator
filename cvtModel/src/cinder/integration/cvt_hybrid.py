"""Engaged-CVT implementation of the generic segmented hybrid interface."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from cinder.contact import ContactRegime, ContactTractionLaw
from cinder.dynamics.engaged_contact import EngagedContactSolveSettings
from cinder.dynamics.snapshot import CVTDynamicsModel

from .cvt_contact import EngagedCVTContactEvaluator
from .cvt_contact_events import build_cvt_contact_events
from .cvt_contact_switching import (
    CVTContactSwitchSettings,
    resolve_cvt_contact_transition,
)
from .cvt_shift_limits import EngagedShiftTravelLimits
from .hybrid import (
    HybridEvent,
    HybridIntegrationResult,
    HybridIntegratorSettings,
    HybridTransition,
    integrate_hybrid,
)
from .state import CVTDynamicState


@dataclass(slots=True)
class EngagedCVTHybridSystem:
    """Hybrid adapter for the already-derived *engaged* CVT contact model.

    This class owns CVT-specific branch evaluation, events, and transitions.
    It intentionally contains no segmented-solver loop; the reusable loop is
    :func:`cinder.integration.hybrid.integrate_hybrid`.

    Deadzone and contact-loss dynamics remain separate future systems.  Their
    boundaries are currently terminal guards rather than silently continued
    under the engaged-wrap equations.
    """

    model: CVTDynamicsModel
    traction_law: ContactTractionLaw
    solve_settings: EngagedContactSolveSettings
    switching_settings: CVTContactSwitchSettings = field(
        default_factory=CVTContactSwitchSettings
    )
    shift_travel_limits: EngagedShiftTravelLimits | None = None
    evaluator: EngagedCVTContactEvaluator = field(init=False)

    def __post_init__(self) -> None:
        limits = (
            self.shift_travel_limits
            or EngagedShiftTravelLimits.from_geometry_spec(self.model.geometry.spec)
        )
        limits.validate_against_geometry_spec(self.model.geometry.spec)
        self.shift_travel_limits = limits
        self.evaluator = EngagedCVTContactEvaluator(
            model=self.model,
            traction_law=self.traction_law,
            solve_settings=self.solve_settings,
        )

    def rhs(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ContactRegime,
    ) -> NDArray[np.float64]:
        """Return the active branch's six ODE derivatives."""

        return self.evaluator.rhs_vector(time=time, vector=state, regime=mode)

    def events(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ContactRegime,
    ) -> tuple[HybridEvent, ...]:
        """Build branch-specific contact and engaged-domain terminal events."""

        assert self.shift_travel_limits is not None
        return build_cvt_contact_events(
            regime=mode,
            evaluate=lambda event_time, vector: self.evaluator.evaluate_vector(
                time=event_time,
                vector=vector,
                regime=mode,
            ),
            traction_law=self.traction_law,
            switching_settings=self.switching_settings,
            relative_speed_tolerance=self.solve_settings.contact_tolerances.relative_speed_tolerance,
            relative_acceleration_tolerance=self.solve_settings.contact_tolerances.relative_acceleration_tolerance,
            minimum_shift=self.shift_travel_limits.minimum_shift,
            maximum_shift=self.shift_travel_limits.maximum_shift,
        )

    def transition(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ContactRegime,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[ContactRegime]:
        """Resolve an event-guided engaged-contact regime transition."""

        return resolve_cvt_contact_transition(
            evaluator=self.evaluator,
            time=time,
            vector=state,
            old_regime=mode,
            fired_event_names=fired_event_names,
            switching_settings=self.switching_settings,
        )

    def classify_initial_regime(self, state: CVTDynamicState) -> ContactRegime:
        """Classify an already-engaged initial state without deadzone logic."""

        return self.evaluator.classify_initial_regime(
            state=state,
            switching_settings=self.switching_settings,
        )

    def integrate(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: CVTDynamicState,
        initial_regime: ContactRegime | None = None,
        settings: HybridIntegratorSettings = HybridIntegratorSettings(),
    ) -> HybridIntegrationResult[ContactRegime]:
        """Convenience wrapper around the generic segmented integration loop."""

        assert self.shift_travel_limits is not None
        if not self.shift_travel_limits.contains_strictly(initial_state.shift_position):
            raise ValueError(
                "A free engaged integration must start strictly between physical shift "
                "stops; use a future constrained-stop model for an initial stop state."
            )
        regime = initial_regime or self.classify_initial_regime(initial_state)
        return integrate_hybrid(
            system=self,
            time_span=time_span,
            initial_state=initial_state.as_vector(),
            initial_mode=regime,
            settings=settings,
        )
