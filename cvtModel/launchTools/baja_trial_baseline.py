"""Default Baja-style CINDER assembly and composed-system helpers.

This module centralizes the physical constants used by the launch tools. It is a
thin import surface over ``run_route_grade_response`` so every script builds the
same five-state CVT plant, primary engine shaft boundary, secondary shaft
boundary, and host state.
"""

from __future__ import annotations

from dataclasses import dataclass

from cinder.model.system import CVTState
from cinder.model.cvt.contact import ContactTractionUtilization

from run_route_grade_response import (  # noqa: F401
    BajaTrialConstants,
    GradePhase,
    GradeProgramme,
    ResolvedTune,
    TimeProgrammedLockedFinalDriveBoundary,
    TuneCandidate,
    build_components,
    build_composed_system,
    candidate_constants,
    launch_cvt_state,
    load_candidate,
    lower_stop_reaction,
    resolve_primary_preload,
    RPM_TO_RAD_PER_SECOND,
    RPM_PER_RADIAN_PER_SECOND,
    INCH_TO_METRE,
    MILLIMETRE,
    FOOT_POUND_TO_NEWTON_METRE,
)


@dataclass(frozen=True, slots=True)
class BajaTrialBaseline:
    """Convenience bundle for static studies and diagnostics."""

    constants: BajaTrialConstants
    assembly: object
    engine: object
    road_load: object
    system: object
    active_shift_state: CVTState
    quasi_static_state: CVTState
    deadzone_state: CVTState
    default_trial: ContactTractionUtilization
    lambda_sweep: tuple[ContactTractionUtilization, ...]

    @property
    def plant(self):
        return self.system.cvt.model


def _no_slip_state_at_shift(*, geometry, shift_position: float, secondary_speed: float, shift_speed: float) -> CVTState:
    position = geometry.evaluate(shift_position)
    primary_speed = secondary_speed * position.secondary.effective / position.primary.effective
    belt_speed = primary_speed * position.primary.effective
    return CVTState(
        primary_angular_speed=primary_speed,
        secondary_angular_speed=secondary_speed,
        belt_speed=belt_speed,
        shift_position=shift_position,
        shift_speed=shift_speed,
    )


def build_baja_trial_baseline(constants: BajaTrialConstants | None = None) -> BajaTrialBaseline:
    c = constants or BajaTrialConstants()
    programme = GradeProgramme.default()
    system, engine, road_load = build_composed_system(c, programme)
    assembly = system.cvt.model  # plant owns assembly-resolved mechanics; assembly also returned below.
    assembly_spec, _, _ = build_components(c)
    active_shift_position = c.deadzone_shift + 0.60 * (c.max_shift - c.deadzone_shift)
    deadzone_shift_position = 0.50 * c.deadzone_shift
    geometry = assembly_spec.geometry
    return BajaTrialBaseline(
        constants=c,
        assembly=assembly_spec,
        engine=engine,
        road_load=road_load,
        system=system,
        active_shift_state=_no_slip_state_at_shift(
            geometry=geometry,
            shift_position=active_shift_position,
            secondary_speed=180.0,
            shift_speed=0.012,
        ),
        quasi_static_state=_no_slip_state_at_shift(
            geometry=geometry,
            shift_position=active_shift_position,
            secondary_speed=180.0,
            shift_speed=0.0,
        ),
        deadzone_state=_no_slip_state_at_shift(
            geometry=geometry,
            shift_position=deadzone_shift_position,
            secondary_speed=60.0,
            shift_speed=0.006,
        ),
        default_trial=ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=-0.10),
        lambda_sweep=(
            ContactTractionUtilization(primary_lambda=0.05, secondary_lambda=-0.05),
            ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=-0.10),
            ContactTractionUtilization(primary_lambda=0.15, secondary_lambda=-0.10),
            ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=-0.15),
            ContactTractionUtilization(primary_lambda=0.20, secondary_lambda=-0.20),
        ),
    )
