"""Event-guided CVT operating-regime transitions and state projections.

This module owns physical event successors and explicit impact/capture resets.
The engaged low-ratio seat, upper-stop, and deadzone lower-stop closures are
all available to the operating dispatcher.  No state clamp is hidden inside an ODE right-hand
side: each reset is returned through ``HybridTransition.successor_state``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from cinder.contact import ContactInterface, ContactRegime
from cinder.dynamics.deadzone import DeadzoneDynamicsEvaluator
from cinder.dynamics.shift_constraints import EngagedShiftConstraint

from .cvt_contact_events import CVTContactEvent
from .cvt_contact_switching import (
    CVTContactSwitchSettings,
    resolve_cvt_contact_transition,
)
from .cvt_operating_limits import CVTShiftOperatingLimits
from .cvt_regime import CVTEngagementState, CVTOperatingRegime, CVTShiftConstraint
from .cvt_regime_events import CVTRegimeEvent
from .hybrid import HybridTransition
from .state import CVTDynamicState

if TYPE_CHECKING:
    from .cvt_contact import CVTContactEvaluation, EngagedCVTContactEvaluator


_PRIMARY_CLAMP_EVENT_TOLERANCE = 1.0e-8


def classify_initial_cvt_regime(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    state: CVTDynamicState,
    limits: CVTShiftOperatingLimits,
    switching_settings: CVTContactSwitchSettings,
) -> CVTOperatingRegime:
    """Classify an initial state into one physically meaningful regime.

    At the exact engagement position, a nonnegative shift velocity is treated
    as a closing/engaged state; a negative velocity is treated as opening into
    deadzone.  Exact-stop initial states are represented by their matching
    constrained regime; the operating dispatcher then checks unilateral
    reaction admissibility before integration begins.
    """

    _validate_state_within_limits(state=state, limits=limits)
    s = state.shift_position
    if s == limits.lower_stop_shift:
        return CVTOperatingRegime.deadzone_lower_stop()
    if s < limits.engagement_shift or (
        s == limits.engagement_shift and state.shift_speed < 0.0
    ):
        return CVTOperatingRegime.deadzone_free()

    contact = evaluator.classify_initial_regime(
        state=state,
        switching_settings=switching_settings,
    )
    if s == limits.upper_stop_shift:
        return CVTOperatingRegime.engaged_upper_stop(contact_regime=contact)
    return CVTOperatingRegime.engaged_free(contact_regime=contact)


def resolve_cvt_operating_transition(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    deadzone_evaluator: DeadzoneDynamicsEvaluator,
    time: float,
    vector: NDArray[np.float64],
    old_regime: CVTOperatingRegime,
    fired_event_names: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    """Resolve only successors allowed by the active physical regime.

    Geometry/stop events take precedence over contact events because they
    change which governing equations remain valid.  Contact events are then
    delegated to the established engaged-contact resolver and wrapped back
    into the same free/upper-stop operating constraint.
    """

    state = CVTDynamicState.from_vector(vector)
    _validate_state_within_limits(state=state, limits=limits, tolerance=1.0e-8)
    fired = set(fired_event_names)
    geometry_events = _geometry_events_from(fired)
    contact_events = tuple(
        name for name in fired_event_names if name not in _REGIME_EVENT_NAMES
    )

    if old_regime.engagement is CVTEngagementState.DEADZONE:
        return _resolve_deadzone_transition(
            state=state,
            vector=vector,
            old_regime=old_regime,
            geometry_events=geometry_events,
            contact_events=contact_events,
            limits=limits,
            evaluator=evaluator,
            deadzone_evaluator=deadzone_evaluator,
            switching_settings=switching_settings,
        )

    return _resolve_engaged_transition(
        time=time,
        state=state,
        vector=vector,
        old_regime=old_regime,
        geometry_events=geometry_events,
        contact_events=contact_events,
        limits=limits,
        evaluator=evaluator,
        switching_settings=switching_settings,
    )


def project_inelastic_shift_constraint(
    *,
    vector: NDArray[np.float64],
    shift_position: float,
) -> NDArray[np.float64]:
    """Project any fixed-shift boundary arrival to a perfectly inelastic axial state."""

    projected = np.array(vector, dtype=float, copy=True)
    projected[3] = float(shift_position)
    projected[4] = 0.0
    return projected


def primary_independent_clamping_force_at_engagement(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    state: CVTDynamicState,
    limits: CVTShiftOperatingLimits,
) -> float:
    """Return the primary actuator's signed force at the engagement boundary.

    This is intentionally the primary mechanism's own known force, excluding
    the engaged belt normal resultant.  The latter may oppose primary closure
    while a belt is seated, but it does not by itself authorize a transition to
    deadzone.  The current conventional primary is a known-force actuator; a
    force law with closure-unknown gains requires an explicit release model.
    """

    boundary_state = replace(
        state,
        shift_position=limits.engagement_shift,
        shift_speed=0.0,
    )
    snapshot = evaluator.model.snapshot(state=boundary_state)
    if any(value != 0.0 for value in snapshot.primary_actuation.gains.as_tuple()):
        raise NotImplementedError(
            "Primary-clamp disengagement gating requires an independently known "
            "primary actuator force. Add an explicit release law before using a "
            "primary actuation model with closure-unknown gains."
        )
    return snapshot.primary_actuation.bias_force


def capture_belt_to_secondary_at_disengagement(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    state: CVTDynamicState,
    limits: CVTShiftOperatingLimits,
) -> NDArray[np.float64]:
    """Apply the temporary perfectly inelastic belt-secondary capture map.

    Deadzone assumes the belt remains locked to the secondary.  If a slipping
    secondary reaches primary disengagement, this map conserves angular
    momentum about the secondary shaft for a lumped belt mass at the secondary
    effective radius, then imposes ``v_b = r_s omega_s``.  The approximation is
    explicit here so the later neutral RHS can replace it without touching the
    transition graph.
    """

    boundary_state = replace(state, shift_position=limits.engagement_shift)
    snapshot = evaluator.model.snapshot(state=boundary_state)
    radius = snapshot.geometry.secondary.effective
    belt_mass = snapshot.belt_transport_mass
    secondary_inertia = snapshot.secondary_absolute_rotational_inertia
    combined_inertia = secondary_inertia + belt_mass * radius * radius
    if combined_inertia <= 0.0:
        raise RuntimeError("Deadzone belt-secondary capture has non-positive inertia.")

    captured_secondary_speed = (
        secondary_inertia * state.secondary_angular_speed
        + belt_mass * radius * state.belt_speed
    ) / combined_inertia

    projected = boundary_state.as_vector().copy()
    projected[1] = captured_secondary_speed
    projected[2] = radius * captured_secondary_speed
    return projected


def _resolve_deadzone_transition(
    *,
    state: CVTDynamicState,
    vector: NDArray[np.float64],
    old_regime: CVTOperatingRegime,
    geometry_events: set[CVTRegimeEvent],
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    deadzone_evaluator: DeadzoneDynamicsEvaluator,
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    if contact_events:
        raise RuntimeError("Deadzone cannot receive engaged-contact event names.")

    if old_regime.shift_constraint is CVTShiftConstraint.FREE:
        if CVTRegimeEvent.LOWER_STOP_REACHED in geometry_events:
            return _resolve_lower_stop_arrival(
                vector=vector,
                limits=limits,
                deadzone_evaluator=deadzone_evaluator,
            )
        if CVTRegimeEvent.ENGAGEMENT_REACHED in geometry_events:
            boundary_state = CVTDynamicState.from_vector(
                project_inelastic_shift_constraint(
                    vector=vector,
                    shift_position=limits.engagement_shift,
                )
            )
            # Engagement is reached while closing.  The axial velocity is not
            # an impact target, so restore the event velocity after using the
            # common boundary-position projection above.
            engaged_vector = boundary_state.as_vector().copy()
            engaged_vector[4] = vector[4]
            engaged_state = CVTDynamicState.from_vector(engaged_vector)
            contact = evaluator.classify_initial_regime(
                state=engaged_state,
                switching_settings=switching_settings,
            )
            return HybridTransition(
                next_mode=CVTOperatingRegime.engaged_free(contact_regime=contact),
                reason="primary_closed_into_engaged_contact",
                successor_state=engaged_state.as_vector(),
            )
        raise RuntimeError(
            "Deadzone free transition received no reachable geometry event."
        )

    if CVTRegimeEvent.LOWER_STOP_RELEASE in geometry_events:
        return HybridTransition(
            next_mode=CVTOperatingRegime.deadzone_free(),
            reason="lower_stop_released_by_inward_free_shift_tendency",
            successor_state=project_inelastic_shift_constraint(
                vector=vector,
                shift_position=limits.lower_stop_shift,
            ),
        )
    raise RuntimeError("Deadzone lower-stop transition requires LOWER_STOP_RELEASE.")


def _resolve_lower_stop_arrival(
    *,
    vector: NDArray[np.float64],
    limits: CVTShiftOperatingLimits,
    deadzone_evaluator: DeadzoneDynamicsEvaluator,
) -> HybridTransition[CVTOperatingRegime]:
    """Apply the low-stop impact, then accept or immediately release it.

    The lower stop is unilateral.  As with the engaged upper stop, its
    admissibility must be checked under the *constrained* post-impact RHS
    before beginning the next segment; otherwise a negative reaction at the
    endpoint would never produce a downward crossing event.
    """

    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.lower_stop_shift,
    )
    evaluation = deadzone_evaluator.evaluate_lower_stop(
        state=CVTDynamicState.from_vector(projected),
        lower_stop_shift=limits.lower_stop_shift,
    )
    reaction = evaluation.stop_reaction
    if reaction is None:  # pragma: no cover - lower-stop evaluator invariant.
        raise RuntimeError("Lower-stop evaluation did not recover a stop reaction.")

    metadata = {
        "lower_stop_reaction": reaction,
        "impact": "perfectly_inelastic_axial_projection",
    }
    if reaction < 0.0:
        return HybridTransition(
            next_mode=CVTOperatingRegime.deadzone_free(),
            reason="lower_stop_impact_immediately_released_by_tensile_reaction",
            metadata=metadata,
            successor_state=projected,
        )

    return HybridTransition(
        next_mode=CVTOperatingRegime.deadzone_lower_stop(),
        reason="deadzone_lower_stop_reached_perfectly_inelastic_impact",
        metadata=metadata,
        successor_state=projected,
    )


def _resolve_engaged_transition(
    *,
    time: float,
    state: CVTDynamicState,
    vector: NDArray[np.float64],
    old_regime: CVTOperatingRegime,
    geometry_events: set[CVTRegimeEvent],
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    """Resolve one engaged event without letting belt reaction select neutral.

    Free engagement first reaches the low-ratio seat at ``s_engage``.  Only a
    later loss of the primary actuator's own closing force releases that seat
    to deadzone.  Contact events remain entirely inside the engaged closure.
    """

    assert old_regime.contact_regime is not None

    if old_regime.shift_constraint is CVTShiftConstraint.FREE:
        if CVTRegimeEvent.LOW_RATIO_SEAT_REACHED in geometry_events:
            return _resolve_low_ratio_seat_arrival(
                time=time,
                vector=vector,
                old_contact_regime=old_regime.contact_regime,
                contact_events=contact_events,
                limits=limits,
                evaluator=evaluator,
                switching_settings=switching_settings,
            )
        if CVTRegimeEvent.UPPER_STOP_REACHED in geometry_events:
            return _resolve_upper_stop_arrival(
                time=time,
                vector=vector,
                old_contact_regime=old_regime.contact_regime,
                contact_events=contact_events,
                limits=limits,
                evaluator=evaluator,
                switching_settings=switching_settings,
            )

    if old_regime.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
        if CVTRegimeEvent.PRIMARY_CLAMP_LOST in geometry_events:
            return _resolve_low_ratio_seat_disengagement(
                vector=vector,
                old_contact_regime=old_regime.contact_regime,
                limits=limits,
                evaluator=evaluator,
            )
        if CVTRegimeEvent.LOW_RATIO_SEAT_RELEASE in geometry_events:
            return _resolve_low_ratio_seat_release(
                time=time,
                vector=vector,
                old_contact_regime=old_regime.contact_regime,
                contact_events=contact_events,
                limits=limits,
                evaluator=evaluator,
                switching_settings=switching_settings,
            )

    if old_regime.shift_constraint is CVTShiftConstraint.UPPER_STOP:
        if CVTRegimeEvent.UPPER_STOP_RELEASE in geometry_events:
            return _resolve_upper_stop_release(
                time=time,
                vector=vector,
                old_contact_regime=old_regime.contact_regime,
                contact_events=contact_events,
                limits=limits,
                evaluator=evaluator,
                switching_settings=switching_settings,
            )

    if not contact_events:
        raise RuntimeError(
            "Engaged transition received no contact or relevant geometry event."
        )

    constraint = _engaged_constraint_for_operating_regime(old_regime)
    contact_transition = resolve_cvt_contact_transition(
        evaluator=evaluator,
        time=time,
        vector=vector,
        old_regime=old_regime.contact_regime,
        fired_event_names=contact_events,
        switching_settings=switching_settings,
        shift_constraint=constraint,
    )
    if contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata=contact_transition.metadata,
        )
    assert contact_transition.next_mode is not None
    next_mode = _engaged_regime_for_constraint(
        constraint=old_regime.shift_constraint,
        contact_regime=contact_transition.next_mode,
    )
    if next_mode == old_regime:
        # A re-stick zero can be a grazing contact-velocity root rather than a
        # change of topology or kinetic direction.  The contact event itself
        # is re-armed by its outgoing-acceleration guard; an explicit copied
        # state tells the generic segmented runner this continuation is
        # intentional rather than an unhandled no-op transition.
        return HybridTransition(
            next_mode=next_mode,
            reason="kinetic_zero_grazed_continued_same_contact_branch",
            metadata={
                **contact_transition.metadata,
                "continuation": "same_contact_branch_after_outgoing_kinetic_zero",
            },
            successor_state=np.array(vector, dtype=float, copy=True),
        )
    return HybridTransition(
        next_mode=next_mode,
        reason=contact_transition.reason,
        metadata=contact_transition.metadata,
    )


def _resolve_low_ratio_seat_arrival(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    """Enter the low-ratio seat before deciding whether neutral is permitted."""

    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.engagement_shift,
    )
    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
        evaluator=evaluator,
        switching_settings=switching_settings,
    )
    if contact_transition is not None and contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata={
                **contact_transition.metadata,
                "during": "low_ratio_seat_arrival_after_perfectly_inelastic_projection",
            },
            successor_state=projected,
        )

    seat_evaluation = evaluator.evaluate_vector(
        time=time,
        vector=projected,
        regime=contact_regime,
        shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
    )
    seat_reaction = seat_evaluation.low_ratio_seat_reaction
    if seat_reaction is None:  # pragma: no cover - constrained evaluator invariant.
        raise RuntimeError("Low-ratio seat evaluation did not recover a seat reaction.")

    projected_state = CVTDynamicState.from_vector(projected)
    primary_clamp = primary_independent_clamping_force_at_engagement(
        evaluator=evaluator,
        state=projected_state,
        limits=limits,
    )
    metadata: dict[str, object] = {
        "low_ratio_seat_reaction": seat_reaction,
        "primary_independent_clamping_force": primary_clamp,
        "impact": "perfectly_inelastic_axial_projection",
    }
    if contact_transition is not None:
        metadata["contact_transition_reason"] = contact_transition.reason
        metadata.update(contact_transition.metadata)

    # A negative primary mechanism force is the only route from the engaged
    # low-ratio seat into neutral.  The belt normal reaction is intentionally
    # diagnostic here, not a substitute disengagement trigger.
    if primary_clamp < 0.0:
        return HybridTransition(
            next_mode=CVTOperatingRegime.deadzone_free(),
            reason="primary_lost_clamp_at_low_ratio_seat_entered_deadzone",
            metadata={
                **metadata,
                "secondary_capture": "perfectly_inelastic_lumped_belt_secondary_capture",
            },
            successor_state=capture_belt_to_secondary_at_disengagement(
                evaluator=evaluator,
                state=projected_state,
                limits=limits,
            ),
        )

    # The seat itself is unilateral.  When it would need to pull open, release
    # to free *engaged* motion; the primary still has nonnegative clamp.
    if seat_reaction < 0.0:
        return HybridTransition(
            next_mode=CVTOperatingRegime.engaged_free(contact_regime=contact_regime),
            reason="low_ratio_seat_impact_immediately_released_into_engaged_shift",
            metadata=metadata,
            successor_state=projected,
        )

    return HybridTransition(
        next_mode=CVTOperatingRegime.engaged_low_ratio_seat(
            contact_regime=contact_regime,
        ),
        reason="low_ratio_seat_reached_perfectly_inelastic_projection",
        metadata=metadata,
        successor_state=projected,
    )


def _resolve_low_ratio_seat_disengagement(
    *,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
) -> HybridTransition[CVTOperatingRegime]:
    """Release the seated belt to deadzone after primary clamp is lost."""

    del old_contact_regime
    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.engagement_shift,
    )
    projected_state = CVTDynamicState.from_vector(projected)
    primary_clamp = primary_independent_clamping_force_at_engagement(
        evaluator=evaluator,
        state=projected_state,
        limits=limits,
    )
    if primary_clamp > _PRIMARY_CLAMP_EVENT_TOLERANCE:
        raise RuntimeError(
            "PRIMARY_CLAMP_LOST transition received a materially positive primary clamp force."
        )
    return HybridTransition(
        next_mode=CVTOperatingRegime.deadzone_free(),
        reason="primary_clamp_lost_released_low_ratio_seat_into_deadzone",
        metadata={
            "primary_independent_clamping_force": primary_clamp,
            "secondary_capture": "perfectly_inelastic_lumped_belt_secondary_capture",
        },
        successor_state=capture_belt_to_secondary_at_disengagement(
            evaluator=evaluator,
            state=projected_state,
            limits=limits,
        ),
    )


def _resolve_low_ratio_seat_release(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    """Release a tensile low-ratio seat into free engaged shift."""

    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.engagement_shift,
    )
    projected_state = CVTDynamicState.from_vector(projected)
    primary_clamp = primary_independent_clamping_force_at_engagement(
        evaluator=evaluator,
        state=projected_state,
        limits=limits,
    )
    if primary_clamp < 0.0:
        return _resolve_low_ratio_seat_disengagement(
            vector=projected,
            old_contact_regime=old_contact_regime,
            limits=limits,
            evaluator=evaluator,
        )

    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.FREE,
        evaluator=evaluator,
        switching_settings=switching_settings,
    )
    if contact_transition is not None and contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata={
                **contact_transition.metadata,
                "during": "low_ratio_seat_release_into_free_engaged_shift",
            },
            successor_state=projected,
        )

    metadata: dict[str, object] = {
        "release": "low_ratio_seat_reaction_crossed_zero",
        "primary_independent_clamping_force": primary_clamp,
    }
    if contact_transition is not None:
        metadata["contact_transition_reason"] = contact_transition.reason
        metadata.update(contact_transition.metadata)
    return HybridTransition(
        next_mode=CVTOperatingRegime.engaged_free(contact_regime=contact_regime),
        reason="low_ratio_seat_released_by_tensile_reaction",
        metadata=metadata,
        successor_state=projected,
    )


def _engaged_constraint_for_operating_regime(
    regime: CVTOperatingRegime,
) -> EngagedShiftConstraint:
    if regime.shift_constraint is CVTShiftConstraint.FREE:
        return EngagedShiftConstraint.FREE
    if regime.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
        return EngagedShiftConstraint.LOW_RATIO_SEAT
    if regime.shift_constraint is CVTShiftConstraint.UPPER_STOP:
        return EngagedShiftConstraint.UPPER_STOP
    raise ValueError(
        f"Unsupported engaged shift constraint: {regime.shift_constraint!r}."
    )


def _engaged_regime_for_constraint(
    *,
    constraint: CVTShiftConstraint,
    contact_regime: ContactRegime,
) -> CVTOperatingRegime:
    if constraint is CVTShiftConstraint.FREE:
        return CVTOperatingRegime.engaged_free(contact_regime=contact_regime)
    if constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
        return CVTOperatingRegime.engaged_low_ratio_seat(contact_regime=contact_regime)
    if constraint is CVTShiftConstraint.UPPER_STOP:
        return CVTOperatingRegime.engaged_upper_stop(contact_regime=contact_regime)
    raise ValueError(f"Unsupported engaged shift constraint: {constraint!r}.")


def _resolve_upper_stop_arrival(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    """Apply the axial impact, then accept or immediately release the stop.

    The stop is entered only after solving the *constrained* closure.  That
    matters because contact lambdas, normals, and static admissibility at fixed
    ratio need not equal their free-shift values at the instant of impact.
    """

    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.upper_stop_shift,
    )
    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.UPPER_STOP,
        evaluator=evaluator,
        switching_settings=switching_settings,
    )
    if contact_transition is not None and contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata={
                **contact_transition.metadata,
                "during": "upper_stop_arrival_after_perfectly_inelastic_impact",
            },
            successor_state=projected,
        )

    evaluation = evaluator.evaluate_vector(
        time=time,
        vector=projected,
        regime=contact_regime,
        shift_constraint=EngagedShiftConstraint.UPPER_STOP,
    )
    reaction = evaluation.upper_stop_reaction
    if reaction is None:  # pragma: no cover - constrained evaluator invariant.
        raise RuntimeError("Upper-stop evaluation did not recover a stop reaction.")

    metadata = {
        "upper_stop_reaction": reaction,
        "impact": "perfectly_inelastic_axial_projection",
    }
    if contact_transition is not None:
        metadata["contact_transition_reason"] = contact_transition.reason
        metadata.update(contact_transition.metadata)

    # A unilateral stop may push but cannot pull.  If the post-impact
    # constrained reaction is already negative, the perfectly inelastic impact
    # still occurs, but the next continuous segment must immediately be free.
    if reaction < 0.0:
        return HybridTransition(
            next_mode=CVTOperatingRegime.engaged_free(
                contact_regime=contact_regime,
            ),
            reason="upper_stop_impact_immediately_released_by_tensile_reaction",
            metadata=metadata,
            successor_state=projected,
        )

    return HybridTransition(
        next_mode=CVTOperatingRegime.engaged_upper_stop(
            contact_regime=contact_regime,
        ),
        reason="upper_stop_reached_perfectly_inelastic_impact",
        metadata=metadata,
        successor_state=projected,
    )


def _resolve_upper_stop_release(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> HybridTransition[CVTOperatingRegime]:
    """Release the high stop and re-evaluate contact in free shift.

    Contact events can coincide with stop release.  Candidate branch selection
    then belongs to the *free* closure, because that is the successor physics.
    We also inspect free-closure capacity at the endpoint so a negative static
    margin cannot be silently carried into a fresh segment where its event
    would start already below zero.
    """

    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.upper_stop_shift,
    )
    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.FREE,
        evaluator=evaluator,
        switching_settings=switching_settings,
    )
    if contact_transition is not None and contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata={
                **contact_transition.metadata,
                "during": "upper_stop_release_into_free_shift",
            },
            successor_state=projected,
        )

    metadata: dict[str, object] = {
        "release": "upper_stop_reaction_crossed_zero",
    }
    if contact_transition is not None:
        metadata["contact_transition_reason"] = contact_transition.reason
        metadata.update(contact_transition.metadata)

    return HybridTransition(
        next_mode=CVTOperatingRegime.engaged_free(
            contact_regime=contact_regime,
        ),
        reason="upper_stop_released_by_tensile_reaction",
        metadata=metadata,
        successor_state=projected,
    )


def _resolve_contact_at_constraint(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    constraint: EngagedShiftConstraint,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> tuple[ContactRegime, HybridTransition[ContactRegime] | None]:
    """Resolve supplied plus immediately-active contact violations once.

    ``solve_ivp`` terminal events only detect crossings.  At a new stop or a
    newly released constraint, the closure changes discontinuously while the
    continuous state does not.  This helper explicitly re-checks normals and
    static margins under the successor constraint so the next segment never
    begins with a contact event already violated.
    """

    evaluation = evaluator.evaluate_vector(
        time=time,
        vector=vector,
        regime=old_contact_regime,
        shift_constraint=constraint,
    )
    event_names = list(contact_events)
    event_names.extend(
        _immediately_violated_contact_event_names(
            evaluation=evaluation,
            evaluator=evaluator,
            switching_settings=switching_settings,
        )
    )
    event_names = list(dict.fromkeys(event_names))
    if not event_names:
        return old_contact_regime, None

    transition = resolve_cvt_contact_transition(
        evaluator=evaluator,
        time=time,
        vector=vector,
        old_regime=old_contact_regime,
        fired_event_names=tuple(event_names),
        switching_settings=switching_settings,
        shift_constraint=constraint,
    )
    if transition.terminates:
        return old_contact_regime, transition
    assert transition.next_mode is not None
    return transition.next_mode, transition


def _immediately_violated_contact_event_names(
    *,
    evaluation: "CVTContactEvaluation",
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
) -> tuple[str, ...]:
    """Return normal/static conditions that are already invalid at an endpoint."""

    names: list[str] = []
    if evaluation.normal_primary <= switching_settings.normal_resultant_floor:
        names.append(CVTContactEvent.PRIMARY_NORMAL_FLOOR.value)
    if evaluation.normal_secondary <= switching_settings.normal_resultant_floor:
        names.append(CVTContactEvent.SECONDARY_NORMAL_FLOOR.value)

    for interface in evaluation.regime.mode.sticking_interfaces:
        margin = evaluation.static_margin_at(
            interface,
            traction_law=evaluator.traction_law,
        )
        if margin <= switching_settings.stick_exit_static_margin:
            names.append(
                (
                    CVTContactEvent.PRIMARY_STATIC_CAPACITY
                    if interface is ContactInterface.PRIMARY
                    else CVTContactEvent.SECONDARY_STATIC_CAPACITY
                ).value
            )
    return tuple(names)


def _geometry_events_from(names: set[str]) -> set[CVTRegimeEvent]:
    events: set[CVTRegimeEvent] = set()
    for event in CVTRegimeEvent:
        if event.value in names:
            events.add(event)
    return events


_REGIME_EVENT_NAMES = frozenset(event.value for event in CVTRegimeEvent)


def _validate_state_within_limits(
    *,
    state: CVTDynamicState,
    limits: CVTShiftOperatingLimits,
    tolerance: float = 0.0,
) -> None:
    lower = limits.lower_stop_shift - tolerance
    upper = limits.upper_stop_shift + tolerance
    if not lower <= state.shift_position <= upper:
        raise ValueError(
            "Shift position lies outside CVT operating limits: "
            f"{state.shift_position:.9g} not in [{limits.lower_stop_shift:.9g}, "
            f"{limits.upper_stop_shift:.9g}]."
        )
