"""Event-guided CVT operating-regime transitions and state projections.

This module owns physical event successors and explicit impact/capture resets.
The engaged low-ratio seat, upper-stop, and deadzone lower-stop closures are
all available to the operating dispatcher.  No state clamp is hidden inside an ODE right-hand
side: each reset is returned through ``HybridTransition.successor_state``.
"""

from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import ContactInterface, ContactRegime
from cinder.model.cvt.dynamics.deadzone import (
    DeadzoneDynamicsEvaluator,
    build_deadzone_snapshot,
)
from cinder.model.cvt.dynamics.deadzone.free import solve_deadzone_primary_free
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system.ports import CVTShaftBoundaryValues

from .cvt_contact_events import CVTContactEvent
from .cvt_contact_switching import (
    CVTContactSwitchSettings,
    resolve_cvt_contact_transition,
)
from .cvt_impact import (
    CVTImpactProjection,
    CVTVelocityTopology,
    project_cvt_velocity_topology,
)
from .cvt_operating_limits import CVTShiftOperatingLimits
from .cvt_regime import CVTEngagementState, CVTOperatingRegime, CVTShiftConstraint
from .cvt_regime_events import CVTRegimeEvent
from .hybrid import HybridTransition
from .state import CVTState

if TYPE_CHECKING:
    from .cvt_contact import CVTContactEvaluation, EngagedCVTContactEvaluator


