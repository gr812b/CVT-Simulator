"""CVT-specific contact transition policy for the generic hybrid runner."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Iterable

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system.ports import CVTShaftBoundaryValues

from cinder.model.cvt.contact import (
    ContactInterface,
    ContactRegime,
    EngagedContactMode,
    SlipDirection,
)

from .cvt_contact_events import CVTContactEvent
from .hybrid import HybridTransition
from .state import CVTState

if TYPE_CHECKING:
    from .cvt_contact import CVTContactEvaluation, EngagedCVTContactEvaluator


@dataclass(frozen=True, slots=True)
class CVTEventSwitchingTolerances:
    """Hybrid event thresholds for engaged contact, separate from the contact law.

    ``stick_exit_static_margin`` may be zero: a sticking contact leaves only at
    its physical static capacity.  ``restick_static_margin`` must be larger,
    so a candidate must regain a traction reserve before reattachment.

    Re-stick is attempted only at the exact zero-relative-speed event. The
    higher ``restick_static_margin`` is the hysteresis mechanism: a contact
    exits stick at the physical limit but may reattach only after it regains a
    positive traction reserve.
    """

    stick_exit_static_margin: float = 0.0
    restick_static_margin: float = 1.0e-3
    normal_resultant_floor: float = 1.0e-6

    def __post_init__(self) -> None:
        _require_finite_nonnegative(
            stick_exit_static_margin=self.stick_exit_static_margin,
            restick_static_margin=self.restick_static_margin,
            normal_resultant_floor=self.normal_resultant_floor,
        )
        if self.restick_static_margin <= self.stick_exit_static_margin:
            raise ValueError(
                "restick_static_margin must exceed stick_exit_static_margin."
            )


# Backwards internal alias while neighboring modules are migrated. The public
# name describes what these values are: event/switching tolerances, not branch
# rules or physical contact laws.
CVTContactSwitchSettings = CVTEventSwitchingTolerances


def resolve_initial_engaged_regime(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    state: CVTState,
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime:
    """Choose a post-engagement initial contact regime from a supplied state."""

    vector = state.as_vector()
    snapshot = evaluator.model.snapshot(
        state=state,
        shaft_boundaries=shaft_boundaries,
        geometry_side="engaged",
    )
    tolerance = evaluator.solve_settings.contact_tolerances.relative_speed_tolerance
    primary_speed = (
        state.belt_speed
        - snapshot.geometry.primary.effective * state.primary_angular_speed
    )
    secondary_speed = (
        state.belt_speed
        - snapshot.geometry.secondary.effective * state.secondary_angular_speed
    )

    primary_direction = _direction_from_established_speed(primary_speed, tolerance)
    secondary_direction = _direction_from_established_speed(secondary_speed, tolerance)

    # Established velocity selects kinetic direction, but a zero relative
    # speed only makes stick *eligible*.  Never declare the other interface
    # sticking until its constrained closure is actually admissible.  This is
    # especially important at first engagement, where the exact boundary has
    # a one-sided geometry tangent.
    if primary_direction is not None or secondary_direction is not None:
        candidates: list[ContactRegime] = []
        if primary_direction is not None and secondary_direction is not None:
            candidates.append(
                ContactRegime.both_slip(
                    primary_direction=primary_direction,
                    secondary_direction=secondary_direction,
                )
            )
        elif primary_direction is not None:
            candidates.append(
                ContactRegime.primary_slip_secondary_stick(
                    primary_direction=primary_direction
                )
            )
            candidates.extend(
                ContactRegime.both_slip(
                    primary_direction=primary_direction,
                    secondary_direction=direction,
                )
                for direction in _slip_directions()
            )
        else:
            assert secondary_direction is not None
            candidates.append(
                ContactRegime.primary_stick_secondary_slip(
                    secondary_direction=secondary_direction
                )
            )
            candidates.extend(
                ContactRegime.both_slip(
                    primary_direction=direction,
                    secondary_direction=secondary_direction,
                )
                for direction in _slip_directions()
            )

        candidate = _best_admissible_candidate(
            evaluator=evaluator,
            vector=vector,
            candidates=candidates,
            switching_settings=switching_settings,
            required_static_margin=switching_settings.stick_exit_static_margin,
            require_outgoing_directions=True,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if candidate is not None:
            return candidate
        raise RuntimeError(
            "No admissible engaged contact branch exists for the established "
            "relative-speed directions at engagement."
        )

    stick = evaluator.evaluate_vector(
        time=0.0,
        vector=vector,
        regime=ContactRegime.stick_stick(),
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )
    if _candidate_is_admissible(
        stick,
        evaluator=evaluator,
        required_static_margin=switching_settings.stick_exit_static_margin,
        require_outgoing_directions=False,
        switching_settings=switching_settings,
    ):
        return ContactRegime.stick_stick()

    fired: list[str] = []
    for interface in (ContactInterface.PRIMARY, ContactInterface.SECONDARY):
        margin = stick.static_margin_at(interface, traction_law=evaluator.traction_law)
        if margin < switching_settings.stick_exit_static_margin:
            fired.append(_capacity_event_for(interface).value)
    if not fired:
        raise RuntimeError(
            "Initial stick candidate is inadmissible without a static-capacity "
            "violation. Check closure acceptance and normal resultants."
        )
    transition = resolve_cvt_contact_transition(
        evaluator=evaluator,
        time=0.0,
        vector=vector,
        old_regime=ContactRegime.stick_stick(),
        fired_event_names=tuple(fired),
        switching_settings=switching_settings,
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )
    if transition.next_mode is None:
        raise RuntimeError(
            f"Unable to classify an engaged initial regime: {transition.reason}."
        )
    return transition.next_mode


def resolve_cvt_contact_transition(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    fired_event_names: tuple[str, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[ContactRegime]:
    """Resolve a terminal engaged-contact event using its physical cause.

    The fired event guides candidate order.  A capacity event first attempts a
    mixed branch before both-slip; a re-stick event first attempts the more
    constrained sticking branch.  Every candidate is re-evaluated with the
    existing branch solver before it is accepted.
    """

    if not isinstance(shift_constraint, EngagedShiftConstraint):
        raise TypeError("shift_constraint must be an EngagedShiftConstraint.")

    fired = {CVTContactEvent(name) for name in fired_event_names}
    if CVTContactEvent.LOWER_SHIFT_STOP in fired:
        return HybridTransition(
            next_mode=None,
            reason="lower_shift_stop_reached_stop_reaction_unimplemented",
        )
    if CVTContactEvent.UPPER_SHIFT_STOP in fired:
        return HybridTransition(
            next_mode=None,
            reason="upper_shift_stop_reached_stop_reaction_unimplemented",
        )
    if (
        CVTContactEvent.PRIMARY_NORMAL_FLOOR in fired
        or CVTContactEvent.SECONDARY_NORMAL_FLOOR in fired
    ):
        return HybridTransition(
            next_mode=None,
            reason="contact_loss_normal_resultant_floor",
        )

    restick_interfaces = _interfaces_for_events(
        fired,
        primary_event=CVTContactEvent.PRIMARY_RESTICK,
        secondary_event=CVTContactEvent.SECONDARY_RESTICK,
    )
    if restick_interfaces:
        candidate = _select_restick_candidate(
            evaluator=evaluator,
            vector=vector,
            old_regime=old_regime,
            restick_interfaces=restick_interfaces,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if candidate is not None:
            return HybridTransition(
                next_mode=candidate,
                reason="contact_restuck_with_static_reserve",
                metadata={
                    "interfaces": tuple(
                        interface.value for interface in restick_interfaces
                    )
                },
            )

        continuation = _select_zero_crossing_kinetic_continuation(
            evaluator=evaluator,
            vector=vector,
            old_regime=old_regime,
            zero_crossing_interfaces=restick_interfaces,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if continuation is None:
            return HybridTransition(
                next_mode=None,
                reason="no_direction_consistent_kinetic_branch_at_slip_zero_crossing",
            )
        return HybridTransition(
            next_mode=continuation,
            reason="kinetic_slip_direction_updated_at_zero_crossing",
            metadata={
                "interfaces": tuple(interface.value for interface in restick_interfaces)
            },
        )

    capacity_interfaces = _interfaces_for_events(
        fired,
        primary_event=CVTContactEvent.PRIMARY_STATIC_CAPACITY,
        secondary_event=CVTContactEvent.SECONDARY_STATIC_CAPACITY,
    )
    if capacity_interfaces:
        candidate = _select_capacity_loss_candidate(
            evaluator=evaluator,
            vector=vector,
            old_regime=old_regime,
            capacity_interfaces=capacity_interfaces,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if candidate is None:
            return HybridTransition(
                next_mode=None,
                reason="no_direction_consistent_kinetic_branch_after_static_capacity_loss",
            )
        return HybridTransition(
            next_mode=candidate,
            reason="static_capacity_exhausted_entered_kinetic_slip",
            metadata={
                "interfaces": tuple(
                    interface.value for interface in capacity_interfaces
                )
            },
        )

    raise RuntimeError(
        f"Unhandled CVT contact event set: {sorted(event.value for event in fired)}"
    )


def _select_capacity_loss_candidate(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    capacity_interfaces: tuple[ContactInterface, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime | None:
    """Choose the least-relaxed direction-consistent kinetic successor.

    When both stick capacities are exhausted by the *stick--stick* demand, a
    one-contact kinetic release can still reduce the other contact's required
    static lambda back inside its capacity.  Therefore mixed candidates are
    always tested before jumping directly to both-slip.
    """

    lost = set(capacity_interfaces)

    def choose(candidates: Iterable[ContactRegime]) -> ContactRegime | None:
        return _best_admissible_candidate(
            evaluator=evaluator,
            vector=vector,
            candidates=candidates,
            switching_settings=switching_settings,
            required_static_margin=switching_settings.stick_exit_static_margin,
            require_outgoing_directions=True,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )

    if old_regime.mode is EngagedContactMode.STICK_STICK:
        mixed: list[ContactRegime] = []
        if ContactInterface.PRIMARY in lost:
            mixed.extend(
                ContactRegime.primary_slip_secondary_stick(primary_direction=direction)
                for direction in _slip_directions()
            )
        if ContactInterface.SECONDARY in lost:
            mixed.extend(
                ContactRegime.primary_stick_secondary_slip(
                    secondary_direction=direction
                )
                for direction in _slip_directions()
            )
        candidate = choose(mixed)
        if candidate is not None:
            return candidate
        return choose(_both_slip_regimes())

    if old_regime.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
        if ContactInterface.SECONDARY not in lost:
            return None
        primary_direction = old_regime.slip_direction_at(ContactInterface.PRIMARY)
        return choose(
            ContactRegime.both_slip(
                primary_direction=primary_direction,
                secondary_direction=secondary_direction,
            )
            for secondary_direction in _slip_directions()
        )

    if old_regime.mode is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
        if ContactInterface.PRIMARY not in lost:
            return None
        secondary_direction = old_regime.slip_direction_at(ContactInterface.SECONDARY)
        return choose(
            ContactRegime.both_slip(
                primary_direction=primary_direction,
                secondary_direction=secondary_direction,
            )
            for primary_direction in _slip_directions()
        )

    return None


def _select_zero_crossing_kinetic_continuation(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    zero_crossing_interfaces: tuple[ContactInterface, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime | None:
    """Select outgoing Coulomb direction(s) when stick remains unavailable."""

    crossed = set(zero_crossing_interfaces)
    candidates: list[ContactRegime] = []

    if old_regime.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
        candidates.extend(
            ContactRegime.primary_slip_secondary_stick(primary_direction=direction)
            for direction in _slip_directions()
        )
    elif old_regime.mode is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
        candidates.extend(
            ContactRegime.primary_stick_secondary_slip(secondary_direction=direction)
            for direction in _slip_directions()
        )
    elif old_regime.mode is EngagedContactMode.BOTH_SLIP:
        primary_directions = (
            _slip_directions()
            if ContactInterface.PRIMARY in crossed
            else (old_regime.slip_direction_at(ContactInterface.PRIMARY),)
        )
        secondary_directions = (
            _slip_directions()
            if ContactInterface.SECONDARY in crossed
            else (old_regime.slip_direction_at(ContactInterface.SECONDARY),)
        )
        candidates.extend(
            ContactRegime.both_slip(
                primary_direction=primary_direction,
                secondary_direction=secondary_direction,
            )
            for primary_direction in primary_directions
            for secondary_direction in secondary_directions
        )

    return _best_admissible_candidate(
        evaluator=evaluator,
        vector=vector,
        candidates=candidates,
        switching_settings=switching_settings,
        required_static_margin=switching_settings.stick_exit_static_margin,
        require_outgoing_directions=True,
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )


def _select_restick_candidate(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    restick_interfaces: tuple[ContactInterface, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime | None:
    """Attempt only topology-tightening candidates after a velocity event."""

    requested = set(restick_interfaces)
    candidates: list[ContactRegime] = []

    if old_regime.mode in (
        EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK,
        EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP,
    ):
        candidates.append(ContactRegime.stick_stick())
    elif old_regime.mode is EngagedContactMode.BOTH_SLIP:
        if requested == {ContactInterface.PRIMARY, ContactInterface.SECONDARY}:
            candidates.append(ContactRegime.stick_stick())
        if ContactInterface.PRIMARY in requested:
            candidates.append(
                ContactRegime.primary_stick_secondary_slip(
                    secondary_direction=old_regime.slip_direction_at(
                        ContactInterface.SECONDARY
                    )
                )
            )
        if ContactInterface.SECONDARY in requested:
            candidates.append(
                ContactRegime.primary_slip_secondary_stick(
                    primary_direction=old_regime.slip_direction_at(
                        ContactInterface.PRIMARY
                    )
                )
            )

    return _best_admissible_candidate(
        evaluator=evaluator,
        vector=vector,
        candidates=candidates,
        switching_settings=switching_settings,
        required_static_margin=switching_settings.restick_static_margin,
        require_outgoing_directions=False,
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )


def _best_admissible_candidate(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    vector: NDArray[np.float64],
    candidates: Iterable[ContactRegime],
    switching_settings: CVTEventSwitchingTolerances,
    required_static_margin: float,
    require_outgoing_directions: bool,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime | None:
    accepted: list[tuple[float, ContactRegime]] = []
    for candidate in candidates:
        evaluation = evaluator.evaluate_vector(
            time=0.0,
            vector=vector,
            regime=candidate,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if not _candidate_is_admissible(
            evaluation,
            evaluator=evaluator,
            required_static_margin=required_static_margin,
            require_outgoing_directions=require_outgoing_directions,
            switching_settings=switching_settings,
        ):
            continue
        accepted.append((_outgoing_direction_score(evaluation, candidate), candidate))

    if not accepted:
        return None
    accepted.sort(key=lambda item: item[0], reverse=True)
    return accepted[0][1]


def _candidate_is_admissible(
    evaluation: "CVTContactEvaluation",
    *,
    evaluator: "EngagedCVTContactEvaluator",
    required_static_margin: float,
    require_outgoing_directions: bool,
    switching_settings: CVTEventSwitchingTolerances,
) -> bool:
    if (
        evaluation.normal_primary <= switching_settings.normal_resultant_floor
        or evaluation.normal_secondary <= switching_settings.normal_resultant_floor
    ):
        return False
    if not evaluation.sticks_are_admissible(
        traction_law=evaluator.traction_law,
        required_margin=required_static_margin,
    ):
        return False
    # Acceleration compatibility can only preserve a stick constraint that is
    # already satisfied at velocity level.  Without this guard, a branch can
    # be labelled ``stick`` while carrying a finite sliding speed forever.
    relative_speed_tolerance = (
        evaluator.solve_settings.contact_tolerances.relative_speed_tolerance
    )
    for interface in evaluation.regime.mode.sticking_interfaces:
        if (
            abs(evaluation.relative_motion.relative_speed_at(interface))
            > relative_speed_tolerance
        ):
            return False
    if require_outgoing_directions:
        return _slip_directions_are_outgoing(evaluation, evaluation.regime, evaluator)
    return evaluation.slipped_directions_are_consistent()


def _slip_directions_are_outgoing(
    evaluation: "CVTContactEvaluation",
    regime: ContactRegime,
    evaluator: "EngagedCVTContactEvaluator",
) -> bool:
    tolerances = evaluator.solve_settings.contact_tolerances
    for interface in regime.mode.slipping_interfaces:
        direction = regime.slip_direction_at(interface)
        relative_speed = evaluation.relative_motion.relative_speed_at(interface)
        relative_acceleration = evaluation.relative_motion.relative_acceleration_at(
            interface
        )
        sign = _direction_sign(direction)
        if abs(relative_speed) > tolerances.relative_speed_tolerance:
            if sign * relative_speed <= 0.0:
                return False
        elif sign * relative_acceleration <= tolerances.relative_acceleration_tolerance:
            return False
    return True


def _outgoing_direction_score(
    evaluation: "CVTContactEvaluation",
    regime: ContactRegime,
) -> float:
    score = 0.0
    for interface in regime.mode.slipping_interfaces:
        sign = _direction_sign(regime.slip_direction_at(interface))
        score += sign * evaluation.relative_motion.relative_acceleration_at(interface)
    return score


def _direction_from_established_speed(
    relative_speed: float,
    tolerance: float,
) -> SlipDirection | None:
    if relative_speed > tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_speed < -tolerance:
        return SlipDirection.PULLEY_LEADS_BELT
    return None


def _direction_sign(direction: SlipDirection) -> float:
    if direction is SlipDirection.BELT_LEADS_PULLEY:
        return 1.0
    if direction is SlipDirection.PULLEY_LEADS_BELT:
        return -1.0
    raise ValueError("Indeterminate direction cannot define a sign.")


def _slip_directions() -> tuple[SlipDirection, SlipDirection]:
    return (SlipDirection.BELT_LEADS_PULLEY, SlipDirection.PULLEY_LEADS_BELT)


def _both_slip_regimes() -> tuple[ContactRegime, ...]:
    return tuple(
        ContactRegime.both_slip(
            primary_direction=primary_direction,
            secondary_direction=secondary_direction,
        )
        for primary_direction in _slip_directions()
        for secondary_direction in _slip_directions()
    )


def _capacity_event_for(interface: ContactInterface) -> CVTContactEvent:
    if interface is ContactInterface.PRIMARY:
        return CVTContactEvent.PRIMARY_STATIC_CAPACITY
    if interface is ContactInterface.SECONDARY:
        return CVTContactEvent.SECONDARY_STATIC_CAPACITY
    raise ValueError(f"Unsupported contact interface: {interface!r}.")


def _interfaces_for_events(
    events: set[CVTContactEvent],
    *,
    primary_event: CVTContactEvent,
    secondary_event: CVTContactEvent,
) -> tuple[ContactInterface, ...]:
    interfaces: list[ContactInterface] = []
    if primary_event in events:
        interfaces.append(ContactInterface.PRIMARY)
    if secondary_event in events:
        interfaces.append(ContactInterface.SECONDARY)
    return tuple(interfaces)


def _require_finite_nonnegative(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative.")


def _require_finite_positive(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and strictly positive.")
