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
    time: float,
    state: CVTState,
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint = EngagedShiftConstraint.FREE,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime:
    """Choose a post-engagement contact regime from a supplied state and time."""

    if not isfinite(time):
        raise ValueError("time must be finite.")
    vector = state.as_vector()
    snapshot = evaluator.model.snapshot_at_time(
        time=time, state=state, shaft_boundaries=shaft_boundaries
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

    if primary_direction is not None and secondary_direction is not None:
        return ContactRegime.both_slip(
            primary_direction=primary_direction,
            secondary_direction=secondary_direction,
        )
    if primary_direction is not None:
        return ContactRegime.primary_slip_secondary_stick(
            primary_direction=primary_direction
        )
    if secondary_direction is not None:
        return ContactRegime.primary_stick_secondary_slip(
            secondary_direction=secondary_direction
        )

    stick = evaluator.evaluate_vector(
        time=time,
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
        time=time,
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

    if not isfinite(time):
        raise ValueError("time must be finite.")
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
            time=time,
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
            time=time,
            vector=vector,
            old_regime=old_regime,
            zero_crossing_interfaces=restick_interfaces,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if continuation is not None:
            return HybridTransition(
                next_mode=continuation,
                reason="kinetic_slip_direction_updated_at_zero_crossing",
                metadata={
                    "interfaces": tuple(
                        interface.value for interface in restick_interfaces
                    )
                },
            )

        # The positive re-stick reserve above is numerical hysteresis, not an
        # additional physical friction law.  At v_rel = 0 it is possible for
        # the stick solution to lie inside the actual static-capacity boundary
        # while still failing that extra reserve.  If neither Coulomb kinetic
        # direction accelerates away from zero, rejecting stick as well leaves
        # an artificial hole in the hybrid mode graph.  In that corner, fall
        # back to the same topology-tightening candidate using the physical
        # stick-exit margin.  This does not prefer stick over an available
        # kinetic continuation: the hysteretic stick test and both outgoing
        # kinetic directions have already been tried first.
        physical_stick = _select_restick_candidate(
            evaluator=evaluator,
            time=time,
            vector=vector,
            old_regime=old_regime,
            restick_interfaces=restick_interfaces,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
            required_static_margin=switching_settings.stick_exit_static_margin,
        )
        if physical_stick is not None:
            return HybridTransition(
                next_mode=physical_stick,
                reason="contact_restuck_at_physical_limit_no_kinetic_continuation",
                metadata={
                    "interfaces": tuple(
                        interface.value for interface in restick_interfaces
                    ),
                    "requested_restick_margin": switching_settings.restick_static_margin,
                    "accepted_static_margin_floor": (
                        switching_settings.stick_exit_static_margin
                    ),
                },
            )

        # A zero crossing can require two topology changes at the same instant.
        # Example: primary-stick/secondary-slip reaches v_rel,s = 0; enforcing
        # secondary stick can overload the primary static requirement even though
        # the old mixed branch still had primary reserve.  The physically valid
        # successor can then be primary-slip/secondary-stick.  The old resolver
        # never considered that simultaneous exchange, leaving a false no-mode
        # state.  Test it only after all ordinary successors above have failed,
        # and accept it through the same static/normal/outgoing checks used
        # everywhere else.
        exchanged = _select_zero_crossing_topology_exchange(
            evaluator=evaluator,
            time=time,
            vector=vector,
            old_regime=old_regime,
            restick_interfaces=restick_interfaces,
            switching_settings=switching_settings,
            shift_constraint=shift_constraint,
            shaft_boundaries=shaft_boundaries,
        )
        if exchanged is not None:
            return HybridTransition(
                next_mode=exchanged,
                reason="zero_crossing_simultaneous_contact_topology_exchange",
                metadata={
                    "interfaces": tuple(
                        interface.value for interface in restick_interfaces
                    ),
                    "successor_mode": exchanged.mode.value,
                },
            )

        return HybridTransition(
            next_mode=None,
            reason="no_admissible_stick_or_direction_consistent_kinetic_branch_at_slip_zero_crossing",
            metadata={
                "interfaces": tuple(interface.value for interface in restick_interfaces),
                "requested_restick_margin": switching_settings.restick_static_margin,
                "physical_stick_margin_floor": switching_settings.stick_exit_static_margin,
                "zero_crossing_candidate_diagnostics": _zero_crossing_candidate_diagnostics(
                    evaluator=evaluator,
                    time=time,
                    vector=vector,
                    old_regime=old_regime,
                    restick_interfaces=restick_interfaces,
                    switching_settings=switching_settings,
                    shift_constraint=shift_constraint,
                    shaft_boundaries=shaft_boundaries,
                ),
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
            time=time,
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


def _select_zero_crossing_topology_exchange(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    restick_interfaces: tuple[ContactInterface, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> ContactRegime | None:
    """Try a simultaneous restick/release after ordinary successors fail.

    A contact that reaches zero slip may become sticking while a contact that
    was sticking in the incoming branch simultaneously exceeds static capacity
    under the newly constrained closure.  That is a legitimate complementarity
    transition, not a finite-speed spontaneous release: the newly slipping
    interface starts from zero relative speed because it was constrained in the
    incoming mode, and its kinetic direction must accelerate outward.

    Mixed exchange candidates are preferred over both-slip because they retain
    the maximum number of constraints.  This helper is called only after the
    normal re-stick, kinetic continuation, and physical-limit stick attempts
    have all failed, so it cannot displace an already-valid ordinary successor.
    """

    requested = set(restick_interfaces)
    mixed: list[ContactRegime] = []

    if (
        old_regime.mode is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP
        and ContactInterface.SECONDARY in requested
    ):
        mixed.extend(
            ContactRegime.primary_slip_secondary_stick(
                primary_direction=direction
            )
            for direction in _slip_directions()
        )
    elif (
        old_regime.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK
        and ContactInterface.PRIMARY in requested
    ):
        mixed.extend(
            ContactRegime.primary_stick_secondary_slip(
                secondary_direction=direction
            )
            for direction in _slip_directions()
        )
    else:
        # Both-slip restick logic already considers the corresponding mixed
        # topology; there is no previously sticking interface to release.
        return None

    candidate = _best_admissible_candidate(
        evaluator=evaluator,
        time=time,
        vector=vector,
        candidates=mixed,
        switching_settings=switching_settings,
        required_static_margin=switching_settings.stick_exit_static_margin,
        require_outgoing_directions=True,
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )
    if candidate is not None:
        return candidate

    # If the newly sticking interface itself cannot remain static after the
    # other contact releases, both contacts may need to slide.  At this event
    # both relative speeds are at (or inherited from) valid kinetic states; the
    # standard outgoing-direction test rejects any branch that does not depart
    # consistently from the zero-speed manifold.
    return _best_admissible_candidate(
        evaluator=evaluator,
        time=time,
        vector=vector,
        candidates=_both_slip_regimes(),
        switching_settings=switching_settings,
        required_static_margin=switching_settings.stick_exit_static_margin,
        require_outgoing_directions=True,
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )


def _zero_crossing_candidate_diagnostics(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    restick_interfaces: tuple[ContactInterface, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> dict[str, object]:
    """Return detailed candidate mechanics for an otherwise unresolved zero crossing.

    This is diagnostic only.  It deliberately evaluates a wider candidate set
    than the current transition policy, including a simultaneous exchange of
    which interface is slipping.  The results let a caller distinguish a true
    Coulomb no-solution state from an incomplete successor candidate set before
    changing hybrid policy.
    """

    candidates: list[tuple[str, ContactRegime]] = []
    requested = set(restick_interfaces)

    # Candidate(s) already considered by the transition resolver.
    if old_regime.mode in (
        EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK,
        EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP,
    ):
        candidates.append(("stick_stick", ContactRegime.stick_stick()))
    elif old_regime.mode is EngagedContactMode.BOTH_SLIP:
        if requested == {ContactInterface.PRIMARY, ContactInterface.SECONDARY}:
            candidates.append(("stick_stick", ContactRegime.stick_stick()))

    if old_regime.mode is EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP:
        for direction in _slip_directions():
            candidates.append((
                f"continue_secondary_slip:{direction.value}",
                ContactRegime.primary_stick_secondary_slip(
                    secondary_direction=direction
                ),
            ))
            # A secondary zero crossing can make stick--stick impossible only
            # because the newly constrained solution overloads the primary.
            # This swap is therefore a physically plausible simultaneous
            # successor even though the current policy does not yet select it.
            candidates.append((
                f"swap_to_primary_slip_secondary_stick:{direction.value}",
                ContactRegime.primary_slip_secondary_stick(
                    primary_direction=direction
                ),
            ))
    elif old_regime.mode is EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK:
        for direction in _slip_directions():
            candidates.append((
                f"continue_primary_slip:{direction.value}",
                ContactRegime.primary_slip_secondary_stick(
                    primary_direction=direction
                ),
            ))
            candidates.append((
                f"swap_to_primary_stick_secondary_slip:{direction.value}",
                ContactRegime.primary_stick_secondary_slip(
                    secondary_direction=direction
                ),
            ))

    # Both-slip is the least constrained local topology and is useful as a
    # diagnostic even when the current event policy would not jump to it.
    for regime in _both_slip_regimes():
        candidates.append((
            "both_slip:"
            f"{regime.primary_slip_direction.value}/"
            f"{regime.secondary_slip_direction.value}",
            regime,
        ))

    seen: set[ContactRegime] = set()
    rendered: dict[str, object] = {}
    for label, candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            evaluation = evaluator.evaluate_vector(
                time=time,
                vector=vector,
                regime=candidate,
                shift_constraint=shift_constraint,
                shaft_boundaries=shaft_boundaries,
            )
            branch = evaluation.branch_result
            static_margins: dict[str, float] = {}
            for interface in candidate.mode.sticking_interfaces:
                static_margins[interface.value] = float(
                    evaluation.static_margin_at(
                        interface, traction_law=evaluator.traction_law
                    )
                )
            rendered[label] = {
                "mode": candidate.mode.value,
                "primary_lambda": float(
                    evaluation.traction_utilization.primary_lambda
                ),
                "secondary_lambda": float(
                    evaluation.traction_utilization.secondary_lambda
                ),
                "primary_normal_n": float(evaluation.normal_primary),
                "secondary_normal_n": float(evaluation.normal_secondary),
                "primary_relative_speed_mps": float(
                    evaluation.relative_motion.relative_speed_at(
                        ContactInterface.PRIMARY
                    )
                ),
                "secondary_relative_speed_mps": float(
                    evaluation.relative_motion.relative_speed_at(
                        ContactInterface.SECONDARY
                    )
                ),
                "primary_relative_acceleration_mps2": float(
                    evaluation.relative_motion.relative_acceleration_at(
                        ContactInterface.PRIMARY
                    )
                ),
                "secondary_relative_acceleration_mps2": float(
                    evaluation.relative_motion.relative_acceleration_at(
                        ContactInterface.SECONDARY
                    )
                ),
                "static_margins": static_margins,
                "stick_solver_accepted": (
                    bool(branch.accepted) if hasattr(branch, "accepted") else None
                ),
                "optimizer_success": (
                    bool(branch.optimizer_success)
                    if hasattr(branch, "optimizer_success")
                    else None
                ),
                "optimizer_cost": (
                    float(branch.optimizer_cost)
                    if hasattr(branch, "optimizer_cost")
                    else None
                ),
                "jacobian_condition_number": (
                    float(branch.jacobian_condition_number)
                    if hasattr(branch, "jacobian_condition_number")
                    else None
                ),
                "physical_static_admissible": bool(
                    evaluation.sticks_are_admissible(
                        traction_law=evaluator.traction_law,
                        required_margin=switching_settings.stick_exit_static_margin,
                    )
                ),
                "slipped_directions_consistent": bool(
                    evaluation.slipped_directions_are_consistent()
                ),
                "outgoing_if_slipping": bool(
                    _slip_directions_are_outgoing(
                        evaluation, candidate, evaluator
                    )
                    if candidate.mode.slipping_interfaces
                    else True
                ),
            }
        except Exception as exc:  # diagnostic path must not mask root failure
            rendered[label] = {
                "evaluation_error": f"{type(exc).__name__}: {exc}"
            }

    return {
        "event_time_s": float(time),
        "old_mode": old_regime.mode.value,
        "restick_interfaces": tuple(
            interface.value for interface in restick_interfaces
        ),
        "candidates": rendered,
    }


def _select_capacity_loss_candidate(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
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
            time=time,
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
    time: float,
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
        time=time,
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
    time: float,
    vector: NDArray[np.float64],
    old_regime: ContactRegime,
    restick_interfaces: tuple[ContactInterface, ...],
    switching_settings: CVTEventSwitchingTolerances,
    shift_constraint: EngagedShiftConstraint,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
    required_static_margin: float | None = None,
) -> ContactRegime | None:
    """Attempt only topology-tightening candidates after a velocity event.

    ``required_static_margin`` defaults to the configured positive re-stick
    reserve.  The transition resolver may explicitly retry with the physical
    stick-exit margin only after no outgoing kinetic continuation exists.
    """

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

    margin = (
        switching_settings.restick_static_margin
        if required_static_margin is None
        else float(required_static_margin)
    )
    _require_finite_nonnegative(required_static_margin=margin)
    return _best_admissible_candidate(
        evaluator=evaluator,
        time=time,
        vector=vector,
        candidates=candidates,
        switching_settings=switching_settings,
        required_static_margin=margin,
        require_outgoing_directions=False,
        shift_constraint=shift_constraint,
        shaft_boundaries=shaft_boundaries,
    )


def _best_admissible_candidate(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
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
            time=time,
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