def classify_initial_cvt_regime(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
    state: CVTState,
    limits: CVTShiftOperatingLimits,
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> CVTOperatingRegime:
    """Classify an initial state into one physically meaningful regime.

    At the exact engagement position, a nonnegative shift velocity is treated
    as a closing/engaged state; a negative velocity is treated as opening into
    deadzone.  Exact-stop initial states are represented by their matching
    constrained regime; the operating dispatcher then checks unilateral
    reaction admissibility before integration begins.
    """

    if not isfinite(time):
        raise ValueError("time must be finite.")
    _validate_state_within_limits(state=state, limits=limits)
    s = state.shift_position
    if limits.has_deadzone:
        if s == limits.lower_stop_shift:
            return CVTOperatingRegime.deadzone_lower_stop()
        if s < limits.engagement_shift or (
            s == limits.engagement_shift and state.shift_speed < 0.0
        ):
            return CVTOperatingRegime.deadzone_free()

    contact = evaluator.classify_initial_regime_at_time(
        time=time,
        state=state,
        switching_settings=switching_settings,
        shaft_boundaries=shaft_boundaries,
    )
    if s == limits.upper_stop_shift:
        return CVTOperatingRegime.engaged_upper_stop(contact_regime=contact)
    if not limits.has_deadzone and s == limits.lower_stop_shift:
        return CVTOperatingRegime.engaged_low_ratio_seat(contact_regime=contact)
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
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Resolve only successors allowed by the active physical regime.

    Geometry/stop events take precedence over contact events because they
    change which governing equations remain valid.  Contact events are then
    delegated to the established engaged-contact resolver and wrapped back
    into the same free/upper-stop operating constraint.
    """

    if not isfinite(time):
        raise ValueError("time must be finite.")
    state = CVTState.from_vector(vector)
    _validate_state_within_limits(state=state, limits=limits, tolerance=1.0e-8)
    fired = set(fired_event_names)
    geometry_events = _geometry_events_from(fired)
    contact_events = tuple(
        name for name in fired_event_names if name not in _REGIME_EVENT_NAMES
    )

    if old_regime.engagement is CVTEngagementState.DEADZONE:
        if not limits.has_deadzone:
            raise RuntimeError(
                "Deadzone transition requested for a zero-width deadzone topology."
            )
        return _resolve_deadzone_transition(
            time=time,
            state=state,
            vector=vector,
            old_regime=old_regime,
            geometry_events=geometry_events,
            contact_events=contact_events,
            limits=limits,
            evaluator=evaluator,
            deadzone_evaluator=deadzone_evaluator,
            switching_settings=switching_settings,
            shaft_boundaries=shaft_boundaries,
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
        shaft_boundaries=shaft_boundaries,
    )


def project_inelastic_shift_constraint(
    *,
    vector: NDArray[np.float64],
    shift_position: float,
) -> NDArray[np.float64]:
    """Snap an already constrained/evaluation state onto an exact shift boundary.

    This is *not* the physical impact map.  Finite-speed arrivals use the
    mass-metric projection in :mod:`cvt_impact`.  This helper is used after a
    constraint is already active (or for endpoint admissibility checks), where
    ``s_dot`` should be zero apart from numerical roundoff.
    """

    projected = np.array(vector, dtype=float, copy=True)
    projected[3] = float(shift_position)
    projected[4] = 0.0
    return projected


def primary_contact_separation_at_engagement(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    time: float,
    vector: NDArray[np.float64],
    contact_regime: ContactRegime,
    limits: CVTShiftOperatingLimits,
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> tuple[float, float, float]:
    """Return the seated-primary separation indicator and its two margins.

    Primary disengagement is a unilateral contact decision, not an actuator
    sign test. At the low-ratio seat it is permitted only when both

      * the solved physical primary normal resultant has fallen to its floor;
      * the primary, re-evaluated with belt contact removed, tends to accelerate
        in the opening direction (negative global ``s`` acceleration).

    The returned scalar has force units and is non-positive only when both
    conditions hold. The acceleration condition is converted to an equivalent
    axial-force margin using the primary local shift-inertia gain, so the
    ``max`` combines like-dimensional quantities. This produces one meaningful
    hybrid event rather than a normal-force event followed by a no-op guard.
    """

    projected = project_inelastic_shift_constraint(
        vector=vector, shift_position=limits.engagement_shift
    )
    seat = evaluator.evaluate_vector(
        time=time,
        vector=projected,
        regime=contact_regime,
        shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
        shaft_boundaries=shaft_boundaries,
    )
    normal_margin = seat.normal_primary - switching_settings.normal_resultant_floor

    contact_free_state = CVTState.from_vector(projected)
    deadzone_snapshot = build_deadzone_snapshot(
        time=time,
        model=evaluator.model,
        state=contact_free_state,
        shaft_boundaries=shaft_boundaries,
    )
    _alpha_p, opening_acceleration = solve_deadzone_primary_free(deadzone_snapshot)
    opening_force_margin = (
        deadzone_snapshot.primary_axial_inertia.local_shift_acceleration_gain
        * opening_acceleration
    )
    indicator = max(normal_margin, opening_force_margin)
    return float(indicator), float(seat.normal_primary), float(opening_acceleration)


def capture_belt_to_secondary_at_disengagement(
    *,
    evaluator: "EngagedCVTContactEvaluator",
    state: CVTState,
    limits: CVTShiftOperatingLimits,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> CVTImpactProjection:
    """Enter deadzone with a momentum-consistent belt/secondary capture.

    This generalized projection also transfers any secondary movable-sheave
    helix-relative angular momentum into the secondary shaft when the closed
    stop removes that relative motion.  It replaces the old scalar lumped
    inertia average, which could not account for helix cross momentum.
    """

    projection = project_cvt_velocity_topology(
        model=evaluator.model,
        vector=state.as_vector(),
        shift_position=limits.engagement_shift,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.DEADZONE,
        shaft_boundaries=shaft_boundaries,
        lock_secondary_belt=True,
    )
    return projection


def _resolve_deadzone_transition(
    *,
    time: float,
    state: CVTState,
    vector: NDArray[np.float64],
    old_regime: CVTOperatingRegime,
    geometry_events: set[CVTRegimeEvent],
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    deadzone_evaluator: DeadzoneDynamicsEvaluator,
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    if contact_events:
        raise RuntimeError("Deadzone cannot receive engaged-contact event names.")

    if old_regime.shift_constraint is CVTShiftConstraint.FREE:
        if CVTRegimeEvent.LOWER_STOP_REACHED in geometry_events:
            return _resolve_lower_stop_arrival(
                time=time,
                vector=vector,
                limits=limits,
                deadzone_evaluator=deadzone_evaluator,
                shaft_boundaries=shaft_boundaries,
            )
        if CVTRegimeEvent.ENGAGEMENT_REACHED in geometry_events:
            # Rigid contact activates secondary axial/helix kinematics that do
            # not exist in deadzone.  Carry the incoming generalized momentum
            # into that larger moving set instead of copying s_dot unchanged,
            # which would create kinetic energy.  The pre-existing
            # belt-secondary lock remains active through the capture.
            capture = project_cvt_velocity_topology(
                model=evaluator.model,
                vector=vector,
                shift_position=limits.engagement_shift,
                from_topology=CVTVelocityTopology.DEADZONE,
                to_topology=CVTVelocityTopology.ENGAGED,
                shaft_boundaries=shaft_boundaries,
                lock_secondary_belt=True,
            )
            engaged_vector = capture.successor_state
            engaged_state = CVTState.from_vector(engaged_vector)
            contact = evaluator.classify_initial_regime_at_time(
                time=time,
                state=engaged_state,
                switching_settings=switching_settings,
                shaft_boundaries=shaft_boundaries,
            )
            return HybridTransition(
                next_mode=CVTOperatingRegime.engaged_free(contact_regime=contact),
                reason="primary_closed_into_engaged_contact",
                metadata={
                    **capture.metadata(),
                    "capture": "deadzone_to_engaged_mass_metric_projection",
                },
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
    time: float,
    vector: NDArray[np.float64],
    limits: CVTShiftOperatingLimits,
    deadzone_evaluator: DeadzoneDynamicsEvaluator,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Apply the low-stop impact, then accept or immediately release it.

    The lower stop is unilateral.  As with the engaged upper stop, its
    admissibility must be checked under the *constrained* post-impact RHS
    before beginning the next segment; otherwise a negative reaction at the
    endpoint would never produce a downward crossing event.
    """

    impact = project_cvt_velocity_topology(
        model=deadzone_evaluator.model,
        vector=vector,
        shift_position=limits.lower_stop_shift,
        from_topology=CVTVelocityTopology.DEADZONE,
        to_topology=CVTVelocityTopology.DEADZONE,
        shaft_boundaries=shaft_boundaries,
        stop_shift_velocity=True,
        lock_secondary_belt=True,
    )
    projected = impact.successor_state
    evaluation = deadzone_evaluator.evaluate_lower_stop_at_time(
        time=time,
        state=CVTState.from_vector(projected),
        lower_stop_shift=limits.lower_stop_shift,
        shaft_boundaries=shaft_boundaries,
    )
    reaction = evaluation.stop_reaction
    if reaction is None:  # pragma: no cover - lower-stop evaluator invariant.
        raise RuntimeError("Lower-stop evaluation did not recover a stop reaction.")

    metadata = {
        "lower_stop_reaction": reaction,
        "impact": "perfectly_inelastic_mass_metric_projection",
        **impact.metadata(),
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
    state: CVTState,
    vector: NDArray[np.float64],
    old_regime: CVTOperatingRegime,
    geometry_events: set[CVTRegimeEvent],
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Resolve one engaged event with unilateral seat/contact separation.

    Free engagement first reaches the low-ratio seat at ``s_engage``. The seat
    releases to deadzone only when primary normal support is exhausted *and*
    the contact-free primary tends to accelerate open. Other contact events
    remain inside the engaged closure.
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
                shaft_boundaries=shaft_boundaries,
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
                shaft_boundaries=shaft_boundaries,
            )

    if old_regime.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
        if CVTRegimeEvent.PRIMARY_CONTACT_SEPARATION in geometry_events:
            return _resolve_low_ratio_seat_disengagement(
                time=time,
                vector=vector,
                old_contact_regime=old_regime.contact_regime,
                limits=limits,
                evaluator=evaluator,
                switching_settings=switching_settings,
                shaft_boundaries=shaft_boundaries,
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
                shaft_boundaries=shaft_boundaries,
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
                shaft_boundaries=shaft_boundaries,
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
        shaft_boundaries=shaft_boundaries,
    )
    if contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata=contact_transition.metadata,
        )
    assert contact_transition.next_mode is not None
    next_contact_regime = contact_transition.next_mode

    # A discrete contact-topology change can jump the recovered reaction of an
    # already-active unilateral seat/stop across zero. Recheck the successor
    # branch at the same event time so the next segment never starts with a
    # constraint that would have to pull rather than push.
    constraint_release = _constraint_release_after_contact_transition(
        time=time,
        vector=vector,
        shift_constraint=old_regime.shift_constraint,
        contact_regime=next_contact_regime,
        evaluator=evaluator,
        shaft_boundaries=shaft_boundaries,
    )
    if constraint_release is not None:
        release_mode, release_reason, reaction_name, reaction_value = constraint_release
        return HybridTransition(
            next_mode=release_mode,
            reason=release_reason,
            metadata={
                **contact_transition.metadata,
                "contact_transition_reason": contact_transition.reason,
                reaction_name: reaction_value,
                "constraint_release": "contact_topology_changed_unilateral_reaction_sign",
            },
            successor_state=np.array(vector, dtype=float, copy=True),
        )

    next_mode = _engaged_regime_for_constraint(
        constraint=old_regime.shift_constraint,
        contact_regime=next_contact_regime,
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


def _constraint_release_after_contact_transition(
    *,
    time: float,
    vector: NDArray[np.float64],
    shift_constraint: CVTShiftConstraint,
    contact_regime: ContactRegime,
    evaluator: "EngagedCVTContactEvaluator",
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> tuple[CVTOperatingRegime, str, str, float] | None:
    """Release a unilateral shift constraint invalidated by a contact switch."""

    if shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
        evaluation = evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=contact_regime,
            shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
            shaft_boundaries=shaft_boundaries,
        )
        reaction = evaluation.low_ratio_seat_reaction
        if reaction is None:
            raise RuntimeError(
                "Low-ratio seat evaluation did not recover a seat reaction after contact transition."
            )
        if reaction < 0.0:
            return (
                CVTOperatingRegime.engaged_free(contact_regime=contact_regime),
                "contact_transition_released_low_ratio_seat_by_tensile_reaction",
                "low_ratio_seat_reaction",
                float(reaction),
            )
        return None

    if shift_constraint is CVTShiftConstraint.UPPER_STOP:
        evaluation = evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=contact_regime,
            shift_constraint=EngagedShiftConstraint.UPPER_STOP,
            shaft_boundaries=shaft_boundaries,
        )
        reaction = evaluation.upper_stop_reaction
        if reaction is None:
            raise RuntimeError(
                "Upper-stop evaluation did not recover a stop reaction after contact transition."
            )
        if reaction < 0.0:
            return (
                CVTOperatingRegime.engaged_free(contact_regime=contact_regime),
                "contact_transition_released_upper_stop_by_tensile_reaction",
                "upper_stop_reaction",
                float(reaction),
            )
        return None

    return None


