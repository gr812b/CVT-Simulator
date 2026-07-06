"""System-level physical admissibility checks for hybrid CVT trajectories.

This module intentionally sits above the individual contact/stop solvers.  It
samples completed hybrid segments and checks the invariants that should remain
true regardless of how a segment was reached.  It is a diagnostic harness, not
a unit-test framework and not a replacement for calibration/validation.

The checks deliberately preserve the active regime split:

* deadzone checks use the imposed belt--secondary lock;
* engaged checks use the selected contact closure;
* lower and upper stops are checked as unilateral constraints;
* transition resets are inspected separately from the pre-event segment state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING, Iterable

import numpy as np
from numpy.typing import NDArray

from cinder.model.cvt.contact import ContactInterface
from cinder.model.cvt.dynamics.deadzone import DeadzoneEvaluation
from cinder.results import inspect_cvt_state

from cinder.execution.hybrid.cvt_contact import CVTContactEvaluation
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTOperatingRegime,
    CVTShiftConstraint,
)
from cinder.execution.hybrid.hybrid import HybridIntegrationResult
from cinder.execution.hybrid.state import CVTDynamicState

if TYPE_CHECKING:
    from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingHybridSystem


class CVTInvariant(str, Enum):
    """Named physical statements checked over a completed hybrid trajectory."""

    FINITE_STATE = "finite_state"
    FINITE_DERIVATIVE = "finite_derivative"
    SHIFT_WITHIN_OPERATING_LIMITS = "shift_within_operating_limits"
    MODE_POSITION_DOMAIN = "mode_position_domain"
    DEADZONE_BELT_SECONDARY_SPEED_LOCK = "deadzone_belt_secondary_speed_lock"
    DEADZONE_BELT_SECONDARY_ACCELERATION_LOCK = (
        "deadzone_belt_secondary_acceleration_lock"
    )
    DEADZONE_PRIMARY_CONTACT_ABSENT = "deadzone_primary_contact_absent"
    LOWER_STOP_POSITION = "lower_stop_position"
    LOWER_STOP_KINEMATIC_CONSTRAINT = "lower_stop_kinematic_constraint"
    LOWER_STOP_UNILATERAL_REACTION = "lower_stop_unilateral_reaction"
    UPPER_STOP_POSITION = "upper_stop_position"
    UPPER_STOP_KINEMATIC_CONSTRAINT = "upper_stop_kinematic_constraint"
    UPPER_STOP_UNILATERAL_REACTION = "upper_stop_unilateral_reaction"
    ENGAGED_NORMAL_FLOOR = "engaged_normal_floor"
    STICK_ACCELERATION_COMPATIBILITY = "stick_acceleration_compatibility"
    STICK_STATIC_ADMISSIBILITY = "stick_static_admissibility"
    KINETIC_DIRECTION_CONSISTENCY = "kinetic_direction_consistency"
    KINETIC_DISSIPATION = "kinetic_dissipation"
    TRANSITION_RESET_FINITE = "transition_reset_finite"
    STOP_IMPACT_PROJECTION = "stop_impact_projection"
    DISENGAGEMENT_CAPTURE_LOCK = "disengagement_capture_lock"


@dataclass(frozen=True, slots=True)
class CVTSystemCheckSettings:
    """Numerical slack used only when evaluating trajectory invariants.

    These are diagnostics tolerances, not contact-law or switch-policy
    parameters.  Defaults are deliberately tighter than practical mechanics but
    looser than floating-point endpoint noise.
    """

    maximum_samples_per_segment: int = 96
    shift_position_tolerance: float = 2.0e-8
    shift_speed_tolerance: float = 2.0e-8
    shift_acceleration_tolerance: float = 2.0e-7
    deadzone_speed_lock_tolerance: float = 2.0e-8
    deadzone_acceleration_lock_tolerance: float = 2.0e-8
    normal_resultant_tolerance: float = 2.0e-8
    static_margin_tolerance: float = 2.0e-7
    stick_acceleration_multiplier: float = 20.0
    kinetic_dissipation_tolerance: float = 2.0e-7
    stop_reaction_tolerance: float = 2.0e-7

    def __post_init__(self) -> None:
        if self.maximum_samples_per_segment < 2:
            raise ValueError("maximum_samples_per_segment must be at least two.")
        for name, value in (
            ("shift_position_tolerance", self.shift_position_tolerance),
            ("shift_speed_tolerance", self.shift_speed_tolerance),
            ("shift_acceleration_tolerance", self.shift_acceleration_tolerance),
            ("deadzone_speed_lock_tolerance", self.deadzone_speed_lock_tolerance),
            (
                "deadzone_acceleration_lock_tolerance",
                self.deadzone_acceleration_lock_tolerance,
            ),
            ("normal_resultant_tolerance", self.normal_resultant_tolerance),
            ("static_margin_tolerance", self.static_margin_tolerance),
            ("stick_acceleration_multiplier", self.stick_acceleration_multiplier),
            ("kinetic_dissipation_tolerance", self.kinetic_dissipation_tolerance),
            ("stop_reaction_tolerance", self.stop_reaction_tolerance),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and strictly positive.")


@dataclass(frozen=True, slots=True)
class CVTInvariantViolation:
    """One failed physical assertion at a named sample or transition."""

    invariant: CVTInvariant
    location: str
    observed: float | str
    expected: str

    def format(self) -> str:
        return (
            f"{self.invariant.value} at {self.location}: "
            f"observed={self.observed!r}; expected {self.expected}"
        )


@dataclass(frozen=True, slots=True)
class CVTSystemCheckReport:
    """Audit result from :func:`check_cvt_hybrid_result`."""

    samples_checked: int
    transitions_checked: int
    failures: tuple[CVTInvariantViolation, ...] = ()
    minimum_primary_normal: float | None = None
    minimum_secondary_normal: float | None = None
    minimum_static_margin: float | None = None
    minimum_slip_dissipation: float | None = None
    minimum_stop_reaction: float | None = None
    maximum_closure_condition_number: float | None = None

    @property
    def passed(self) -> bool:
        return not self.failures

    def raise_if_failed(self) -> None:
        if self.passed:
            return
        rendered = "\n".join(f"  - {failure.format()}" for failure in self.failures)
        raise AssertionError(
            f"CVT hybrid physical checks failed ({len(self.failures)} violation(s)):\n"
            f"{rendered}"
        )

    def summary_lines(self) -> tuple[str, ...]:
        status = "PASS" if self.passed else f"FAIL ({len(self.failures)} violations)"
        lines = [
            f"physical checks: {status}",
            f"samples checked: {self.samples_checked}",
            f"transitions checked: {self.transitions_checked}",
        ]
        if self.minimum_primary_normal is not None:
            lines.append(f"min N_p: {self.minimum_primary_normal:.6g} N")
        if self.minimum_secondary_normal is not None:
            lines.append(f"min N_s: {self.minimum_secondary_normal:.6g} N")
        if self.minimum_static_margin is not None:
            lines.append(f"min static lambda margin: {self.minimum_static_margin:.6g}")
        if self.minimum_slip_dissipation is not None:
            lines.append(
                f"min kinetic dissipation: {self.minimum_slip_dissipation:.6g} W"
            )
        if self.minimum_stop_reaction is not None:
            lines.append(
                f"min active stop reaction: {self.minimum_stop_reaction:.6g} N"
            )
        if self.maximum_closure_condition_number is not None:
            lines.append(
                "max closure condition number: "
                f"{self.maximum_closure_condition_number:.6g}"
            )
        return tuple(lines)


def check_cvt_hybrid_result(
    *,
    system: "CVTOperatingHybridSystem",
    result: HybridIntegrationResult[CVTOperatingRegime],
    settings: CVTSystemCheckSettings = CVTSystemCheckSettings(),
) -> CVTSystemCheckReport:
    """Sample a hybrid trajectory and audit the active regime's invariants.

    The function never changes simulator state.  It calls the same regime
    evaluator used by integration at accepted segment samples, then records
    all failures instead of stopping at the first one.  That makes a bad run
    diagnosable without requiring a separate unit test for every condition.
    """

    if not isinstance(result, HybridIntegrationResult):
        raise TypeError("result must be a HybridIntegrationResult instance.")
    if not isinstance(settings, CVTSystemCheckSettings):
        raise TypeError("settings must be a CVTSystemCheckSettings instance.")

    failures: list[CVTInvariantViolation] = []
    primary_normals: list[float] = []
    secondary_normals: list[float] = []
    static_margins: list[float] = []
    slip_dissipations: list[float] = []
    stop_reactions: list[float] = []
    closure_condition_numbers: list[float] = []
    samples_checked = 0

    for segment_index, segment in enumerate(result.segments):
        for sample_index in _sample_indices(
            segment.state.shape[1],
            maximum=settings.maximum_samples_per_segment,
        ):
            time = float(segment.time[sample_index])
            vector = np.asarray(segment.state[:, sample_index], dtype=float)
            location = (
                f"segment={segment_index}, sample={sample_index}, t={time:.9g}, "
                f"mode={_format_mode(segment.mode)}"
            )
            samples_checked += 1
            _check_finite_vector(
                vector,
                invariant=CVTInvariant.FINITE_STATE,
                location=location,
                failures=failures,
            )
            _check_shift_bounds(
                system=system,
                state=vector,
                location=location,
                settings=settings,
                failures=failures,
            )
            try:
                inspection = inspect_cvt_state(
                    system=system,
                    time=time,
                    vector=vector,
                    mode=segment.mode,
                    include_closure_audit=True,
                )
                evaluation = inspection.contact or inspection.deadzone
                if evaluation is None:  # pragma: no cover - inspection exhaustiveness guard.
                    raise RuntimeError("State inspection did not expose an active regime evaluation.")
            except Exception as error:  # pragma: no cover - diagnostic of a failed run.
                failures.append(
                    CVTInvariantViolation(
                        invariant=CVTInvariant.FINITE_DERIVATIVE,
                        location=location,
                        observed=type(error).__name__,
                        expected="active-regime evaluation to succeed at an accepted state",
                    )
                )
                continue

            derivative = evaluation.state_derivative.as_vector()
            _check_finite_vector(
                derivative,
                invariant=CVTInvariant.FINITE_DERIVATIVE,
                location=location,
                failures=failures,
            )

            if isinstance(evaluation, DeadzoneEvaluation):
                _check_deadzone_sample(
                    system=system,
                    mode=segment.mode,
                    evaluation=evaluation,
                    location=location,
                    settings=settings,
                    failures=failures,
                    stop_reactions=stop_reactions,
                )
            elif isinstance(evaluation, CVTContactEvaluation):
                _check_engaged_sample(
                    system=system,
                    mode=segment.mode,
                    evaluation=evaluation,
                    location=location,
                    settings=settings,
                    failures=failures,
                    primary_normals=primary_normals,
                    secondary_normals=secondary_normals,
                    static_margins=static_margins,
                    slip_dissipations=slip_dissipations,
                    stop_reactions=stop_reactions,
                    closure_condition_numbers=closure_condition_numbers,
                    closure_condition_number=(
                        None
                        if inspection.closure_audit is None
                        else inspection.closure_audit.condition_number
                    ),
                )
            else:  # pragma: no cover - TypeAlias exhaustiveness guard.
                failures.append(
                    CVTInvariantViolation(
                        invariant=CVTInvariant.FINITE_DERIVATIVE,
                        location=location,
                        observed=type(evaluation).__name__,
                        expected="known CVT regime evaluation type",
                    )
                )

    _check_transition_resets(
        system=system,
        result=result,
        settings=settings,
        failures=failures,
    )

    return CVTSystemCheckReport(
        samples_checked=samples_checked,
        transitions_checked=len(result.transitions),
        failures=tuple(failures),
        minimum_primary_normal=_minimum_or_none(primary_normals),
        minimum_secondary_normal=_minimum_or_none(secondary_normals),
        minimum_static_margin=_minimum_or_none(static_margins),
        minimum_slip_dissipation=_minimum_or_none(slip_dissipations),
        minimum_stop_reaction=_minimum_or_none(stop_reactions),
        maximum_closure_condition_number=(
            max(closure_condition_numbers) if closure_condition_numbers else None
        ),
    )


def _check_deadzone_sample(
    *,
    system: "CVTOperatingHybridSystem",
    mode: CVTOperatingRegime,
    evaluation: DeadzoneEvaluation,
    location: str,
    settings: CVTSystemCheckSettings,
    failures: list[CVTInvariantViolation],
    stop_reactions: list[float],
) -> None:
    limits = system.operating_limits
    state = evaluation.state
    derivative = evaluation.state_derivative

    _expect(
        mode.engagement is CVTEngagementState.DEADZONE,
        invariant=CVTInvariant.MODE_POSITION_DOMAIN,
        location=location,
        observed=mode.engagement.value,
        expected="deadzone evaluation only in deadzone regime",
        failures=failures,
    )
    _expect(
        state.shift_position
        <= limits.engagement_shift + settings.shift_position_tolerance,
        invariant=CVTInvariant.MODE_POSITION_DOMAIN,
        location=location,
        observed=state.shift_position,
        expected=f"s <= engagement_shift + {settings.shift_position_tolerance:g}",
        failures=failures,
    )
    _expect(
        abs(evaluation.belt_secondary_speed_residual)
        <= settings.deadzone_speed_lock_tolerance,
        invariant=CVTInvariant.DEADZONE_BELT_SECONDARY_SPEED_LOCK,
        location=location,
        observed=evaluation.belt_secondary_speed_residual,
        expected=f"abs(v_b - r_s*omega_s) <= {settings.deadzone_speed_lock_tolerance:g}",
        failures=failures,
    )
    _expect(
        abs(evaluation.belt_secondary_acceleration_residual)
        <= settings.deadzone_acceleration_lock_tolerance,
        invariant=CVTInvariant.DEADZONE_BELT_SECONDARY_ACCELERATION_LOCK,
        location=location,
        observed=evaluation.belt_secondary_acceleration_residual,
        expected=(
            "abs(v_b_dot - r_s*alpha_s) <= "
            f"{settings.deadzone_acceleration_lock_tolerance:g}"
        ),
        failures=failures,
    )
    _expect(
        abs(evaluation.primary_normal_resultant) <= settings.normal_resultant_tolerance
        and abs(evaluation.primary_transmitted_torque)
        <= settings.normal_resultant_tolerance,
        invariant=CVTInvariant.DEADZONE_PRIMARY_CONTACT_ABSENT,
        location=location,
        observed=(
            f"N_p={evaluation.primary_normal_resultant:.6g}, "
            f"tau_p={evaluation.primary_transmitted_torque:.6g}"
        ),
        expected="N_p = 0 and tau_p = 0 under primary-disengaged deadzone model",
        failures=failures,
    )

    if mode.shift_constraint is CVTShiftConstraint.FREE:
        _expect(
            state.shift_position
            >= limits.lower_stop_shift - settings.shift_position_tolerance,
            invariant=CVTInvariant.MODE_POSITION_DOMAIN,
            location=location,
            observed=state.shift_position,
            expected=f"s >= lower_stop_shift - {settings.shift_position_tolerance:g}",
            failures=failures,
        )
        return

    _expect(
        mode.shift_constraint is CVTShiftConstraint.LOWER_STOP,
        invariant=CVTInvariant.MODE_POSITION_DOMAIN,
        location=location,
        observed=mode.shift_constraint.value,
        expected="deadzone/free or deadzone/lower_stop",
        failures=failures,
    )
    _expect(
        abs(state.shift_position - limits.lower_stop_shift)
        <= settings.shift_position_tolerance,
        invariant=CVTInvariant.LOWER_STOP_POSITION,
        location=location,
        observed=state.shift_position,
        expected=f"s = lower_stop_shift within {settings.shift_position_tolerance:g}",
        failures=failures,
    )
    _expect(
        abs(state.shift_speed) <= settings.shift_speed_tolerance
        and abs(derivative.shift_position_rate) <= settings.shift_speed_tolerance
        and abs(derivative.shift_acceleration) <= settings.shift_acceleration_tolerance,
        invariant=CVTInvariant.LOWER_STOP_KINEMATIC_CONSTRAINT,
        location=location,
        observed=(
            f"s_dot={state.shift_speed:.6g}, ds_dt={derivative.shift_position_rate:.6g}, "
            f"s_ddot={derivative.shift_acceleration:.6g}"
        ),
        expected="s_dot = ds_dt = s_ddot = 0 while lower-stop constrained",
        failures=failures,
    )
    reaction = evaluation.stop_reaction
    if reaction is None:
        failures.append(
            CVTInvariantViolation(
                invariant=CVTInvariant.LOWER_STOP_UNILATERAL_REACTION,
                location=location,
                observed="None",
                expected="finite lower-stop reaction",
            )
        )
    else:
        stop_reactions.append(reaction)
        _expect(
            reaction >= -settings.stop_reaction_tolerance,
            invariant=CVTInvariant.LOWER_STOP_UNILATERAL_REACTION,
            location=location,
            observed=reaction,
            expected=f"R_low >= -{settings.stop_reaction_tolerance:g}",
            failures=failures,
        )


def _check_engaged_sample(
    *,
    system: "CVTOperatingHybridSystem",
    mode: CVTOperatingRegime,
    evaluation: CVTContactEvaluation,
    location: str,
    settings: CVTSystemCheckSettings,
    failures: list[CVTInvariantViolation],
    primary_normals: list[float],
    secondary_normals: list[float],
    static_margins: list[float],
    slip_dissipations: list[float],
    stop_reactions: list[float],
    closure_condition_numbers: list[float],
    closure_condition_number: float | None,
) -> None:
    limits = system.operating_limits
    state = evaluation.state
    derivative = evaluation.state_derivative
    contact = evaluation.regime

    _expect(
        mode.engagement is CVTEngagementState.ENGAGED,
        invariant=CVTInvariant.MODE_POSITION_DOMAIN,
        location=location,
        observed=mode.engagement.value,
        expected="engaged evaluation only in engaged regime",
        failures=failures,
    )
    _expect(
        state.shift_position
        >= limits.engagement_shift - settings.shift_position_tolerance,
        invariant=CVTInvariant.MODE_POSITION_DOMAIN,
        location=location,
        observed=state.shift_position,
        expected=f"s >= engagement_shift - {settings.shift_position_tolerance:g}",
        failures=failures,
    )
    primary_normals.append(evaluation.normal_primary)
    secondary_normals.append(evaluation.normal_secondary)
    if closure_condition_number is not None:
        closure_condition_numbers.append(closure_condition_number)
    normal_floor = system.switching_settings.normal_resultant_floor
    _expect(
        evaluation.normal_primary >= normal_floor - settings.normal_resultant_tolerance
        and evaluation.normal_secondary
        >= normal_floor - settings.normal_resultant_tolerance,
        invariant=CVTInvariant.ENGAGED_NORMAL_FLOOR,
        location=location,
        observed=(
            f"N_p={evaluation.normal_primary:.6g}, N_s={evaluation.normal_secondary:.6g}"
        ),
        expected=f"both normals >= {normal_floor:g} (within check tolerance)",
        failures=failures,
    )

    if mode.shift_constraint is CVTShiftConstraint.FREE:
        _expect(
            state.shift_position
            <= limits.upper_stop_shift + settings.shift_position_tolerance,
            invariant=CVTInvariant.MODE_POSITION_DOMAIN,
            location=location,
            observed=state.shift_position,
            expected=f"s <= upper_stop_shift + {settings.shift_position_tolerance:g}",
            failures=failures,
        )
    else:
        _expect(
            mode.shift_constraint is CVTShiftConstraint.UPPER_STOP,
            invariant=CVTInvariant.MODE_POSITION_DOMAIN,
            location=location,
            observed=mode.shift_constraint.value,
            expected="engaged/free or engaged/upper_stop",
            failures=failures,
        )
        _expect(
            abs(state.shift_position - limits.upper_stop_shift)
            <= settings.shift_position_tolerance,
            invariant=CVTInvariant.UPPER_STOP_POSITION,
            location=location,
            observed=state.shift_position,
            expected=f"s = upper_stop_shift within {settings.shift_position_tolerance:g}",
            failures=failures,
        )
        _expect(
            abs(state.shift_speed) <= settings.shift_speed_tolerance
            and abs(derivative.shift_position_rate) <= settings.shift_speed_tolerance
            and abs(derivative.shift_acceleration)
            <= settings.shift_acceleration_tolerance,
            invariant=CVTInvariant.UPPER_STOP_KINEMATIC_CONSTRAINT,
            location=location,
            observed=(
                f"s_dot={state.shift_speed:.6g}, ds_dt={derivative.shift_position_rate:.6g}, "
                f"s_ddot={derivative.shift_acceleration:.6g}"
            ),
            expected="s_dot = ds_dt = s_ddot = 0 while upper-stop constrained",
            failures=failures,
        )
        reaction = evaluation.upper_stop_reaction
        if reaction is None:
            failures.append(
                CVTInvariantViolation(
                    invariant=CVTInvariant.UPPER_STOP_UNILATERAL_REACTION,
                    location=location,
                    observed="None",
                    expected="finite upper-stop reaction",
                )
            )
        else:
            stop_reactions.append(reaction)
            _expect(
                reaction >= -settings.stop_reaction_tolerance,
                invariant=CVTInvariant.UPPER_STOP_UNILATERAL_REACTION,
                location=location,
                observed=reaction,
                expected=f"R_high >= -{settings.stop_reaction_tolerance:g}",
                failures=failures,
            )

    stick_tolerance = (
        settings.stick_acceleration_multiplier
        * system.solve_settings.contact_tolerances.stick_acceleration_tolerance
    )
    for interface in contact.mode.sticking_interfaces:
        acceleration_residual = evaluation.relative_motion.relative_acceleration_at(
            interface
        )
        _expect(
            abs(acceleration_residual) <= stick_tolerance,
            invariant=CVTInvariant.STICK_ACCELERATION_COMPATIBILITY,
            location=location,
            observed=acceleration_residual,
            expected=f"abs(a_rel,{interface.value}) <= {stick_tolerance:g}",
            failures=failures,
        )
        margin = evaluation.static_margin_at(
            interface, traction_law=system.traction_law
        )
        static_margins.append(margin)
        _expect(
            margin >= -settings.static_margin_tolerance,
            invariant=CVTInvariant.STICK_STATIC_ADMISSIBILITY,
            location=location,
            observed=margin,
            expected=f"static lambda margin >= -{settings.static_margin_tolerance:g}",
            failures=failures,
        )

    direction_consistent = _slip_directions_are_consistent_or_at_zero(
        system=system,
        evaluation=evaluation,
    )
    _expect(
        direction_consistent,
        invariant=CVTInvariant.KINETIC_DIRECTION_CONSISTENCY,
        location=location,
        observed=(
            "inconsistent" if contact.mode.slipping_interfaces else "not_applicable"
        ),
        expected=(
            "all imposed kinetic slip directions consistent with established relative motion, "
            "or an exact re-stick zero-speed endpoint"
        ),
        failures=failures,
    )
    for interface in contact.mode.slipping_interfaces:
        dissipation = _kinetic_dissipation(evaluation=evaluation, interface=interface)
        slip_dissipations.append(dissipation)
        _expect(
            dissipation >= -settings.kinetic_dissipation_tolerance,
            invariant=CVTInvariant.KINETIC_DISSIPATION,
            location=location,
            observed=dissipation,
            expected=f"P_diss,{interface.value} >= -{settings.kinetic_dissipation_tolerance:g}",
            failures=failures,
        )


def _check_transition_resets(
    *,
    system: "CVTOperatingHybridSystem",
    result: HybridIntegrationResult[CVTOperatingRegime],
    settings: CVTSystemCheckSettings,
    failures: list[CVTInvariantViolation],
) -> None:
    for transition_index, record in enumerate(result.transitions):
        vector = np.asarray(record.post_transition_state, dtype=float)
        location = (
            f"transition={transition_index}, t={record.time:.9g}, "
            f"reason={record.transition.reason}"
        )
        _check_finite_vector(
            vector,
            invariant=CVTInvariant.TRANSITION_RESET_FINITE,
            location=location,
            failures=failures,
        )
        reason = record.transition.reason
        if "upper_stop" in reason:
            _expect(
                abs(vector[3] - system.operating_limits.upper_stop_shift)
                <= settings.shift_position_tolerance
                and abs(vector[4]) <= settings.shift_speed_tolerance,
                invariant=CVTInvariant.STOP_IMPACT_PROJECTION,
                location=location,
                observed=f"s={vector[3]:.6g}, s_dot={vector[4]:.6g}",
                expected="upper-stop transition projects s=s_upper and s_dot=0",
                failures=failures,
            )
        if "lower_stop" in reason:
            _expect(
                abs(vector[3] - system.operating_limits.lower_stop_shift)
                <= settings.shift_position_tolerance
                and abs(vector[4]) <= settings.shift_speed_tolerance,
                invariant=CVTInvariant.STOP_IMPACT_PROJECTION,
                location=location,
                observed=f"s={vector[3]:.6g}, s_dot={vector[4]:.6g}",
                expected="lower-stop transition projects s=s_lower and s_dot=0",
                failures=failures,
            )
        if "disengagement" in reason:
            state = CVTDynamicState.from_vector(vector)
            try:
                snapshot = system.deadzone_evaluator.snapshot(state=state)
                residual = snapshot.belt_secondary_speed_residual
            except (
                Exception
            ) as error:  # pragma: no cover - captures regression diagnostics.
                failures.append(
                    CVTInvariantViolation(
                        invariant=CVTInvariant.DISENGAGEMENT_CAPTURE_LOCK,
                        location=location,
                        observed=type(error).__name__,
                        expected="post-disengagement state to satisfy deadzone belt-secondary lock",
                    )
                )
            else:
                _expect(
                    abs(residual) <= settings.deadzone_speed_lock_tolerance,
                    invariant=CVTInvariant.DISENGAGEMENT_CAPTURE_LOCK,
                    location=location,
                    observed=residual,
                    expected=(
                        "abs(v_b - r_s*omega_s) <= "
                        f"{settings.deadzone_speed_lock_tolerance:g} after capture"
                    ),
                    failures=failures,
                )


def _slip_directions_are_consistent_or_at_zero(
    *,
    system: "CVTOperatingHybridSystem",
    evaluation: CVTContactEvaluation,
) -> bool:
    """Accept an exact terminal ``v_rel = 0`` re-stick endpoint.

    A segment retains its pre-event kinetic mode through the zero-speed event
    sample produced by ``solve_ivp``.  At that point the old stored direction
    can be indeterminate or about to reverse, so it is not a meaningful
    direction-consistency failure.  The transition resolver owns the successor
    choice immediately afterward.
    """

    tolerances = system.solve_settings.contact_tolerances
    for interface in evaluation.regime.mode.slipping_interfaces:
        relative_speed = evaluation.relative_motion.relative_speed_at(interface)
        if abs(relative_speed) <= tolerances.relative_speed_tolerance:
            continue
        inferred = evaluation.relative_motion.slip_direction_at(
            interface,
            tolerances=tolerances,
        )
        if inferred is not evaluation.regime.slip_direction_at(interface):
            return False
    return True


def _kinetic_dissipation(
    *,
    evaluation: CVTContactEvaluation,
    interface: ContactInterface,
) -> float:
    """Return belt--pulley friction power converted to heat at one slipped contact."""

    unknowns = evaluation.closure_unknowns
    relative_speed = evaluation.relative_motion.relative_speed_at(interface)
    if interface is ContactInterface.PRIMARY:
        belt_force = (
            unknowns.primary_torque / evaluation.snapshot.geometry.primary.effective
        )
    elif interface is ContactInterface.SECONDARY:
        belt_force = (
            -unknowns.secondary_torque
            / evaluation.snapshot.geometry.secondary.effective
        )
    else:  # pragma: no cover - enum exhaustiveness guard.
        raise ValueError(f"Unsupported contact interface: {interface!r}.")
    return -belt_force * relative_speed


def _check_shift_bounds(
    *,
    system: "CVTOperatingHybridSystem",
    state: NDArray[np.float64],
    location: str,
    settings: CVTSystemCheckSettings,
    failures: list[CVTInvariantViolation],
) -> None:
    lower = system.operating_limits.lower_stop_shift
    upper = system.operating_limits.upper_stop_shift
    shift = float(state[3])
    _expect(
        lower - settings.shift_position_tolerance
        <= shift
        <= upper + settings.shift_position_tolerance,
        invariant=CVTInvariant.SHIFT_WITHIN_OPERATING_LIMITS,
        location=location,
        observed=shift,
        expected=(
            f"{lower - settings.shift_position_tolerance:g} <= s <= "
            f"{upper + settings.shift_position_tolerance:g}"
        ),
        failures=failures,
    )


def _sample_indices(count: int, *, maximum: int) -> NDArray[np.int64]:
    if count < 1:
        raise ValueError("segment sample count must be positive.")
    if count <= maximum:
        return np.arange(count, dtype=np.int64)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=np.int64))


def _check_finite_vector(
    vector: NDArray[np.float64],
    *,
    invariant: CVTInvariant,
    location: str,
    failures: list[CVTInvariantViolation],
) -> None:
    if not np.all(np.isfinite(vector)):
        failures.append(
            CVTInvariantViolation(
                invariant=invariant,
                location=location,
                observed="non-finite vector",
                expected="all components finite",
            )
        )


def _expect(
    condition: bool,
    *,
    invariant: CVTInvariant,
    location: str,
    observed: float | str,
    expected: str,
    failures: list[CVTInvariantViolation],
) -> None:
    if condition:
        return
    failures.append(
        CVTInvariantViolation(
            invariant=invariant,
            location=location,
            observed=observed,
            expected=expected,
        )
    )


def _minimum_or_none(values: Iterable[float]) -> float | None:
    materialized = tuple(values)
    return min(materialized) if materialized else None


def _format_mode(mode: CVTOperatingRegime) -> str:
    contact = "none" if mode.contact_regime is None else mode.contact_regime.mode.value
    return f"{mode.engagement.value}/{mode.shift_constraint.value}/{contact}"
