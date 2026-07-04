"""Small, physical tuning helpers shared by launch-oriented diagnostics.

This module intentionally lives under ``tools`` rather than ``cinder``.  It
uses the simulator to inspect a candidate mechanism, but it does not define
runtime CVT physics or a controller.  Its purpose is to turn interpretable
primary-side design targets into the corresponding baseline constants.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from baja_trial_baseline import (
    BajaTrialConstants,
    RPM_TO_RAD_PER_SECOND,
    build_baja_trial_baseline,
)
from cinder.dynamics.deadzone import DeadzoneDynamicsEvaluator
from cinder.integration import CVTDynamicState


@dataclass(frozen=True, slots=True)
class PrimaryTuningRequest:
    """Physical primary-side choices used by a diagnostic baseline.

    ``target_lower_stop_release_rpm`` is optional.  When supplied, the helper
    derives primary spring preload such that the *deadzone lower-stop* primary
    force balance is zero at that shaft speed.  It therefore controls the
    nominal speed at which the primary first becomes able to leave the lower
    stop; it is not a promise of a particular full-launch shift trajectory.
    """

    flyweight_mass: float
    ramp_angle_degrees: float
    spring_rate: float
    explicit_preload: float
    target_lower_stop_release_rpm: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("flyweight_mass", self.flyweight_mass),
            ("ramp_angle_degrees", self.ramp_angle_degrees),
            ("spring_rate", self.spring_rate),
            ("explicit_preload", self.explicit_preload),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if self.flyweight_mass <= 0.0:
            raise ValueError("flyweight_mass must be strictly positive.")
        if not 0.0 < self.ramp_angle_degrees < 89.0:
            raise ValueError(
                "ramp_angle_degrees must lie strictly between 0 and 89 degrees."
            )
        if self.spring_rate <= 0.0:
            raise ValueError("spring_rate must be strictly positive.")
        if self.explicit_preload < 0.0:
            raise ValueError("explicit_preload must be non-negative.")
        if self.target_lower_stop_release_rpm is not None:
            if (
                not isfinite(self.target_lower_stop_release_rpm)
                or self.target_lower_stop_release_rpm <= 0.0
            ):
                raise ValueError(
                    "target_lower_stop_release_rpm must be finite and positive."
                )


@dataclass(frozen=True, slots=True)
class PrimaryTuningResult:
    """Resolved primary tuning constants and the lower-stop force check."""

    constants: BajaTrialConstants
    request: PrimaryTuningRequest
    resolved_preload: float
    target_lower_stop_release_rpm: float | None
    lower_stop_force_at_target: float | None


def resolve_primary_tuning(
    *,
    reference_constants: BajaTrialConstants,
    request: PrimaryTuningRequest,
) -> PrimaryTuningResult:
    """Return constants with an explicit or target-derived primary preload.

    The preload solve is intentionally local to the lower stop.  It uses two
    exact simulator evaluations to exploit the current linear preload law,
    rather than embedding a hand-derived ramp/spring formula in a plotting
    script.  This remains correct if the primary local axial-coordinate map is
    later changed.
    """

    if not isinstance(reference_constants, BajaTrialConstants):
        raise TypeError("reference_constants must be a BajaTrialConstants instance.")
    if not isinstance(request, PrimaryTuningRequest):
        raise TypeError("request must be a PrimaryTuningRequest instance.")

    base = replace(
        reference_constants,
        flyweight_mass=request.flyweight_mass,
        primary_ramp_angle_degrees=request.ramp_angle_degrees,
        primary_spring_rate=request.spring_rate,
        primary_spring_initial_compression=request.explicit_preload,
    )

    if request.target_lower_stop_release_rpm is None:
        return PrimaryTuningResult(
            constants=base,
            request=request,
            resolved_preload=base.primary_spring_initial_compression,
            target_lower_stop_release_rpm=None,
            lower_stop_force_at_target=None,
        )

    target_rpm = request.target_lower_stop_release_rpm
    preload = solve_preload_for_lower_stop_release(
        reference_constants=base,
        target_primary_rpm=target_rpm,
    )
    resolved = replace(base, primary_spring_initial_compression=preload)
    force = lower_stop_primary_force(
        constants=resolved,
        primary_rpm=target_rpm,
    )
    return PrimaryTuningResult(
        constants=resolved,
        request=request,
        resolved_preload=preload,
        target_lower_stop_release_rpm=target_rpm,
        lower_stop_force_at_target=force,
    )


def solve_preload_for_lower_stop_release(
    *,
    reference_constants: BajaTrialConstants,
    target_primary_rpm: float,
) -> float:
    """Solve the primary preload giving zero free axial force at the low stop.

    At the lower stop, the deadzone unilateral reaction is

    .. math:: R_{\rm low}=-F_p.

    Release occurs at ``R_low = 0``, equivalently ``F_p = 0``.  The current
    primary spring law is affine in preload, so two force samples recover the
    exact preload without an iterative optimization.
    """

    if not isinstance(reference_constants, BajaTrialConstants):
        raise TypeError("reference_constants must be a BajaTrialConstants instance.")
    if not isfinite(target_primary_rpm) or target_primary_rpm <= 0.0:
        raise ValueError("target_primary_rpm must be finite and strictly positive.")

    zero_preload_constants = replace(
        reference_constants,
        primary_spring_initial_compression=0.0,
    )
    unit_preload = 1.0e-3
    unit_preload_constants = replace(
        zero_preload_constants,
        primary_spring_initial_compression=unit_preload,
    )
    force_zero = lower_stop_primary_force(
        constants=zero_preload_constants,
        primary_rpm=target_primary_rpm,
    )
    force_unit = lower_stop_primary_force(
        constants=unit_preload_constants,
        primary_rpm=target_primary_rpm,
    )
    slope = (force_unit - force_zero) / unit_preload
    if not isfinite(slope) or slope >= 0.0:
        raise RuntimeError(
            "Expected a negative primary-force slope with preload at the lower stop; "
            f"got {slope:.6e} N/m."
        )

    preload = -force_zero / slope
    if not isfinite(preload) or preload < 0.0:
        raise RuntimeError(
            "The requested lower-stop release speed would require negative or non-finite "
            f"primary preload ({preload!r})."
        )
    return float(preload)


def lower_stop_primary_force(
    *, constants: BajaTrialConstants, primary_rpm: float
) -> float:
    """Return the unconstrained primary closing force at the lower stop."""

    if not isinstance(constants, BajaTrialConstants):
        raise TypeError("constants must be a BajaTrialConstants instance.")
    if not isfinite(primary_rpm) or primary_rpm < 0.0:
        raise ValueError("primary_rpm must be finite and non-negative.")

    baseline = build_baja_trial_baseline(constants)
    state = CVTDynamicState(
        primary_angular_speed=primary_rpm * RPM_TO_RAD_PER_SECOND,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
        secondary_shaft_angle=0.0,
    )
    snapshot = DeadzoneDynamicsEvaluator(model=baseline.model).snapshot(state=state)
    return float(snapshot.primary_actuation.bias_force)