def _resolve_low_ratio_seat_arrival(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Resolve return to minimum ratio as a secondary closed-stop impact.

    The secondary movable sheave, not the primary, physically reaches a hard
    stop at this boundary.  For finite opening shift speed the stop arrests the
    secondary axial/helix motion and transfers its relative angular momentum
    into the secondary shaft, while the primary is free to separate and carry
    its remaining axial momentum into deadzone.

    Repeated rigid make/break captures can converge geometrically to zero
    velocity (the usual Zeno limit of a plastic impact model).  Only once the
    kinetic energy that would be removed by additionally seating the shared
    shift coordinate falls below floating-point energy resolution do we close
    that mathematical limit and enter the ordinary fixed low-ratio seat.
    """

    lock_primary, lock_secondary = _sticking_belt_locks(old_contact_regime)
    hypothetical_seat = project_cvt_velocity_topology(
        model=evaluator.model,
        vector=vector,
        shift_position=limits.engagement_shift,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.ENGAGED,
        shaft_boundaries=shaft_boundaries,
        stop_shift_velocity=True,
        lock_primary_belt=lock_primary,
        lock_secondary_belt=lock_secondary,
    )
    energy_resolution = (
        8192.0 * np.finfo(float).eps * max(1.0, hypothetical_seat.pre_kinetic_energy)
    )

    if hypothetical_seat.dissipated_energy > energy_resolution:
        # This is a real secondary-stop collision followed by primary
        # separation, not a shared-coordinate impact.  The deadzone topology
        # removes secondary axial/helix motion, keeps the primary axial degree
        # of freedom, and retains the imposed belt-secondary lock.
        impact = project_cvt_velocity_topology(
            model=evaluator.model,
            vector=vector,
            shift_position=limits.engagement_shift,
            from_topology=CVTVelocityTopology.ENGAGED,
            to_topology=CVTVelocityTopology.DEADZONE,
            shaft_boundaries=shaft_boundaries,
            lock_secondary_belt=True,
        )
        return HybridTransition(
            next_mode=CVTOperatingRegime.deadzone_free(),
            reason="secondary_closed_stop_impact_primary_separated_into_deadzone",
            metadata={
                **impact.metadata(),
                "impact": "secondary_closed_stop_mass_metric_projection",
                "z_to_seat_energy_resolution_J": energy_resolution,
            },
            successor_state=impact.successor_state,
        )

    projected = hypothetical_seat.successor_state
    contact_events = tuple(
        name
        for name in contact_events
        if name != CVTContactEvent.PRIMARY_NORMAL_FLOOR.value
    )
    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
        evaluator=evaluator,
        switching_settings=switching_settings,
        shaft_boundaries=shaft_boundaries,
        ignore_primary_normal_floor=True,
    )
    if contact_transition is not None and contact_transition.terminates:
        return HybridTransition(
            next_mode=None,
            reason=contact_transition.reason,
            metadata={
                **contact_transition.metadata,
                **hypothetical_seat.metadata(),
                "during": "low_ratio_seat_z_limit_completion",
            },
            successor_state=projected,
        )

    seat_evaluation = evaluator.evaluate_vector(
        time=time,
        vector=projected,
        regime=contact_regime,
        shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
        shaft_boundaries=shaft_boundaries,
    )
    seat_reaction = seat_evaluation.low_ratio_seat_reaction
    if seat_reaction is None:  # pragma: no cover - constrained evaluator invariant.
        raise RuntimeError("Low-ratio seat evaluation did not recover a seat reaction.")

    separation_indicator, primary_normal, opening_acceleration = (
        primary_contact_separation_at_engagement(
            evaluator=evaluator,
            time=time,
            vector=projected,
            contact_regime=contact_regime,
            limits=limits,
            switching_settings=switching_settings,
            shaft_boundaries=shaft_boundaries,
        )
    )
    metadata: dict[str, object] = {
        "low_ratio_seat_reaction": seat_reaction,
        "primary_normal_resultant": primary_normal,
        "contact_free_primary_shift_acceleration": opening_acceleration,
        "primary_separation_indicator": separation_indicator,
        "impact": "zero_velocity_z_limit_secondary_stop_seat_completion",
        "z_to_seat_energy_resolution_J": energy_resolution,
        **hypothetical_seat.metadata(),
    }
    if contact_transition is not None:
        metadata["contact_transition_reason"] = contact_transition.reason
        metadata.update(contact_transition.metadata)

    if separation_indicator <= 0.0:
        deadzone_capture = project_cvt_velocity_topology(
            model=evaluator.model,
            vector=projected,
            shift_position=limits.engagement_shift,
            from_topology=CVTVelocityTopology.ENGAGED,
            to_topology=CVTVelocityTopology.DEADZONE,
            shaft_boundaries=shaft_boundaries,
            lock_secondary_belt=True,
        )
        return HybridTransition(
            next_mode=CVTOperatingRegime.deadzone_free(),
            reason="primary_contact_separated_at_low_ratio_seat_entered_deadzone",
            metadata={**metadata, **deadzone_capture.metadata()},
            successor_state=deadzone_capture.successor_state,
        )

    if seat_reaction < 0.0:
        return HybridTransition(
            next_mode=CVTOperatingRegime.engaged_free(contact_regime=contact_regime),
            reason="low_ratio_secondary_stop_immediately_released_into_engaged_shift",
            metadata=metadata,
            successor_state=projected,
        )

    return HybridTransition(
        next_mode=CVTOperatingRegime.engaged_low_ratio_seat(
            contact_regime=contact_regime,
        ),
        reason="low_ratio_secondary_stop_seated_after_z_limit",
        metadata=metadata,
        successor_state=projected,
    )


def _resolve_low_ratio_seat_disengagement(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Release the seated primary only after unilateral contact separates."""

    projected = project_inelastic_shift_constraint(
        vector=vector, shift_position=limits.engagement_shift
    )
    indicator, primary_normal, opening_acceleration = (
        primary_contact_separation_at_engagement(
            evaluator=evaluator,
            time=time,
            vector=projected,
            contact_regime=old_contact_regime,
            limits=limits,
            switching_settings=switching_settings,
            shaft_boundaries=shaft_boundaries,
        )
    )
    if indicator > 0.0:
        raise RuntimeError(
            "PRIMARY_CONTACT_SEPARATION fired while unilateral contact remained admissible."
        )
    projected_state = CVTState.from_vector(projected)
    capture = capture_belt_to_secondary_at_disengagement(
        evaluator=evaluator,
        state=projected_state,
        limits=limits,
        shaft_boundaries=shaft_boundaries,
    )
    return HybridTransition(
        next_mode=CVTOperatingRegime.deadzone_free(),
        reason="primary_contact_separated_released_low_ratio_seat_into_deadzone",
        metadata={
            "primary_normal_resultant": primary_normal,
            "contact_free_primary_shift_acceleration": opening_acceleration,
            "primary_separation_indicator": indicator,
            "secondary_capture": "mass_metric_belt_secondary_capture",
            **capture.metadata(),
        },
        successor_state=capture.successor_state,
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
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Release a tensile low-ratio seat into free engaged shift."""

    projected = project_inelastic_shift_constraint(
        vector=vector,
        shift_position=limits.engagement_shift,
    )
    separation_indicator, primary_normal, opening_acceleration = (
        primary_contact_separation_at_engagement(
            evaluator=evaluator,
            time=time,
            vector=projected,
            contact_regime=old_contact_regime,
            limits=limits,
            switching_settings=switching_settings,
            shaft_boundaries=shaft_boundaries,
        )
    )
    if separation_indicator <= 0.0:
        return _resolve_low_ratio_seat_disengagement(
            time=time,
            vector=projected,
            old_contact_regime=old_contact_regime,
            limits=limits,
            evaluator=evaluator,
            switching_settings=switching_settings,
            shaft_boundaries=shaft_boundaries,
        )

    contact_events = tuple(
        name
        for name in contact_events
        if name != CVTContactEvent.PRIMARY_NORMAL_FLOOR.value
    )
    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.FREE,
        evaluator=evaluator,
        switching_settings=switching_settings,
        shaft_boundaries=shaft_boundaries,
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
        "primary_normal_resultant": primary_normal,
        "contact_free_primary_shift_acceleration": opening_acceleration,
        "primary_separation_indicator": separation_indicator,
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


def _sticking_belt_locks(contact_regime: ContactRegime) -> tuple[bool, bool]:
    """Return which no-slip constraints should survive an axial impact."""

    sticking = set(contact_regime.mode.sticking_interfaces)
    return (
        ContactInterface.PRIMARY in sticking,
        ContactInterface.SECONDARY in sticking,
    )


def _resolve_upper_stop_arrival(
    *,
    time: float,
    vector: NDArray[np.float64],
    old_contact_regime: ContactRegime,
    contact_events: tuple[str, ...],
    limits: CVTShiftOperatingLimits,
    evaluator: "EngagedCVTContactEvaluator",
    switching_settings: CVTContactSwitchSettings,
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
) -> HybridTransition[CVTOperatingRegime]:
    """Apply the axial impact, then accept or immediately release the stop.

    The stop is entered only after solving the *constrained* closure.  That
    matters because contact lambdas, normals, and static admissibility at fixed
    ratio need not equal their free-shift values at the instant of impact.
    """

    lock_primary, lock_secondary = _sticking_belt_locks(old_contact_regime)
    impact = project_cvt_velocity_topology(
        model=evaluator.model,
        vector=vector,
        shift_position=limits.upper_stop_shift,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.ENGAGED,
        shaft_boundaries=shaft_boundaries,
        stop_shift_velocity=True,
        lock_primary_belt=lock_primary,
        lock_secondary_belt=lock_secondary,
    )
    projected = impact.successor_state
    contact_regime, contact_transition = _resolve_contact_at_constraint(
        time=time,
        vector=projected,
        old_contact_regime=old_contact_regime,
        contact_events=contact_events,
        constraint=EngagedShiftConstraint.UPPER_STOP,
        evaluator=evaluator,
        switching_settings=switching_settings,
        shaft_boundaries=shaft_boundaries,
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
        shaft_boundaries=shaft_boundaries,
    )
    reaction = evaluation.upper_stop_reaction
    if reaction is None:  # pragma: no cover - constrained evaluator invariant.
        raise RuntimeError("Upper-stop evaluation did not recover a stop reaction.")

    metadata = {
        "upper_stop_reaction": reaction,
        "impact": "perfectly_inelastic_mass_metric_projection",
        **impact.metadata(),
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
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
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
        shaft_boundaries=shaft_boundaries,
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
    shaft_boundaries: CVTShaftBoundaryValues | None = None,
    ignore_primary_normal_floor: bool = False,
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
        shaft_boundaries=shaft_boundaries,
    )
    event_names = list(contact_events)
    event_names.extend(
        _immediately_violated_contact_event_names(
            evaluation=evaluation,
            evaluator=evaluator,
            switching_settings=switching_settings,
        )
    )
    if ignore_primary_normal_floor:
        event_names = [
            name
            for name in event_names
            if name != CVTContactEvent.PRIMARY_NORMAL_FLOOR.value
        ]
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
        shaft_boundaries=shaft_boundaries,
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
    state: CVTState,
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
