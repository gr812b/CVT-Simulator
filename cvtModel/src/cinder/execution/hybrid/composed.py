"""Composition layer that hosts a five-state CVT plant in a larger system."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray

from cinder.core import StateBlock, StateLayout
from cinder.hosts import CVTHost, NoHost
from cinder.model.boundaries import (
    FixedShaftBoundary,
    ShaftBoundary,
    ShaftBoundaryContext,
)
from cinder.model.system import CVTShaftBoundaryValues, CVTState, MechanicalCVTPlant

from .cvt_operating_hybrid import CVTOperatingHybridSystem
from .cvt_regime import CVTOperatingRegime
from .hybrid import HybridEvent, HybridTransition


@dataclass(frozen=True, slots=True)
class ComposedCVTMode:
    """Hybrid mode for a composed CVT-host system."""

    cvt: CVTOperatingRegime
    host: Any | None = None


@dataclass(slots=True)
class ComposedCVTHybridSystem:
    """Generic host around :class:`CVTOperatingHybridSystem`.

    The flat state always contains a ``cvt`` block and one host block. The CVT
    block is five entries; the host block is supplied by the host object.
    """

    cvt: CVTOperatingHybridSystem
    primary_boundary: ShaftBoundary = field(default_factory=FixedShaftBoundary)
    secondary_boundary: ShaftBoundary = field(default_factory=FixedShaftBoundary)
    host: CVTHost = field(default_factory=NoHost)
    layout: StateLayout = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.cvt, CVTOperatingHybridSystem):
            raise TypeError("cvt must be a CVTOperatingHybridSystem.")
        if not callable(getattr(self.primary_boundary, "evaluate", None)):
            raise TypeError("primary_boundary must provide evaluate(context).")
        if not callable(getattr(self.secondary_boundary, "evaluate", None)):
            raise TypeError("secondary_boundary must provide evaluate(context).")
        if not callable(getattr(self.host, "rhs", None)):
            raise TypeError("host must implement the CVTHost contract.")
        self.layout = StateLayout(StateBlock("cvt", 5), self.host.state_block)

    @classmethod
    def from_plant(
        cls,
        *,
        plant: MechanicalCVTPlant,
        solve_settings=None,
        switching_tolerances=None,
        primary_boundary: ShaftBoundary | None = None,
        secondary_boundary: ShaftBoundary | None = None,
        host: CVTHost | None = None,
    ) -> "ComposedCVTHybridSystem":
        """Build a composed system with physics-derived solver defaults.

        ``plant`` supplies shift limits and contact physics. Optional
        ``solve_settings`` and ``switching_tolerances`` are numerical overrides;
        physical shift stops are always read from the plant geometry.
        """

        cvt = CVTOperatingHybridSystem(
            model=plant,
            **({} if solve_settings is None else {"solve_settings": solve_settings}),
            **(
                {}
                if switching_tolerances is None
                else {"switching_settings": switching_tolerances}
            ),
        )
        return cls(
            cvt=cvt,
            primary_boundary=primary_boundary or FixedShaftBoundary(),
            secondary_boundary=secondary_boundary or FixedShaftBoundary(),
            host=host or NoHost(),
        )

    def initial_state(
        self, *, cvt_state: CVTState, host_state: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        return self.layout.pack(
            cvt=cvt_state.as_vector(), **{self.host.state_block.name: host_state}
        )

    def classify_initial_mode_at_time(
        self, *, time: float, state: NDArray[np.float64]
    ) -> ComposedCVTMode:
        """Classify a composed initial state at an explicit simulation time."""

        cvt_state = CVTState.from_vector(self.layout.view(state, "cvt"))
        shaft_values = self._shaft_boundaries(time=time, state=state)
        return ComposedCVTMode(
            cvt=self.cvt.classify_initial_regime_at_time(
                time=time,
                state=cvt_state,
                shaft_boundaries=shaft_values,
            )
        )

    def classify_initial_mode(self, state: NDArray[np.float64]) -> ComposedCVTMode:
        """Classify a standalone initial state at the explicit local origin t=0."""

        return self.classify_initial_mode_at_time(time=0.0, state=state)

    def rhs(
        self, time: float, state: NDArray[np.float64], mode: ComposedCVTMode
    ) -> NDArray[np.float64]:
        cvt_vector = self.layout.view(state, "cvt")
        host_vector = self.layout.view(state, self.host.state_block.name)
        cvt_state = CVTState.from_vector(cvt_vector)
        shaft_values = self._shaft_boundaries(time=time, state=state)
        dy_cvt = self.cvt.rhs_with_boundaries(
            time=time,
            state=cvt_vector,
            mode=mode.cvt,
            shaft_boundaries=shaft_values,
        )
        dy_host = self.host.rhs(
            time=time,
            cvt_state=cvt_state,
            host_state=host_vector,
            shaft_boundaries=shaft_values,
        )
        return self.layout.pack(cvt=dy_cvt, **{self.host.state_block.name: dy_host})

    def events(
        self, time: float, state: NDArray[np.float64], mode: ComposedCVTMode
    ) -> Sequence[HybridEvent]:
        cvt_vector = self.layout.view(state, "cvt")
        shaft_values = self._shaft_boundaries(time=time, state=state)
        cvt_events = self.cvt.events_with_boundaries(
            time=time,
            state=cvt_vector,
            mode=mode.cvt,
            shaft_boundaries=shaft_values,
        )
        lifted = [self._lift_cvt_event(event=event, mode=mode) for event in cvt_events]
        cvt_state = CVTState.from_vector(cvt_vector)
        host_vector = self.layout.view(state, self.host.state_block.name)
        host_events = self.host.events(
            time=time,
            cvt_state=cvt_state,
            host_state=host_vector,
            shaft_boundaries=shaft_values,
        )
        return tuple(lifted) + tuple(
            self._lift_host_event(event) for event in host_events
        )

    def transition(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ComposedCVTMode,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[ComposedCVTMode]:
        cvt_fired = tuple(
            name.removeprefix("cvt:")
            for name in fired_event_names
            if name.startswith("cvt:")
        )
        host_fired = tuple(
            name.removeprefix("host:")
            for name in fired_event_names
            if name.startswith("host:")
        )
        successor = np.array(state, dtype=float, copy=True)
        next_cvt_mode = mode.cvt
        reason_parts: list[str] = []
        metadata: dict[str, Any] = {}

        if cvt_fired:
            cvt_transition = self.cvt.transition_with_boundaries(
                time=time,
                state=self.layout.view(state, "cvt"),
                mode=mode.cvt,
                fired_event_names=cvt_fired,
                shaft_boundaries=self._shaft_boundaries(time=time, state=state),
            )
            reason_parts.append(cvt_transition.reason)
            metadata["cvt"] = cvt_transition.metadata
            if cvt_transition.terminates:
                return HybridTransition(
                    next_mode=None,
                    reason=cvt_transition.reason,
                    metadata=metadata,
                    successor_state=state,
                )
            assert cvt_transition.next_mode is not None
            next_cvt_mode = cvt_transition.next_mode
            if cvt_transition.successor_state is not None:
                successor = self.layout.replace_block(
                    successor, "cvt", cvt_transition.successor_state
                )

        if host_fired:
            cvt_state = CVTState.from_vector(self.layout.view(successor, "cvt"))
            host_vector = self.layout.view(successor, self.host.state_block.name)
            host_transition = self.host.transition(
                time=time,
                cvt_state=cvt_state,
                host_state=host_vector,
                shaft_boundaries=self._shaft_boundaries(time=time, state=successor),
                fired_event_names=host_fired,
            )
            if host_transition is not None:
                reason_parts.append(host_transition.reason)
                metadata["host"] = host_transition.metadata
                if host_transition.terminates:
                    return HybridTransition(
                        next_mode=None,
                        reason=host_transition.reason,
                        metadata=metadata,
                        successor_state=successor,
                    )
                if host_transition.successor_state is not None:
                    successor = self.layout.replace_block(
                        successor,
                        self.host.state_block.name,
                        host_transition.successor_state,
                    )

        reason = "; ".join(reason_parts) or "composed_transition"
        successor.setflags(write=False)
        return HybridTransition(
            next_mode=ComposedCVTMode(cvt=next_cvt_mode, host=mode.host),
            reason=reason,
            metadata=metadata,
            successor_state=successor,
        )

    def integrate_trace(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: NDArray[np.float64],
        initial_mode: ComposedCVTMode | None = None,
        settings=None,
    ):
        """Return a raw trace for this composed CVT-host system."""

        from cinder.execution.hybrid.hybrid import (
            HybridIntegratorSettings,
            integrate_hybrid,
        )
        from cinder.results import CVTIntegrationTrace

        if settings is None:
            settings = HybridIntegratorSettings()
        mode = initial_mode or self.classify_initial_mode_at_time(
            time=float(time_span[0]), state=initial_state
        )
        return CVTIntegrationTrace(
            raw=integrate_hybrid(
                system=self,
                time_span=time_span,
                initial_state=initial_state,
                initial_mode=mode,
                settings=settings,
            )
        )

    def run(
        self,
        *,
        time_span: tuple[float, float],
        initial_state: NDArray[np.float64],
        initial_mode: ComposedCVTMode | None = None,
        settings=None,
        reporting_settings=None,
    ):
        """Integrate and materialize report signals for a composed system."""

        from cinder.execution.hybrid.hybrid import HybridIntegratorSettings
        from cinder.results import CVTResultBuilder, ReportingSettings

        if settings is None:
            settings = HybridIntegratorSettings()
        if reporting_settings is None:
            reporting_settings = ReportingSettings.standard()
        if (
            reporting_settings.grid.requires_dense_output
            and not settings.retain_dense_output
        ):
            settings = replace(settings, retain_dense_output=True)
        return CVTResultBuilder(system=self).build(
            self.integrate_trace(
                time_span=time_span,
                initial_state=initial_state,
                initial_mode=initial_mode,
                settings=settings,
            ),
            settings=reporting_settings,
        )

    def _lift_cvt_event(
        self, *, event: HybridEvent, mode: ComposedCVTMode
    ) -> HybridEvent:
        def callback(time: float, state: NDArray[np.float64]) -> float:
            cvt_vector = self.layout.view(state, "cvt")
            # Rebuild the CVT event with the boundary values at the full state
            # being tested by the root finder.
            shaft_values = self._shaft_boundaries(time=time, state=state)
            matching = {
                inner.name: inner
                for inner in self.cvt.events_with_boundaries(
                    time=time,
                    state=cvt_vector,
                    mode=mode.cvt,
                    shaft_boundaries=shaft_values,
                )
            }
            return matching[event.name].function(time, cvt_vector)

        return HybridEvent(
            name=f"cvt:{event.name}",
            function=callback,
            direction=event.direction,
            terminal=event.terminal,
        )

    @staticmethod
    def _lift_host_event(event: HybridEvent) -> HybridEvent:
        return HybridEvent(
            name=f"host:{event.name}",
            function=event.function,
            direction=event.direction,
            terminal=event.terminal,
        )

    def _shaft_boundaries(
        self, *, time: float, state: NDArray[np.float64]
    ) -> CVTShaftBoundaryValues:
        cvt_vector = self.layout.view(state, "cvt")
        host_vector = self.layout.view(state, self.host.state_block.name)
        cvt_state = CVTState.from_vector(cvt_vector)
        host_context = self.host.context(
            time=time,
            cvt_state=cvt_state,
            host_state=host_vector,
        )
        primary = self.primary_boundary.evaluate(
            ShaftBoundaryContext(
                time=time, cvt=cvt_state, shaft="primary", host=host_context
            )
        )
        secondary = self.secondary_boundary.evaluate(
            ShaftBoundaryContext(
                time=time, cvt=cvt_state, shaft="secondary", host=host_context
            )
        )
        return CVTShaftBoundaryValues(primary=primary, secondary=secondary)
