"""Shared tuning helpers for CINDER's mechanically actuated launch model.

The two command-line tools in this directory intentionally separate *screening*
from expensive hybrid integration:

* :mod:`screen_launch_tuning` evaluates lower-stop release and a small family
  of state-frozen *selected-contact* closures.  It is fast enough to eliminate
  obviously wrong combinations before any ODE run while still allowing the
  primary-slip launch branch selected by the real contact policy.
* :mod:`preflight_launch_sweep` runs a deliberately small number of promising
  candidates through the complete hybrid dispatcher over a longer window.
* :mod:`run_tuned_launch` produces the full diagnostic figures and physical
  audit for one chosen candidate.

The engagement target is a lower-stop unilateral-reaction target.  The
``shift_onset`` target is the first zero of free engaged ``s_ddot`` evaluated
at a small, fixed distance above the engagement boundary with kinematically
consistent low-ratio shaft speeds.  It remains a *screening proxy*; the full
launch metrics use the actual low-ratio-seat release event as the main-shift
onset.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from pathlib import Path
import sys
from typing import Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

_TOOLS_DIRECTORY = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _TOOLS_DIRECTORY.parent
# Keep this launchTools directory first: its baseline/tuning helpers are an
# intentional overlay and must not be shadowed by an older root-level copy.
if str(_TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIRECTORY))
for _candidate in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    _REPOSITORY_ROOT / "tools",
):
    if str(_candidate) not in sys.path:
        sys.path.append(str(_candidate))

from baja_trial_baseline import (  # noqa: E402
    BajaTrialBaseline,
    BajaTrialConstants,
    RPM_TO_RAD_PER_SECOND,
    build_baja_trial_baseline,
)
from cinder.model.system import CVTSimulationCase  # noqa: E402
from cinder.results import ReportingSettings  # noqa: E402
from cinder.model.boundaries.output import LockedFinalDriveVehicle  # noqa: E402
from cinder.model.cvt.contact import ContactRegime, ContactTractionLaw  # noqa: E402
from cinder.model.cvt.dynamics import (
    EngagedContactSolveSettings,
    LambdaSearchBounds,
)  # noqa: E402
from cinder.model.cvt.dynamics.deadzone import DeadzoneEvaluation  # noqa: E402
from cinder.execution.hybrid import CVTDynamicState, HybridIntegratorSettings  # noqa: E402
from cinder.execution.hybrid.cvt_contact import CVTContactEvaluation  # noqa: E402
from cinder.execution.hybrid.cvt_operating_hybrid import (
    CVTOperatingHybridSystem,
    CVTOperatingSystemConfig,
)  # noqa: E402
from cinder.execution.hybrid.cvt_operating_limits import (
    CVTShiftOperatingLimits,
)  # noqa: E402
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTOperatingRegime,
)  # noqa: E402
from cinder.model.cvt.profiles import CircularSegment, LinearSegment, PiecewiseRamp  # noqa: E402

RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3


@dataclass(frozen=True, slots=True)
class TuneCandidate:
    """One launch-tuning candidate including the primary ramp geometry.

    The primary preload is resolved from the requested engagement target, not
    independently swept.  A circular hard-to-soft ramp raises the centrifugal
    generalized force near low ratio, where the primary needs traction reserve,
    and then reduces the radial slope over travel so that this extra clamp does
    not remain imposed throughout the full shift.
    """

    flyweight_mass_kg: float
    helix_angle_degrees: float
    secondary_torsional_pretension_degrees: float
    secondary_compression_preload_mm: float
    primary_ramp_kind: str = "linear"
    primary_ramp_angle_degrees: float = 30.0
    primary_ramp_start_angle_degrees: float = 42.0
    primary_ramp_end_angle_degrees: float = 12.0

    def label(self) -> str:
        if self.primary_ramp_kind == "linear":
            ramp = f"ramp=L{self.primary_ramp_angle_degrees:.0f}"
        else:
            ramp = (
                f"ramp=C{self.primary_ramp_start_angle_degrees:.0f}"
                f"→{self.primary_ramp_end_angle_degrees:.0f}"
            )
        return (
            f"m={self.flyweight_mass_kg:.3f} kg, "
            f"h={self.helix_angle_degrees:.1f} deg, "
            f"twist={self.secondary_torsional_pretension_degrees:.0f} deg, "
            f"sec={self.secondary_compression_preload_mm:.1f} mm, {ramp}"
        )


@dataclass(frozen=True, slots=True)
class ResolvedTune:
    """Candidate plus primary preload resolved to a lower-stop release target."""

    candidate: TuneCandidate
    constants: BajaTrialConstants
    target_engagement_rpm: float
    resolved_primary_preload_mm: float
    lower_stop_reaction_at_target_n: float


@dataclass(frozen=True, slots=True)
class StaticShiftPoint:
    """One state-frozen, near-low-ratio free-engagement evaluation."""

    primary_rpm: float
    shift_acceleration_m_per_s2: float | None
    accepted: bool
    stick_admissible: bool
    contact_mode: str | None
    primary_lambda: float | None
    secondary_lambda: float | None
    primary_normal_n: float | None
    secondary_normal_n: float | None
    minimum_static_margin: float | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ScreenResult:
    """Rankable outcome of the low-cost engagement and shift-onset screen."""

    resolved: ResolvedTune
    points: tuple[StaticShiftPoint, ...]
    estimated_shift_onset_rpm: float | None
    acceleration_at_target_plus_200: float | None
    minimum_static_margin_near_target: float | None
    stick_admissible_points: int
    static_valid: bool
    score: float
    rejection_reason: str | None = None

    def csv_row(
        self, *, rank: int | None = None
    ) -> dict[str, float | int | str | None]:
        c = self.resolved.candidate
        return {
            "rank": rank,
            "flyweight_mass_kg": c.flyweight_mass_kg,
            "helix_angle_degrees": c.helix_angle_degrees,
            "secondary_torsional_pretension_degrees": (
                c.secondary_torsional_pretension_degrees
            ),
            "secondary_compression_preload_mm": c.secondary_compression_preload_mm,
            "primary_ramp_kind": c.primary_ramp_kind,
            "primary_ramp_angle_degrees": c.primary_ramp_angle_degrees,
            "primary_ramp_start_angle_degrees": c.primary_ramp_start_angle_degrees,
            "primary_ramp_end_angle_degrees": c.primary_ramp_end_angle_degrees,
            "resolved_primary_preload_mm": self.resolved.resolved_primary_preload_mm,
            "target_engagement_rpm": self.resolved.target_engagement_rpm,
            "lower_stop_reaction_at_target_n": (
                self.resolved.lower_stop_reaction_at_target_n
            ),
            "estimated_shift_onset_rpm": self.estimated_shift_onset_rpm,
            "acceleration_at_target_plus_200_m_per_s2": (
                self.acceleration_at_target_plus_200
            ),
            "minimum_static_margin_near_target": (
                self.minimum_static_margin_near_target
            ),
            "stick_admissible_points": self.stick_admissible_points,
            "selected_contact_modes": " | ".join(
                sorted(
                    {point.contact_mode for point in self.points if point.contact_mode}
                )
            ),
            "static_valid": int(self.static_valid),
            "score": self.score,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True, slots=True)
class LaunchTrace:
    """Sparse re-evaluation of accepted hybrid trajectory samples."""

    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode_label: tuple[str, ...]
    primary_surface_speed: NDArray[np.float64]
    secondary_surface_speed: NDArray[np.float64]
    primary_torque: NDArray[np.float64]
    secondary_torque: NDArray[np.float64]
    primary_lambda: NDArray[np.float64]
    secondary_lambda: NDArray[np.float64]
    primary_normal: NDArray[np.float64]
    secondary_normal: NDArray[np.float64]
    primary_relative_speed: NDArray[np.float64]
    secondary_relative_speed: NDArray[np.float64]
    stop_reaction: NDArray[np.float64]


def _validate_candidate(candidate: TuneCandidate) -> None:
    for name, value in asdict(candidate).items():
        if name == "primary_ramp_kind":
            continue
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
    if candidate.flyweight_mass_kg <= 0.0:
        raise ValueError("flyweight_mass_kg must be strictly positive.")
    if not 1.0 < candidate.helix_angle_degrees < 89.0:
        raise ValueError("helix_angle_degrees must lie strictly between 1 and 89.")
    if candidate.secondary_torsional_pretension_degrees < 0.0:
        raise ValueError("secondary torsional pretension must be non-negative.")
    if candidate.secondary_compression_preload_mm < 0.0:
        raise ValueError("secondary compression preload must be non-negative.")
    if candidate.primary_ramp_kind not in {"linear", "circular_hard_to_soft"}:
        raise ValueError(
            "primary_ramp_kind must be 'linear' or 'circular_hard_to_soft'."
        )
    if not 0.0 < candidate.primary_ramp_angle_degrees < 89.0:
        raise ValueError(
            "primary linear ramp angle must lie strictly between 0 and 89 degrees."
        )
    if not 0.0 < candidate.primary_ramp_start_angle_degrees < 89.0:
        raise ValueError(
            "primary circular start angle must lie strictly between 0 and 89 degrees."
        )
    if not 0.0 < candidate.primary_ramp_end_angle_degrees < 89.0:
        raise ValueError(
            "primary circular end angle must lie strictly between 0 and 89 degrees."
        )
    if candidate.primary_ramp_kind == "circular_hard_to_soft" and (
        candidate.primary_ramp_start_angle_degrees
        < candidate.primary_ramp_end_angle_degrees
    ):
        raise ValueError(
            "hard-to-soft circular ramp requires start angle >= end angle."
        )


def candidate_constants(
    candidate: TuneCandidate,
    *,
    primary_preload_m: float | None = None,
) -> BajaTrialConstants:
    """Map one tune candidate onto the diagnostic Baja baseline constants."""

    _validate_candidate(candidate)
    updates: dict[str, float] = {
        "flyweight_mass": candidate.flyweight_mass_kg,
        "helix_angle_degrees": candidate.helix_angle_degrees,
        "secondary_torsional_initial_twist": np.deg2rad(
            candidate.secondary_torsional_pretension_degrees
        ),
        "secondary_spring_initial_compression": (
            candidate.secondary_compression_preload_mm * MILLIMETRE
        ),
        "primary_ramp_kind": candidate.primary_ramp_kind,
        "primary_ramp_angle_degrees": candidate.primary_ramp_angle_degrees,
        "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
        "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
    }
    if primary_preload_m is not None:
        if not isfinite(primary_preload_m) or primary_preload_m < 0.0:
            raise ValueError("primary_preload_m must be finite and non-negative.")
        updates["primary_spring_initial_compression"] = primary_preload_m
    return replace(BajaTrialConstants(), **updates)


def build_operating_configuration(
    constants: BajaTrialConstants,
    *,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
) -> tuple[CVTOperatingSystemConfig, BajaTrialBaseline]:
    """Build case-independent hybrid settings plus the immutable Baja case."""

    baseline = build_baja_trial_baseline(constants)
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=static_lambda_limit,
        secondary_static_lambda_limit=static_lambda_limit,
        primary_kinetic_lambda_magnitude=kinetic_lambda_magnitude,
        secondary_kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    configuration = CVTOperatingSystemConfig(
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=3.0,
                secondary_half_width=3.0,
            ),
            initial_guess=baseline.default_trial,
            maximum_closure_condition_number=1.0e8,
        ),
        operating_limits=CVTShiftOperatingLimits(
            lower_stop_shift=0.0,
            engagement_shift=constants.deadzone_shift,
            upper_stop_shift=constants.max_shift,
        ),
    )
    return configuration, baseline


def build_operating_system(
    constants: BajaTrialConstants,
    *,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
) -> tuple[CVTOperatingHybridSystem, BajaTrialBaseline]:
    """Build the normal hybrid system from the baseline simulation case."""

    configuration, baseline = build_operating_configuration(
        constants,
        static_lambda_limit=static_lambda_limit,
        kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    return configuration.build(baseline.case), baseline

def launch_initial_state(*, primary_rpm: float = 1800.0) -> CVTDynamicState:
    """Return the requested rest-launch state: primary spinning, driven side at rest."""

    if not isfinite(primary_rpm) or primary_rpm < 0.0:
        raise ValueError("primary_rpm must be finite and non-negative.")
    return CVTDynamicState(
        primary_angular_speed=primary_rpm * RPM_TO_RAD_PER_SECOND,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
        secondary_shaft_angle=0.0,
    )


def lower_stop_reaction(
    system: CVTOperatingHybridSystem,
    *,
    primary_rpm: float,
) -> float:
    """Recover the unilateral lower-stop reaction at a zero-vehicle-speed launch."""

    evaluation = system.deadzone_evaluator.evaluate_lower_stop(
        state=launch_initial_state(primary_rpm=primary_rpm),
        lower_stop_shift=system.operating_limits.lower_stop_shift,
    )
    reaction = evaluation.stop_reaction
    if reaction is None:  # pragma: no cover - lower-stop evaluator invariant.
        raise RuntimeError("Lower-stop evaluation did not recover a reaction.")
    return float(reaction)


def resolve_primary_preload(
    candidate: TuneCandidate,
    *,
    target_engagement_rpm: float,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
) -> ResolvedTune:
    """Resolve primary preload from the lower-stop reaction at the target speed.

    At a fixed lower-stop coordinate, changing the primary spring's installed
    compression adds exactly ``k_p Δx`` to the closing stop reaction.  One
    baseline lower-stop evaluation is therefore enough to solve the preload;
    no nonlinear search and no time integration are needed.
    """

    if not isfinite(target_engagement_rpm) or target_engagement_rpm <= 0.0:
        raise ValueError("target_engagement_rpm must be finite and strictly positive.")
    provisional_constants = candidate_constants(candidate)
    provisional_system, _ = build_operating_system(
        provisional_constants,
        static_lambda_limit=static_lambda_limit,
        kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    reaction = lower_stop_reaction(
        provisional_system,
        primary_rpm=target_engagement_rpm,
    )
    spring_rate = provisional_constants.primary_spring_rate
    preload = (
        provisional_constants.primary_spring_initial_compression
        - reaction / spring_rate
    )
    if preload < -1.0e-12:
        raise ValueError(
            "The requested engagement target requires negative primary preload for "
            f"{candidate.label()}. Increase flyweight mass or engagement target."
        )
    preload = max(0.0, preload)
    resolved_constants = candidate_constants(candidate, primary_preload_m=preload)
    resolved_system, _ = build_operating_system(
        resolved_constants,
        static_lambda_limit=static_lambda_limit,
        kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    resolved_reaction = lower_stop_reaction(
        resolved_system,
        primary_rpm=target_engagement_rpm,
    )
    return ResolvedTune(
        candidate=candidate,
        constants=resolved_constants,
        target_engagement_rpm=target_engagement_rpm,
        resolved_primary_preload_mm=preload / MILLIMETRE,
        lower_stop_reaction_at_target_n=resolved_reaction,
    )


def make_near_low_ratio_stick_state(
    *,
    system: CVTOperatingHybridSystem,
    primary_rpm: float,
    probe_fraction: float,
) -> CVTDynamicState:
    """Build a synchronous state just above engagement for the onset screen."""

    if not 0.0 < probe_fraction < 1.0:
        raise ValueError("probe_fraction must lie strictly between zero and one.")
    lower = system.operating_limits.engagement_shift
    upper = system.operating_limits.upper_stop_shift
    shift = lower + probe_fraction * (upper - lower)
    geometry = system.model.geometry.evaluate(shift)
    primary_speed = primary_rpm * RPM_TO_RAD_PER_SECOND
    belt_speed = primary_speed * geometry.primary.effective
    secondary_speed = belt_speed / geometry.secondary.effective
    return CVTDynamicState(
        primary_angular_speed=primary_speed,
        secondary_angular_speed=secondary_speed,
        belt_speed=belt_speed,
        shift_position=shift,
        shift_speed=0.0,
        secondary_shaft_angle=0.0,
    )


def evaluate_static_shift_point(
    *,
    system: CVTOperatingHybridSystem,
    primary_rpm: float,
    probe_fraction: float,
) -> StaticShiftPoint:
    """Evaluate the contact branch selected by the actual launch policy.

    The earlier screen forced a stick--stick closure and consequently rejected
    useful launch candidates whose primary contact is correctly kinetic-slip
    limited immediately after engagement.  Here the exact same initial branch
    classifier used by the hybrid dispatcher chooses stick, mixed slip, or
    both-slip at the frozen state before the free-shift acceleration is read.
    """

    try:
        state = make_near_low_ratio_stick_state(
            system=system,
            primary_rpm=primary_rpm,
            probe_fraction=probe_fraction,
        )
        regime = system.evaluator.classify_initial_regime(
            state=state,
            switching_settings=system.switching_settings,
        )
        evaluation = system.evaluator.evaluate_vector(
            time=0.0,
            vector=state.as_vector(),
            regime=regime,
        )
        margins = tuple(
            evaluation.static_margin_at(interface, traction_law=system.traction_law)
            for interface in evaluation.regime.mode.sticking_interfaces
        )
        minimum_margin = float(min(margins)) if margins else None
        numerical_acceptance = bool(
            getattr(evaluation.branch_result, "accepted", True)
            and evaluation.normal_primary > 0.0
            and evaluation.normal_secondary > 0.0
            and evaluation.slipped_directions_are_consistent()
        )
        stick_admissible = bool(
            evaluation.sticks_are_admissible(
                traction_law=system.traction_law,
                required_margin=0.0,
            )
            and evaluation.normal_primary > 0.0
            and evaluation.normal_secondary > 0.0
        )
        return StaticShiftPoint(
            primary_rpm=primary_rpm,
            shift_acceleration_m_per_s2=float(
                evaluation.state_derivative.shift_acceleration
            ),
            accepted=numerical_acceptance,
            stick_admissible=stick_admissible,
            contact_mode=regime.mode.value,
            primary_lambda=float(evaluation.traction_utilization.primary_lambda),
            secondary_lambda=float(evaluation.traction_utilization.secondary_lambda),
            primary_normal_n=float(evaluation.normal_primary),
            secondary_normal_n=float(evaluation.normal_secondary),
            minimum_static_margin=minimum_margin,
        )
    except Exception as error:  # A screened candidate should not abort its sweep.
        return StaticShiftPoint(
            primary_rpm=primary_rpm,
            shift_acceleration_m_per_s2=None,
            accepted=False,
            stick_admissible=False,
            contact_mode=None,
            primary_lambda=None,
            secondary_lambda=None,
            primary_normal_n=None,
            secondary_normal_n=None,
            minimum_static_margin=None,
            error=f"{type(error).__name__}: {error}",
        )


def _interpolate_zero(points: Sequence[StaticShiftPoint]) -> float | None:
    """Return the first valid free-shift acceleration zero crossing."""

    for left, right in zip(points, points[1:], strict=False):
        if not left.accepted or not right.accepted:
            continue
        left_acceleration = left.shift_acceleration_m_per_s2
        right_acceleration = right.shift_acceleration_m_per_s2
        if left_acceleration is None or right_acceleration is None:
            continue
        if left_acceleration == 0.0:
            return left.primary_rpm
        if left_acceleration <= 0.0 <= right_acceleration:
            delta = right_acceleration - left_acceleration
            if delta == 0.0:
                return right.primary_rpm
            fraction = -left_acceleration / delta
            return left.primary_rpm + fraction * (right.primary_rpm - left.primary_rpm)
    return None


def _interpolate_acceleration(
    points: Sequence[StaticShiftPoint],
    *,
    primary_rpm: float,
) -> float | None:
    """Linearly interpolate valid static acceleration samples."""

    for left, right in zip(points, points[1:], strict=False):
        if not left.accepted or not right.accepted:
            continue
        if not left.primary_rpm <= primary_rpm <= right.primary_rpm:
            continue
        left_acceleration = left.shift_acceleration_m_per_s2
        right_acceleration = right.shift_acceleration_m_per_s2
        if left_acceleration is None or right_acceleration is None:
            continue
        fraction = (primary_rpm - left.primary_rpm) / (
            right.primary_rpm - left.primary_rpm
        )
        return left_acceleration + fraction * (right_acceleration - left_acceleration)
    return None


def screen_tune(
    candidate: TuneCandidate,
    *,
    target_engagement_rpm: float = 2000.0,
    target_shift_onset_rpm: float = 3000.0,
    static_rpm_grid: Sequence[float],
    probe_fraction: float = 0.02,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
    gentle_acceleration_limit_m_per_s2: float = 140.0,
) -> ScreenResult:
    """Score one tune using engagement and state-frozen onset checks.

    A candidate is rejected when the contact branch selected by the actual
    launch policy cannot be evaluated with positive normal resultants across
    the target window, or when free shift acceleration does not cross from
    opening to closing inside the grid.
    """

    try:
        resolved = resolve_primary_preload(
            candidate,
            target_engagement_rpm=target_engagement_rpm,
            static_lambda_limit=static_lambda_limit,
            kinetic_lambda_magnitude=kinetic_lambda_magnitude,
        )
    except Exception as error:
        fallback_constants = candidate_constants(candidate)
        fallback = ResolvedTune(
            candidate=candidate,
            constants=fallback_constants,
            target_engagement_rpm=target_engagement_rpm,
            resolved_primary_preload_mm=(
                fallback_constants.primary_spring_initial_compression / MILLIMETRE
            ),
            lower_stop_reaction_at_target_n=np.nan,
        )
        return ScreenResult(
            resolved=fallback,
            points=(),
            estimated_shift_onset_rpm=None,
            acceleration_at_target_plus_200=None,
            minimum_static_margin_near_target=None,
            stick_admissible_points=0,
            static_valid=False,
            score=np.inf,
            rejection_reason=f"{type(error).__name__}: {error}",
        )

    system, _ = build_operating_system(
        resolved.constants,
        static_lambda_limit=static_lambda_limit,
        kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    points = tuple(
        evaluate_static_shift_point(
            system=system,
            primary_rpm=float(primary_rpm),
            probe_fraction=probe_fraction,
        )
        for primary_rpm in static_rpm_grid
    )
    onset = _interpolate_zero(points)
    acceleration_200 = _interpolate_acceleration(
        points,
        primary_rpm=target_shift_onset_rpm + 200.0,
    )
    static_valid = all(point.accepted for point in points)
    target_margins = [
        point.minimum_static_margin
        for point in points
        if point.minimum_static_margin is not None
        and abs(point.primary_rpm - target_shift_onset_rpm)
        <= 0.5
        * (
            static_rpm_grid[1] - static_rpm_grid[0]
            if len(static_rpm_grid) > 1
            else 100.0
        )
    ]
    minimum_static_margin_near_target = min(target_margins) if target_margins else None
    stick_admissible_points = sum(point.stick_admissible for point in points)
    rejection_reason: str | None = None
    if not static_valid:
        rejection_reason = "selected near-low-ratio contact branch did not solve with positive normal resultants across the screen grid"
    elif onset is None:
        rejection_reason = (
            "free shift acceleration does not cross zero inside the screen grid"
        )
    elif acceleration_200 is None:
        rejection_reason = "target+200 rpm lies outside valid static interpolation"

    if rejection_reason is not None:
        return ScreenResult(
            resolved=resolved,
            points=points,
            estimated_shift_onset_rpm=onset,
            acceleration_at_target_plus_200=acceleration_200,
            minimum_static_margin_near_target=minimum_static_margin_near_target,
            stick_admissible_points=stick_admissible_points,
            static_valid=False,
            score=np.inf,
            rejection_reason=rejection_reason,
        )

    assert onset is not None
    assert acceleration_200 is not None
    traction_penalty = 0.0
    if minimum_static_margin_near_target is not None:
        traction_penalty = max(0.0, -minimum_static_margin_near_target) / 0.10
    score = (
        abs(onset - target_shift_onset_rpm) / 100.0
        + max(0.0, acceleration_200 - gentle_acceleration_limit_m_per_s2)
        / gentle_acceleration_limit_m_per_s2
        + traction_penalty
    )
    return ScreenResult(
        resolved=resolved,
        points=points,
        estimated_shift_onset_rpm=onset,
        acceleration_at_target_plus_200=acceleration_200,
        minimum_static_margin_near_target=minimum_static_margin_near_target,
        stick_admissible_points=stick_admissible_points,
        static_valid=True,
        score=score,
    )


def integrate_resolved_tune(
    resolved: ResolvedTune,
    *,
    duration_seconds: float,
    initial_primary_rpm: float = 1800.0,
    maximum_step_seconds: float = 0.005,
    relative_tolerance: float = 3.0e-5,
    absolute_tolerance: float = 1.0e-7,
    maximum_transitions: int = 100,
    method: str = "LSODA",
    first_step_seconds: float | None = None,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
    reporting_settings: ReportingSettings | None = None,
):
    """Integrate the actual hybrid launch from the requested rest state."""

    if duration_seconds <= 0.0:
        raise ValueError("duration_seconds must be strictly positive.")
    system, _ = build_operating_system(
        resolved.constants,
        static_lambda_limit=static_lambda_limit,
        kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    result = system.run(
        time_span=(0.0, duration_seconds),
        initial_state=launch_initial_state(primary_rpm=initial_primary_rpm),
        settings=HybridIntegratorSettings(
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
            method=method,
            max_step=maximum_step_seconds,
            first_step=first_step_seconds,
            maximum_transitions=maximum_transitions,
        ),
        reporting_settings=reporting_settings,
    )
    return system, result


def _sample_indices(count: int, maximum: int) -> NDArray[np.int64]:
    if count <= maximum:
        return np.arange(count, dtype=np.int64)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=np.int64))


def _allocate_sample_budget(
    segment_sizes: Iterable[int], maximum: int | None
) -> tuple[int, ...]:
    sizes = tuple(segment_sizes)
    if maximum is None:
        return sizes
    total = sum(sizes)
    if total <= maximum:
        return sizes
    raw = [max(2, round(maximum * size / total)) for size in sizes]
    while sum(raw) > maximum:
        index = max(range(len(raw)), key=lambda candidate: raw[candidate])
        if raw[index] <= 2:
            break
        raw[index] -= 1
    return tuple(raw)


def mode_label(mode: CVTOperatingRegime) -> str:
    if mode.contact_regime is None:
        return f"{mode.engagement.value}/{mode.shift_constraint.value}"
    return (
        f"{mode.engagement.value}/{mode.shift_constraint.value}/"
        f"{mode.contact_regime.mode.value}"
    )


def sample_launch_trace(
    *,
    system: CVTOperatingHybridSystem,
    result,
    maximum_samples: int | None = None,
) -> LaunchTrace:
    """Re-evaluate accepted samples for plotting and exportable diagnostics."""

    trace_time: list[float] = []
    trace_state: list[NDArray[np.float64]] = []
    labels: list[str] = []
    primary_surface: list[float] = []
    secondary_surface: list[float] = []
    primary_torque: list[float] = []
    secondary_torque: list[float] = []
    primary_lambda: list[float] = []
    secondary_lambda: list[float] = []
    primary_normal: list[float] = []
    secondary_normal: list[float] = []
    primary_relative_speed: list[float] = []
    secondary_relative_speed: list[float] = []
    stop_reaction: list[float] = []

    budgets = _allocate_sample_budget(
        (segment.state.shape[1] for segment in result.segments),
        maximum=maximum_samples,
    )
    for segment, budget in zip(result.segments, budgets, strict=True):
        for index in _sample_indices(segment.state.shape[1], budget):
            time = float(segment.time[index])
            vector = np.asarray(segment.state[:, index], dtype=float)
            state = CVTDynamicState.from_vector(vector)
            evaluation = system.inspect(time=time, state=vector, mode=segment.mode)
            trace_time.append(time)
            trace_state.append(vector)
            labels.append(mode_label(segment.mode))

            if isinstance(evaluation, DeadzoneEvaluation):
                primary_surface.append(np.nan)
                secondary_surface.append(
                    evaluation.snapshot.belt_secondary_lock_radius
                    * state.secondary_angular_speed
                )
                primary_torque.append(evaluation.primary_transmitted_torque)
                secondary_torque.append(np.nan)
                primary_lambda.append(np.nan)
                secondary_lambda.append(np.nan)
                primary_normal.append(evaluation.primary_normal_resultant)
                secondary_normal.append(np.nan)
                primary_relative_speed.append(np.nan)
                secondary_relative_speed.append(np.nan)
                stop_reaction.append(
                    np.nan
                    if evaluation.stop_reaction is None
                    else evaluation.stop_reaction
                )
                continue

            assert isinstance(evaluation, CVTContactEvaluation)
            unknowns = evaluation.closure_unknowns
            primary_surface.append(
                evaluation.snapshot.geometry.primary.effective
                * state.primary_angular_speed
            )
            secondary_surface.append(
                evaluation.snapshot.geometry.secondary.effective
                * state.secondary_angular_speed
            )
            primary_torque.append(unknowns.primary_torque)
            secondary_torque.append(unknowns.secondary_torque)
            primary_lambda.append(evaluation.traction_utilization.primary_lambda)
            secondary_lambda.append(evaluation.traction_utilization.secondary_lambda)
            primary_normal.append(evaluation.normal_primary)
            secondary_normal.append(evaluation.normal_secondary)
            primary_relative_speed.append(
                evaluation.relative_motion.primary_relative_speed
            )
            secondary_relative_speed.append(
                evaluation.relative_motion.secondary_relative_speed
            )
            active_constraint_reaction = evaluation.low_ratio_seat_reaction
            if active_constraint_reaction is None:
                active_constraint_reaction = evaluation.upper_stop_reaction
            stop_reaction.append(
                np.nan
                if active_constraint_reaction is None
                else active_constraint_reaction
            )

    return LaunchTrace(
        time=np.asarray(trace_time, dtype=float),
        state=np.column_stack(trace_state),
        mode_label=tuple(labels),
        primary_surface_speed=np.asarray(primary_surface, dtype=float),
        secondary_surface_speed=np.asarray(secondary_surface, dtype=float),
        primary_torque=np.asarray(primary_torque, dtype=float),
        secondary_torque=np.asarray(secondary_torque, dtype=float),
        primary_lambda=np.asarray(primary_lambda, dtype=float),
        secondary_lambda=np.asarray(secondary_lambda, dtype=float),
        primary_normal=np.asarray(primary_normal, dtype=float),
        secondary_normal=np.asarray(secondary_normal, dtype=float),
        primary_relative_speed=np.asarray(primary_relative_speed, dtype=float),
        secondary_relative_speed=np.asarray(secondary_relative_speed, dtype=float),
        stop_reaction=np.asarray(stop_reaction, dtype=float),
    )


def _short_transition_label(reason: str) -> str:
    """Compact, plot-safe wording for hybrid events."""

    if "lower_stop_released" in reason:
        return "low stop"
    if "primary_closed_into_engaged_contact" in reason:
        return "engage"
    if "low_ratio_seat_reached" in reason:
        return "low seat"
    if "low_ratio_seat_released" in reason:
        return "shift start"
    if "static_capacity_exhausted" in reason:
        return "slip"
    if "contact_restuck" in reason:
        return "re-stick"
    if "upper_stop_reached" in reason:
        return "high stop"
    if "upper_stop_released" in reason:
        return "high release"
    if "primary_opened_through_disengagement" in reason:
        return "disengage"
    return reason.replace("_", " ")


def _add_transition_markers(*, axes: Iterable[plt.Axes], result) -> None:
    axes = tuple(axes)
    for record_index, record in enumerate(result.transitions):
        label = _short_transition_label(record.transition.reason)
        y_fraction = 0.975 - 0.115 * (record_index % 5)
        for axis in axes:
            axis.axvline(record.time, linestyle="--", linewidth=0.9, alpha=0.75)
            axis.annotate(
                label,
                xy=(record.time, y_fraction),
                xycoords=("data", "axes fraction"),
                xytext=(2, 0),
                textcoords="offset points",
                rotation=90,
                va="top",
                ha="left",
                fontsize=6,
                alpha=0.9,
            )


def plot_primary_ramp_profile(*, resolved: ResolvedTune):
    """Plot the profile quantities that set the primary flyweight force.

    The runtime law is ``F_fw = m omega^2 (r_0 + Delta r) d(Delta r)/ds``.
    Plotting its geometry separately makes the circular design transparent:
    it starts with a stronger radial slope and then fades continuously.
    """

    constants = resolved.constants
    if constants.primary_ramp_kind == "linear":
        segment = LinearSegment(
            length=constants.max_shift,
            angle_degrees=constants.primary_ramp_angle_degrees,
        )
        ramp_name = f"linear {constants.primary_ramp_angle_degrees:.0f}°"
    else:
        segment = CircularSegment(
            length=constants.max_shift,
            angle_start_degrees=constants.primary_ramp_start_angle_degrees,
            angle_end_degrees=constants.primary_ramp_end_angle_degrees,
            quadrant=2,
        )
        ramp_name = (
            f"circular {constants.primary_ramp_start_angle_degrees:.0f}°"
            f"→{constants.primary_ramp_end_angle_degrees:.0f}°"
        )
    profile = PiecewiseRamp((segment,))
    shift = np.linspace(0.0, constants.max_shift, 300)
    samples = [profile.evaluate(float(position)) for position in shift]
    displacement = np.asarray([sample.value for sample in samples])
    slope = np.asarray([sample.first_derivative for sample in samples])
    radius = constants.initial_flyweight_radius + displacement
    normalized_force = radius * slope

    figure, axes = plt.subplots(
        3, 1, figsize=(10, 9), sharex=True, constrained_layout=True
    )
    axes[0].plot(shift / MILLIMETRE, displacement / MILLIMETRE)
    axes[0].set_ylabel(r"$\Delta r_f$ [mm]")
    axes[0].set_title(f"Primary flyweight-ramp profile: {ramp_name}")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(shift / MILLIMETRE, slope)
    axes[1].set_ylabel(r"$d\Delta r_f/ds$ [-]")
    axes[1].grid(True, alpha=0.25)

    for rpm in (2000.0, 3000.0, 3500.0):
        omega = rpm / RPM_PER_RADIAN_PER_SECOND
        force = constants.flyweight_mass * omega**2 * normalized_force
        axes[2].plot(shift / MILLIMETRE, force, label=f"{rpm:.0f} rpm")
    axes[2].set_xlabel("Shift coordinate [mm]")
    axes[2].set_ylabel(r"$F_{\mathrm{fw}}$ [N]")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="best")
    return figure


def plot_launch_diagnostics(
    *,
    trace: LaunchTrace,
    result,
    resolved: ResolvedTune,
    static_lambda_limit: float,
):
    """Return a full launch diagnostic figure.

    The shift curve intentionally uses the conventional wording/order:
    **primary speed vs secondary speed**, therefore x = secondary and
    y = primary.  This is the requested flip from the older preview plot.
    """

    time = trace.time
    state = trace.state
    primary_rpm = state[0] * RPM_PER_RADIAN_PER_SECOND
    secondary_rpm = state[1] * RPM_PER_RADIAN_PER_SECOND
    constants = resolved.constants

    figure, axes = plt.subplots(3, 3, figsize=(19, 14), constrained_layout=True)
    speed_axis = axes[0, 0]
    speed_axis.plot(time, primary_rpm, label=r"$\omega_p$")
    speed_axis.plot(time, secondary_rpm, label=r"$\omega_s$")
    speed_axis.set_title("Shaft speeds")
    speed_axis.set_xlabel("Time [s]")
    speed_axis.set_ylabel("Speed [rpm]")
    speed_axis.grid(True, alpha=0.25)
    speed_axis.legend(loc="best")

    shift_axis = axes[0, 1]
    shift_axis.plot(time, state[3] / MILLIMETRE, label=r"$s$")
    shift_axis.axhline(0.0, linestyle=":", label=r"$s_{\rm low}$")
    shift_axis.axhline(
        constants.deadzone_shift / MILLIMETRE,
        linestyle="--",
        label=r"$s_{\rm engage}$",
    )
    shift_axis.axhline(
        constants.max_shift / MILLIMETRE,
        linestyle="--",
        label=r"$s_{\rm high}$",
    )
    shift_axis.set_title("Shift coordinate and physical boundaries")
    shift_axis.set_xlabel("Time [s]")
    shift_axis.set_ylabel("Shift coordinate [mm]")
    shift_axis.grid(True, alpha=0.25)
    shift_speed_axis = shift_axis.twinx()
    shift_speed_axis.plot(
        time, state[4] / MILLIMETRE, linestyle=":", label=r"$\dot{s}$"
    )
    shift_speed_axis.set_ylabel("Shift speed [mm/s]")
    handles, labels = shift_axis.get_legend_handles_labels()
    handles_2, labels_2 = shift_speed_axis.get_legend_handles_labels()
    shift_axis.legend(handles + handles_2, labels + labels_2, loc="best")

    curve_axis = axes[0, 2]
    curve_axis.plot(secondary_rpm, primary_rpm, label="trajectory")
    curve_axis.scatter([secondary_rpm[0]], [primary_rpm[0]], marker="o", label="launch")
    for record in result.transitions:
        point = np.asarray(record.post_transition_state, dtype=float)[:2]
        point = point * RPM_PER_RADIAN_PER_SECOND
        curve_axis.scatter([point[1]], [point[0]], marker="x")
        curve_axis.annotate(
            _short_transition_label(record.transition.reason),
            xy=(point[1], point[0]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=6.5,
        )
    curve_axis.set_title("Shift curve: primary vs secondary speed")
    curve_axis.set_xlabel("Secondary speed [rpm]")
    curve_axis.set_ylabel("Primary speed [rpm]")
    curve_axis.grid(True, alpha=0.25)
    curve_axis.legend(loc="best")

    surface_axis = axes[1, 0]
    surface_axis.plot(time, state[2], label=r"$v_b$")
    surface_axis.plot(time, trace.primary_surface_speed, label=r"$r_p\omega_p$")
    surface_axis.plot(time, trace.secondary_surface_speed, label=r"$r_s\omega_s$")
    surface_axis.set_title("Belt and pulley surface speeds")
    surface_axis.set_xlabel("Time [s]")
    surface_axis.set_ylabel("Tangential speed [m/s]")
    surface_axis.grid(True, alpha=0.25)
    surface_axis.legend(loc="best")

    torque_axis = axes[1, 1]
    torque_axis.plot(time, trace.primary_torque, label=r"$\tau_p$")
    torque_axis.plot(time, trace.secondary_torque, label=r"$\tau_s$")
    torque_axis.set_title("Engaged torque path")
    torque_axis.set_xlabel("Time [s]")
    torque_axis.set_ylabel("Torque [N m]")
    torque_axis.grid(True, alpha=0.25)
    torque_axis.legend(loc="best")

    lambda_axis = axes[1, 2]
    lambda_axis.plot(time, trace.primary_lambda, label=r"$\lambda_p$")
    lambda_axis.plot(time, trace.secondary_lambda, label=r"$\lambda_s$")
    lambda_axis.axhline(static_lambda_limit, linestyle="--", label="static bounds")
    lambda_axis.axhline(-static_lambda_limit, linestyle="--")
    lambda_axis.set_title("Contact traction utilization")
    lambda_axis.set_xlabel("Time [s]")
    lambda_axis.set_ylabel(r"$\lambda$ [-]")
    lambda_axis.grid(True, alpha=0.25)
    lambda_axis.legend(loc="best")

    normal_axis = axes[2, 0]
    normal_axis.plot(time, trace.primary_normal, label=r"$N_p$")
    normal_axis.plot(time, trace.secondary_normal, label=r"$N_s$")
    normal_axis.set_title("Normal resultants")
    normal_axis.set_xlabel("Time [s]")
    normal_axis.set_ylabel("Resultant [N]")
    normal_axis.grid(True, alpha=0.25)
    normal_axis.legend(loc="best")

    relative_axis = axes[2, 1]
    relative_axis.plot(time, trace.primary_relative_speed, label=r"$v_{\rm rel,p}$")
    relative_axis.plot(time, trace.secondary_relative_speed, label=r"$v_{\rm rel,s}$")
    relative_axis.axhline(0.0, linestyle=":")
    relative_axis.set_title("Engaged contact relative speeds")
    relative_axis.set_xlabel("Time [s]")
    relative_axis.set_ylabel("Relative speed [m/s]")
    relative_axis.grid(True, alpha=0.25)
    relative_axis.legend(loc="best")

    reaction_axis = axes[2, 2]
    reaction_axis.plot(time, trace.stop_reaction, label="active stop reaction")
    reaction_axis.axhline(0.0, linestyle=":")
    reaction_axis.set_title("Active shift-boundary reaction")
    reaction_axis.set_xlabel("Time [s]")
    reaction_axis.set_ylabel("Reaction [N]")
    reaction_axis.grid(True, alpha=0.25)
    reaction_axis.legend(loc="best")

    _add_transition_markers(
        axes=(
            speed_axis,
            shift_axis,
            surface_axis,
            torque_axis,
            lambda_axis,
            normal_axis,
            relative_axis,
            reaction_axis,
        ),
        result=result,
    )
    candidate = resolved.candidate
    ramp_label = (
        f"ramp=L{candidate.primary_ramp_angle_degrees:.0f}"
        if candidate.primary_ramp_kind == "linear"
        else (
            f"ramp=C{candidate.primary_ramp_start_angle_degrees:.0f}"
            f"→{candidate.primary_ramp_end_angle_degrees:.0f}"
        )
    )
    figure.suptitle(
        "CINDER full launch diagnostic | "
        f"m={candidate.flyweight_mass_kg:.3f} kg, {ramp_label}, "
        f"helix={candidate.helix_angle_degrees:.1f} deg, "
        f"twist={candidate.secondary_torsional_pretension_degrees:.0f} deg, "
        f"sec preload={candidate.secondary_compression_preload_mm:.1f} mm, "
        f"primary preload={resolved.resolved_primary_preload_mm:.2f} mm",
        fontsize=14,
    )
    return figure


def transition_metrics(
    *, result, trace: LaunchTrace, resolved: ResolvedTune
) -> dict[str, float | int | str | None]:
    """Extract launch metrics with the physical main-shift event kept explicit.

    Entering engaged contact produces a short capture transient.  It is not the
    main upshift.  The present operating graph makes the physically useful
    onset unambiguous: release of the low-ratio seat by a tensile reaction.
    """

    reasons = tuple(record.transition.reason for record in result.transitions)
    engagement_times = [
        record.time
        for record in result.transitions
        if "primary_closed_into_engaged_contact" in record.transition.reason
    ]
    disengagement_times = [
        record.time
        for record in result.transitions
        if "primary_opened_through_disengagement" in record.transition.reason
    ]
    low_ratio_release_records = [
        record
        for record in result.transitions
        if "low_ratio_seat_released_by_tensile_reaction" in record.transition.reason
    ]
    upper_stop_records = [
        record
        for record in result.transitions
        if "upper_stop_reached" in record.transition.reason
    ]
    upper_stop_impacts = [
        record
        for record in result.transitions
        if "upper_stop" in record.transition.reason
        and "impact" in record.transition.reason
    ]
    engaged_segment_durations = [
        segment.end_time - segment.start_time
        for segment in result.segments
        if segment.mode.engagement is CVTEngagementState.ENGAGED
    ]
    longest_engaged_duration = max(engaged_segment_durations, default=0.0)

    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    active_shift = trace.state[3] - resolved.constants.deadzone_shift
    active_travel = resolved.constants.max_shift - resolved.constants.deadzone_shift
    normalized_shift = np.clip(active_shift / active_travel, 0.0, 1.0)

    if low_ratio_release_records:
        main_release = low_ratio_release_records[0]
        main_shift_onset_time = float(main_release.time)
        main_shift_onset_primary_rpm = float(
            main_release.post_transition_state[0] * RPM_PER_RADIAN_PER_SECOND
        )
        after_main = trace.time >= main_shift_onset_time - 1.0e-12
    else:
        main_shift_onset_time = None
        main_shift_onset_primary_rpm = None
        after_main = np.zeros(trace.time.shape, dtype=bool)

    ten = np.flatnonzero(after_main & (normalized_shift >= 0.10))
    ninety = np.flatnonzero(after_main & (normalized_shift >= 0.90))
    shift_10_to_90 = None
    if ten.size and ninety.size:
        shift_10_to_90 = float(trace.time[int(ninety[0])] - trace.time[int(ten[0])])

    main_shift_speeds = np.abs(trace.state[4, after_main]) / MILLIMETRE
    maximum_main_shift_speed = (
        float(np.max(main_shift_speeds)) if main_shift_speeds.size else None
    )

    primary_slip_indices = np.flatnonzero(
        np.asarray(["primary_slip" in label for label in trace.mode_label], dtype=bool)
    )
    primary_slip_start_time = (
        None
        if primary_slip_indices.size == 0
        else float(trace.time[int(primary_slip_indices[0])])
    )
    primary_restuck_records = [
        record
        for record in result.transitions
        if "contact_restuck" in record.transition.reason
    ]
    if primary_restuck_records:
        primary_restuck = primary_restuck_records[0]
        primary_restuck_time = float(primary_restuck.time)
        primary_restuck_primary_rpm = float(
            primary_restuck.post_transition_state[0] * RPM_PER_RADIAN_PER_SECOND
        )
        primary_restuck_shift_mm = float(
            primary_restuck.post_transition_state[3] / MILLIMETRE
        )
    else:
        primary_restuck_time = None
        primary_restuck_primary_rpm = None
        primary_restuck_shift_mm = None
    primary_slip_duration = (
        None
        if primary_slip_start_time is None or primary_restuck_time is None
        else float(primary_restuck_time - primary_slip_start_time)
    )

    return {
        "completed": int(result.completed),
        "termination_reason": result.termination_reason,
        "final_time_s": float(result.final_time),
        "segments": len(result.segments),
        "transitions": len(result.transitions),
        "engagement_events": len(engagement_times),
        "disengagement_events": len(disengagement_times),
        "first_engagement_time_s": (
            None if not engagement_times else float(engagement_times[0])
        ),
        "longest_contiguous_engaged_duration_s": float(longest_engaged_duration),
        "primary_slip_start_time_s": primary_slip_start_time,
        "primary_restuck_time_s": primary_restuck_time,
        "primary_restuck_primary_rpm": primary_restuck_primary_rpm,
        "primary_restuck_shift_mm": primary_restuck_shift_mm,
        "primary_slip_duration_s": primary_slip_duration,
        "main_shift_onset_time_s": main_shift_onset_time,
        "main_shift_onset_primary_rpm": main_shift_onset_primary_rpm,
        "observed_shift_onset_time_s": main_shift_onset_time,
        "observed_shift_onset_primary_rpm": main_shift_onset_primary_rpm,
        "shift_10_to_90_s": shift_10_to_90,
        "maximum_main_shift_speed_mm_per_s": maximum_main_shift_speed,
        "upper_stop_time_s": (
            None if not upper_stop_records else float(upper_stop_records[0].time)
        ),
        "upper_stop_impact_time_s": (
            None if not upper_stop_impacts else float(upper_stop_impacts[0].time)
        ),
        "final_primary_rpm": float(primary_rpm[-1]),
        "final_secondary_rpm": float(trace.state[1, -1] * RPM_PER_RADIAN_PER_SECOND),
        "final_shift_mm": float(trace.state[3, -1] / MILLIMETRE),
        "maximum_shift_mm": float(np.max(trace.state[3]) / MILLIMETRE),
        "maximum_shift_speed_mm_per_s": float(
            np.max(np.abs(trace.state[4])) / MILLIMETRE
        ),
        "persistent_engagement": int(longest_engaged_duration >= 0.050),
        "transition_reasons": " | ".join(reasons),
    }


def require_locked_vehicle_output_boundary(
    system: CVTOperatingHybridSystem,
) -> LockedFinalDriveVehicle:
    """Return the locked vehicle boundary carried by one runtime system.

    This is intentionally a read-only inspection helper.  Editing a route still
    starts from :class:`CVTSimulationCase` and rebuilds the runtime model via
    :func:`case_with_output_road_profile`; a hybrid system is never treated as
    an editable case container.
    """

    if not isinstance(system, CVTOperatingHybridSystem):
        raise TypeError("system must be a CVTOperatingHybridSystem.")
    boundary = system.model.output_boundary
    if not isinstance(boundary, LockedFinalDriveVehicle):
        raise TypeError(
            "This operation requires a LockedFinalDriveVehicle output boundary; "
            f"received {type(boundary).__name__}."
        )
    return boundary


def case_with_output_road_profile(
    case: CVTSimulationCase,
    road_profile,
) -> CVTSimulationCase:
    """Return one editable case with only its locked-vehicle route replaced.

    This is configuration assembly only.  The caller then creates exactly one
    runtime system through the explicit operating configuration and runs
    one continuous hybrid integration.
    """

    if not isinstance(case, CVTSimulationCase):
        raise TypeError("case must be a CVTSimulationCase.")
    boundary = case.output_boundary
    if not isinstance(boundary, LockedFinalDriveVehicle):
        raise TypeError(
            "The requested road profile requires a LockedFinalDriveVehicle "
            "output boundary."
        )
    return case.with_output_boundary(boundary.with_road_profile(road_profile))


def build_system_from_case(
    case: CVTSimulationCase,
    *,
    configuration: CVTOperatingSystemConfig,
) -> CVTOperatingHybridSystem:
    """Build one runtime hybrid system from one fully specified immutable case."""

    if not isinstance(case, CVTSimulationCase):
        raise TypeError("case must be a CVTSimulationCase.")
    if not isinstance(configuration, CVTOperatingSystemConfig):
        raise TypeError("configuration must be a CVTOperatingSystemConfig.")
    return configuration.build(case)
