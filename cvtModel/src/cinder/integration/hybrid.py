"""Generic segmented hybrid ODE orchestration with no CVT-specific knowledge."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Callable, Generic, Mapping, Protocol, Sequence, TypeVar

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.integrate import solve_ivp

ModeT = TypeVar("ModeT")

HybridRhs = Callable[[float, NDArray[np.float64]], NDArray[np.float64]]
HybridEventFunction = Callable[[float, NDArray[np.float64]], float]


def _require_finite_positive(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and strictly positive.")


@dataclass(frozen=True, slots=True)
class HybridEvent:
    """One named scalar event supplied by a domain-specific hybrid system."""

    name: str
    function: HybridEventFunction
    direction: float = 0.0
    terminal: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("HybridEvent.name must be non-empty.")
        if not callable(self.function):
            raise TypeError("HybridEvent.function must be callable.")
        if not isfinite(self.direction) or self.direction not in (-1.0, 0.0, 1.0):
            raise ValueError("HybridEvent.direction must be -1, 0, or +1.")
        if not isinstance(self.terminal, bool):
            raise TypeError("HybridEvent.terminal must be bool.")

    def as_scipy(self) -> HybridEventFunction:
        """Return a solve_ivp-compatible callable with event attributes."""

        def callback(time: float, state: NDArray[np.float64]) -> float:
            value = float(self.function(time, state))
            if not isfinite(value):
                raise FloatingPointError(
                    f"Hybrid event {self.name!r} returned a non-finite value."
                )
            return value

        callback.direction = self.direction  # type: ignore[attr-defined]
        callback.terminal = self.terminal  # type: ignore[attr-defined]
        return callback


@dataclass(frozen=True, slots=True)
class HybridTransition(Generic[ModeT]):
    """One transition decision emitted after one or more terminal events.

    ``successor_state`` is an optional explicit post-event state.  It keeps
    impact, capture, and constraint projections out of a continuous RHS while
    remaining generic: the hybrid runner neither knows nor assumes why a
    domain system changed the state.
    """

    next_mode: ModeT | None
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    successor_state: ArrayLike | None = None

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("HybridTransition.reason must be non-empty.")
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.successor_state is not None:
            state = np.asarray(self.successor_state, dtype=float)
            if state.ndim != 1 or state.size == 0 or not np.all(np.isfinite(state)):
                raise ValueError(
                    "HybridTransition.successor_state must be a non-empty finite vector."
                )
            frozen = np.array(state, dtype=float, copy=True)
            frozen.setflags(write=False)
            object.__setattr__(self, "successor_state", frozen)

    @property
    def terminates(self) -> bool:
        """Return whether this transition intentionally ends the run."""

        return self.next_mode is None

    @property
    def has_successor_state(self) -> bool:
        """Return whether the transition explicitly projected/reset the state."""

        return self.successor_state is not None


class HybridSystem(Protocol[ModeT]):
    """Minimal domain adapter consumed by :func:`integrate_hybrid`.

    The generic runner only sees a vector state, a mode object, ODE RHS values,
    named terminal events, and a transition decision.  Vehicle, CVT, contact,
    suspension, or controller logic belongs in the adapter implementation.
    """

    def rhs(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ModeT,
    ) -> NDArray[np.float64]:
        """Return a derivative vector for the active mode."""

    def events(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ModeT,
    ) -> Sequence[HybridEvent]:
        """Build the currently active terminal event set."""

    def transition(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: ModeT,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[ModeT]:
        """Resolve event-guided mode changes at a segment endpoint."""


@dataclass(frozen=True, slots=True)
class HybridIntegratorSettings:
    """Numerical controls shared by generic segmented solve_ivp integration."""

    relative_tolerance: float = 1.0e-7
    absolute_tolerance: float = 1.0e-9
    method: str = "RK45"
    max_step: float = np.inf
    first_step: float | None = None
    maximum_transitions: int = 100
    event_time_tolerance: float = 1.0e-10

    def __post_init__(self) -> None:
        _require_finite_positive(
            relative_tolerance=self.relative_tolerance,
            absolute_tolerance=self.absolute_tolerance,
            event_time_tolerance=self.event_time_tolerance,
        )
        if not self.method:
            raise ValueError("method must be non-empty.")
        if not isfinite(self.max_step) and self.max_step != float("inf"):
            raise ValueError("max_step must be finite and positive or infinity.")
        if self.max_step <= 0.0:
            raise ValueError("max_step must be strictly positive.")
        if self.first_step is not None:
            _require_finite_positive(first_step=self.first_step)
        if self.maximum_transitions < 1:
            raise ValueError("maximum_transitions must be at least one.")


@dataclass(frozen=True, slots=True)
class HybridSegment(Generic[ModeT]):
    """One contiguous solve_ivp interval integrated under a fixed mode."""

    mode: ModeT
    time: NDArray[np.float64]
    state: NDArray[np.float64]
    fired_event_names: tuple[str, ...] = ()
    transition: HybridTransition[ModeT] | None = None

    def __post_init__(self) -> None:
        time = _immutable_vector(self.time, name="HybridSegment.time")
        state = np.asarray(self.state, dtype=float)
        if state.ndim != 2 or state.shape[1] != time.size:
            raise ValueError("HybridSegment.state must have shape (n_state, n_time).")
        if not np.all(np.isfinite(state)):
            raise ValueError("HybridSegment.state must contain only finite values.")
        frozen_state = np.array(state, dtype=float, copy=True)
        frozen_state.setflags(write=False)
        if len(set(self.fired_event_names)) != len(self.fired_event_names):
            raise ValueError("HybridSegment.fired_event_names must not contain duplicates.")
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "state", frozen_state)

    @property
    def start_time(self) -> float:
        return float(self.time[0])

    @property
    def end_time(self) -> float:
        return float(self.time[-1])


@dataclass(frozen=True, slots=True)
class HybridTransitionRecord(Generic[ModeT]):
    """Immutable mode-change or intentional-stop record.

    ``post_transition_state`` is recorded separately because a reset can make
    the state discontinuous at one time instant. Segment histories retain the
    pre-event solution produced by ``solve_ivp``; consumers that need impact
    data should inspect this record rather than silently losing the jump.
    """

    time: float
    previous_mode: ModeT
    fired_event_names: tuple[str, ...]
    transition: HybridTransition[ModeT]
    post_transition_state: NDArray[np.float64]

    def __post_init__(self) -> None:
        if not isfinite(self.time):
            raise ValueError("transition time must be finite.")
        if not self.fired_event_names:
            raise ValueError("transition record requires at least one event name.")
        state = _immutable_vector(
            self.post_transition_state,
            name="HybridTransitionRecord.post_transition_state",
        )
        object.__setattr__(self, "post_transition_state", state)


@dataclass(frozen=True, slots=True)
class HybridIntegrationResult(Generic[ModeT]):
    """Segment-preserving result of a generic hybrid integration."""

    segments: tuple[HybridSegment[ModeT], ...]
    transitions: tuple[HybridTransitionRecord[ModeT], ...]
    completed: bool
    termination_reason: str

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("HybridIntegrationResult requires at least one segment.")
        if not self.termination_reason:
            raise ValueError("termination_reason must be non-empty.")

    @property
    def final_time(self) -> float:
        return self.segments[-1].end_time

    @property
    def final_state(self) -> NDArray[np.float64]:
        """Return the latest physical state, including a terminal reset if present."""

        if self.transitions and self.transitions[-1].time == self.final_time:
            return self.transitions[-1].post_transition_state
        values = np.array(self.segments[-1].state[:, -1], dtype=float, copy=True)
        values.setflags(write=False)
        return values

    def concatenated_time(self) -> NDArray[np.float64]:
        """Return segment times with duplicate event endpoints removed."""

        parts = [self.segments[0].time]
        for segment in self.segments[1:]:
            parts.append(segment.time[1:])
        values = np.concatenate(parts)
        values.setflags(write=False)
        return values

    def concatenated_state(self) -> NDArray[np.float64]:
        """Return state history aligned with :meth:`concatenated_time`."""

        parts = [self.segments[0].state]
        for segment in self.segments[1:]:
            parts.append(segment.state[:, 1:])
        values = np.concatenate(parts, axis=1)
        values.setflags(write=False)
        return values


def integrate_hybrid(
    *,
    system: HybridSystem[ModeT],
    time_span: tuple[float, float],
    initial_state: ArrayLike,
    initial_mode: ModeT,
    settings: HybridIntegratorSettings = HybridIntegratorSettings(),
) -> HybridIntegrationResult[ModeT]:
    """Integrate one domain adapter through terminal event-driven segments.

    No assumptions are made about state dimension, mode type, force model, or
    event meaning.  The adapter owns all domain mechanics and transition
    policy; this function owns only solve_ivp segmentation and result assembly.
    """

    if not isinstance(settings, HybridIntegratorSettings):
        raise TypeError("settings must be a HybridIntegratorSettings instance.")
    start_time, final_time = (float(time_span[0]), float(time_span[1]))
    if not isfinite(start_time) or not isfinite(final_time) or final_time <= start_time:
        raise ValueError("time_span must be finite with final time greater than start time.")

    current_time = start_time
    current_state = _mutable_vector(initial_state, name="initial_state")
    current_mode = initial_mode
    segments: list[HybridSegment[ModeT]] = []
    transitions: list[HybridTransitionRecord[ModeT]] = []

    for _ in range(settings.maximum_transitions + 1):
        active_events = tuple(system.events(current_time, current_state, current_mode))
        _validate_event_names(active_events)
        scipy_events = tuple(event.as_scipy() for event in active_events)

        solution = solve_ivp(
            lambda time, state: _coerce_rhs(
                system.rhs(time, state, current_mode),
                state_size=current_state.size,
            ),
            (current_time, final_time),
            current_state,
            method=settings.method,
            rtol=settings.relative_tolerance,
            atol=settings.absolute_tolerance,
            max_step=settings.max_step,
            first_step=settings.first_step,
            events=scipy_events if scipy_events else None,
        )
        if not solution.success:
            raise RuntimeError(f"solve_ivp failed: {solution.message}")

        event_names = _fired_event_names(
            solution=solution,
            events=active_events,
            tolerance=settings.event_time_tolerance,
        )

        if not event_names:
            segments.append(
                HybridSegment(
                    mode=current_mode,
                    time=solution.t,
                    state=solution.y,
                )
            )
            return HybridIntegrationResult(
                segments=tuple(segments),
                transitions=tuple(transitions),
                completed=True,
                termination_reason="final_time_reached",
            )

        transition = system.transition(
            float(solution.t[-1]),
            np.asarray(solution.y[:, -1], dtype=float),
            current_mode,
            event_names,
        )
        segment = HybridSegment(
            mode=current_mode,
            time=solution.t,
            state=solution.y,
            fired_event_names=event_names,
            transition=transition,
        )
        segments.append(segment)
        endpoint_state = np.asarray(segment.state[:, -1], dtype=float)
        if transition.successor_state is None:
            successor_state = np.array(endpoint_state, dtype=float, copy=True)
        else:
            successor_state = _mutable_vector(
                transition.successor_state,
                name="HybridTransition.successor_state",
            )
            if successor_state.size != current_state.size:
                raise ValueError(
                    "HybridTransition.successor_state must match the integrated state size."
                )

        transitions.append(
            HybridTransitionRecord(
                time=segment.end_time,
                previous_mode=current_mode,
                fired_event_names=event_names,
                transition=transition,
                post_transition_state=successor_state,
            )
        )

        if transition.terminates:
            return HybridIntegrationResult(
                segments=tuple(segments),
                transitions=tuple(transitions),
                completed=False,
                termination_reason=transition.reason,
            )
        if transition.next_mode == current_mode and transition.successor_state is None:
            raise RuntimeError(
                "Hybrid transition returned the exact active mode without a state reset "
                "after a terminal event. Return a distinct mode, provide successor_state, "
                "or terminate."
            )

        current_time = segment.end_time
        current_state = successor_state
        current_mode = transition.next_mode

    raise RuntimeError(
        "Hybrid integration exceeded maximum_transitions without reaching final time."
    )


def _fired_event_names(
    *,
    solution: Any,
    events: Sequence[HybridEvent],
    tolerance: float,
) -> tuple[str, ...]:
    if solution.status != 1:
        return ()
    endpoint = float(solution.t[-1])
    scale = max(1.0, abs(endpoint))
    allowed = max(tolerance, 64.0 * np.finfo(float).eps * scale)
    names: list[str] = []
    for event, event_times in zip(events, solution.t_events, strict=True):
        if event_times.size and abs(float(event_times[-1]) - endpoint) <= allowed:
            names.append(event.name)
    if not names:
        raise RuntimeError("solve_ivp stopped on an event but no endpoint event was identified.")
    return tuple(names)


def _validate_event_names(events: Sequence[HybridEvent]) -> None:
    names = tuple(event.name for event in events)
    if len(set(names)) != len(names):
        raise ValueError("Active hybrid event names must be unique.")


def _coerce_rhs(values: ArrayLike, *, state_size: int) -> NDArray[np.float64]:
    derivative = np.asarray(values, dtype=float)
    if derivative.ndim != 1 or derivative.size != state_size:
        raise ValueError("Hybrid RHS must return a finite vector aligned with the state.")
    if not np.all(np.isfinite(derivative)):
        raise FloatingPointError("Hybrid RHS returned non-finite values.")
    return derivative


def _mutable_vector(values: ArrayLike, *, name: str) -> NDArray[np.float64]:
    vector = np.asarray(values, dtype=float)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional vector.")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain finite values.")
    return np.array(vector, dtype=float, copy=True)


def _immutable_vector(values: ArrayLike, *, name: str) -> NDArray[np.float64]:
    vector = _mutable_vector(values, name=name)
    vector.setflags(write=False)
    return vector
