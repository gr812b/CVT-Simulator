"""Search for where dynamic CVT actuator mechanics materially matter.

This is a mechanism stress/search study, not a single hand-picked transient.

Workflow
--------
1. Run the FULL dynamic Baja model through a flat launch.
2. Extract common already-engaged restart states at several shift fractions.
3. Coarsely screen hundreds of finite continuous perturbations using the full
   model only:
      - grade/load ramps,
      - direct secondary-shaft torque ramps,
      - primary-shaft torque ramps.
4. Rank cases by the *direct* flyweight and helix dynamic corrections while
   classifying whether the response remained continuous, switched contact
   regime, or hit a hybrid state reset/impact.
5. Re-run the strongest, diverse cases with ALL FOUR actuator models from the
   exact same initial state:
      full
      quasi_static_flyweight
      quasi_static_helix
      fully_quasi_static
6. Save rich, high-resolution diagnostics for every selected case so later
   post-processing can make new figures without re-running CINDER.

The study deliberately distinguishes:
  A. direct constitutive/mechanism prediction error,
  B. continuous trajectory consequence,
  C. contact switching / hybrid reset consequence.

Requires the rich actuator-ablation module already installed as:
    cvtModel/launchTools/run_dynamic_actuator_ablation.py
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, asdict, replace
import json
from math import degrees, isfinite
from pathlib import Path
import sys
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_dynamic_actuator_ablation as ab  # noqa: E402
import run_route_grade_response as route  # noqa: E402

from cinder.execution.hybrid import (  # noqa: E402
    HybridIntegratorSettings,
    integrate_hybrid,
)
from cinder.execution.hybrid.composed import (  # noqa: E402
    ComposedCVTHybridSystem,
)
from cinder.hosts import SecondaryShaftAngleHost  # noqa: E402
from cinder.model.boundaries.shaft import (  # noqa: E402
    FullThrottleEngineBoundary,
)
from cinder.model.system import (  # noqa: E402
    CVTState,
    MechanicalCVTPlant,
    ShaftBoundaryValue,
)

MILLIMETRE = 1.0e-3
RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
NAN = float("nan")


# ---------------------------------------------------------------------------
# Search-grid definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RestartState:
    variant_key: str
    key: str
    target_shift_percent: float
    actual_shift_percent: float
    source_time_s: float
    full_state: np.ndarray
    composed_mode: object
    primary_rpm: float
    secondary_rpm: float
    shift_mm: float
    shift_speed_mm_s: float


@dataclass(frozen=True, slots=True)
class StressCandidate:
    case_id: str
    restart_key: str
    restart_shift_percent: float
    family: str
    amplitude: float
    ramp_s: float
    onset_s: float
    hold_s: float

    @property
    def duration_s(self) -> float:
        return self.onset_s + self.ramp_s + self.hold_s

    @property
    def amplitude_label(self) -> str:
        if self.family == "grade":
            return f"{self.amplitude:+.0f} deg"
        return f"{self.amplitude:+.0f} N m"


class SmoothStepSignal:
    """Finite smoothstep from zero to one target value, then hold."""

    def __init__(
        self,
        *,
        onset_s: float,
        ramp_s: float,
        target: float,
    ) -> None:
        self.onset_s = float(onset_s)
        self.ramp_s = float(ramp_s)
        self.target = float(target)

    def value(self, time_s: float) -> float:
        t = float(time_s)
        if t <= self.onset_s:
            return 0.0
        if t >= self.onset_s + self.ramp_s:
            return self.target
        u = (t - self.onset_s) / self.ramp_s
        smooth = u * u * (3.0 - 2.0 * u)
        return self.target * smooth


class AddedTorqueBoundary:
    """Wrap a shaft boundary and add a known time-dependent torque."""

    def __init__(self, base, signal: SmoothStepSignal) -> None:
        self.base = base
        self.signal = signal

    def evaluate(self, context) -> ShaftBoundaryValue:
        base_value = self.base.evaluate(context)
        extra = self.signal.value(context.time)
        metadata = dict(base_value.metadata)
        metadata["stress_extra_torque_Nm"] = extra
        return ShaftBoundaryValue(
            external_torque=(
                base_value.external_torque + extra
            ),
            equivalent_inertia=base_value.equivalent_inertia,
            metadata=metadata,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "outputs/actuator_dynamics_stress_search"
        ),
    )
    parser.add_argument(
        "--conditioning-s",
        type=float,
        default=7.5,
        help="Flat full-model launch used to generate restart states.",
    )
    parser.add_argument(
        "--onset-s",
        type=float,
        default=0.05,
        help="Common hold before each perturbation begins.",
    )
    parser.add_argument(
        "--hold-s",
        type=float,
        default=0.35,
        help="Post-ramp screening hold.",
    )
    parser.add_argument(
        "--screen-sample-step-s",
        type=float,
        default=0.002,
    )
    parser.add_argument(
        "--selected-sample-step-s",
        type=float,
        default=0.0005,
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=15,
        help="Maximum number of diverse candidates re-run with all four models.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Small smoke grid used by the installer.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
    )
    parser.add_argument("--rtol", type=float, default=1.0e-4)
    parser.add_argument("--atol", type=float, default=1.0e-7)
    return parser.parse_args()


def search_grid(args: argparse.Namespace):
    if args.quick:
        shift_percents = (50.0,)
        ramp_times = (0.025, 0.100)
        grade_targets = (-25.0, 25.0)
        secondary_torque_targets = (-60.0, 60.0)
        primary_torque_targets = (-15.0, 15.0)
    else:
        # Broad enough to resolve both the onset threshold and the slow-motion
        # limit without requiring a random search.
        shift_percents = (10.0, 30.0, 50.0, 70.0, 90.0)
        ramp_times = (
            0.005,
            0.010,
            0.025,
            0.050,
            0.100,
            0.250,
            0.500,
        )
        grade_targets = (
            -35.0,
            -25.0,
            -15.0,
            15.0,
            25.0,
            35.0,
        )
        # Positive external torque assists the positive secondary rotation;
        # negative torque is an added resisting load.
        secondary_torque_targets = (
            -120.0,
            -80.0,
            -40.0,
            -20.0,
            20.0,
            40.0,
            80.0,
            120.0,
        )
        # Diagnostic primary-boundary perturbations; ±20 N m is intentionally
        # aggressive relative to the small Baja engine.
        primary_torque_targets = (
            -20.0,
            -10.0,
            10.0,
            20.0,
        )

    return (
        shift_percents,
        ramp_times,
        grade_targets,
        secondary_torque_targets,
        primary_torque_targets,
    )


# ---------------------------------------------------------------------------
# Common flat conditioning trajectory / restart states
# ---------------------------------------------------------------------------


def flat_programme(duration_s: float) -> route.GradeProgramme:
    return route.GradeProgramme(
        (
            route.GradePhase(
                name="flat conditioning",
                start_s=0.0,
                end_s=duration_s,
                start_degrees=0.0,
                end_degrees=0.0,
                transition=False,
            ),
        )
    )


def build_standard_system(
    *,
    assembly,
    engine,
    road_load,
    constants,
    programme,
) -> ComposedCVTHybridSystem:
    return ab.build_system_from_assembly(
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
    )


def run_conditioning(
    *,
    variant,
    full_assembly,
    engine,
    road_load,
    constants,
    duration_s: float,
    args,
):
    """Run one actuator model naturally from the unchanged Baja baseline.

    No spring preload, geometry, inertia, engine, vehicle, or tuning parameter
    is modified to obtain restart states.  The only model difference is the
    actuator dynamic-vs-quasi-static ablation already defined by ``variant``.
    """

    programme = flat_programme(duration_s)
    assembly = ab.ablate_assembly(full_assembly, variant)
    system = build_standard_system(
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
    )
    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(
            secondary_shaft_angle=0.0
        ),
    )
    result = integrate_hybrid(
        system=system,
        time_span=(0.0, duration_s),
        initial_state=initial_full,
        initial_mode=system.classify_initial_mode(initial_full),
        settings=HybridIntegratorSettings(
            relative_tolerance=args.rtol,
            absolute_tolerance=args.atol,
            method="LSODA",
            max_step=0.005,
            maximum_transitions=220,
            retain_dense_output=True,
        ),
    )
    if not result.completed:
        raise RuntimeError(
            f"{variant.label} conditioning launch failed: "
            + result.termination_reason
        )

    samples, _ = ab.sample_variant(
        variant=variant,
        system=system,
        result=result,
        step_s=0.001,
    )
    return system, result, samples


def select_restart_states(
    *,
    variant,
    conditioning_system,
    samples,
    target_percents: Iterable[float],
) -> list[RestartState]:
    """Pick physical states reached naturally by this model at target shifts.

    This deliberately does NOT require one model's instantaneous state to be
    admissible under another model.  Each model is allowed to arrive at the
    requested ratio through its own baseline trajectory, because that is the
    physical trajectory predicted by that model.

    Comparisons of stress *response* are later made as a paired
    stress-minus-control difference for each model, so pre-existing baseline
    trajectory differences do not contaminate the perturbation effect.

    The selector also refuses to silently collapse several requested targets
    onto one state: every requested fraction must actually be traversed to
    within 0.75 percentage point and must use a distinct conditioning sample.
    """

    spec = conditioning_system.cvt.model.geometry.spec
    span = spec.max_shift - spec.deadzone_shift

    usable: list[tuple[object, float]] = []
    for sample in samples:
        if sample.closure is None:
            continue
        if sample.row.get("sample_location") != "interior":
            continue
        fraction = (
            (sample.cvt_state.shift_position - spec.deadzone_shift)
            / span
        )
        if not 0.01 < fraction < 0.99:
            continue
        usable.append((sample, 100.0 * fraction))

    if not usable:
        raise RuntimeError(
            f"{variant.label} conditioning trajectory produced no "
            "interior engaged samples."
        )

    achieved = [fraction for _, fraction in usable]
    achieved_min = min(achieved)
    achieved_max = max(achieved)
    selected: list[RestartState] = []
    used_times: set[float] = set()

    for target in target_percents:
        ordered = sorted(
            usable,
            key=lambda item: abs(item[1] - target),
        )
        chosen = next(
            (
                (sample, actual)
                for sample, actual in ordered
                if float(sample.time) not in used_times
            ),
            None,
        )
        if chosen is None:
            raise RuntimeError(
                f"{variant.label}: no distinct conditioning sample "
                f"available for target {target:.1f}%."
            )

        sample, actual = chosen
        error = abs(actual - float(target))
        if error > 0.75:
            raise RuntimeError(
                f"{variant.label} did not naturally reach requested "
                f"{target:.1f}% shift closely enough during the unchanged "
                f"{conditioning_system.cvt.model.geometry.spec.max_shift=}. "
                f"Nearest interior sample is {actual:.3f}% "
                f"(error {error:.3f} percentage points); conditioning "
                f"trajectory covered {achieved_min:.3f}% to "
                f"{achieved_max:.3f}%. Increase --conditioning-s if the "
                "trajectory simply has not reached the target yet. Do not "
                "change the physical tune to manufacture the state."
            )

        used_times.add(float(sample.time))
        state = sample.cvt_state
        selected.append(
            RestartState(
                variant_key=variant.key,
                key=f"s{int(round(target)):02d}",
                target_shift_percent=float(target),
                actual_shift_percent=float(actual),
                source_time_s=float(sample.time),
                full_state=np.array(
                    sample.full_state,
                    dtype=float,
                    copy=True,
                ),
                composed_mode=sample.composed_mode,
                primary_rpm=(
                    state.primary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                secondary_rpm=(
                    state.secondary_angular_speed
                    * RPM_PER_RADIAN_PER_SECOND
                ),
                shift_mm=state.shift_position / MILLIMETRE,
                shift_speed_mm_s=state.shift_speed / MILLIMETRE,
            )
        )

    return selected


def build_natural_restart_states(
    *,
    full_assembly,
    engine,
    road_load,
    constants,
    target_percents,
    duration_s: float,
    args,
):
    """Condition all four models on the same unchanged Baja baseline."""

    by_variant: dict[str, dict[str, RestartState]] = {}
    conditioning: dict[str, tuple[object, object, list[object]]] = {}

    print(
        "Building natural baseline restart states for all four "
        "actuator models..."
    )
    for variant in ab.VARIANTS:
        system, result, samples = run_conditioning(
            variant=variant,
            full_assembly=full_assembly,
            engine=engine,
            road_load=road_load,
            constants=constants,
            duration_s=duration_s,
            args=args,
        )
        states = select_restart_states(
            variant=variant,
            conditioning_system=system,
            samples=samples,
            target_percents=target_percents,
        )
        by_variant[variant.key] = {
            state.key: state for state in states
        }
        conditioning[variant.key] = (system, result, samples)

        print(f"  {variant.label}:")
        for state in states:
            print(
                f"    {state.target_shift_percent:5.1f}% target -> "
                f"{state.actual_shift_percent:7.3f}% actual at "
                f"t={state.source_time_s:.6f}s, "
                f"primary={state.primary_rpm:.1f} rpm"
            )

    return by_variant, conditioning


def restart_rows(states: list[RestartState]):
    rows = []
    for state in states:
        rows.append(
            {
                "variant": state.variant_key,
                "restart_key": state.key,
                "target_shift_percent": (
                    state.target_shift_percent
                ),
                "actual_shift_percent": (
                    state.actual_shift_percent
                ),
                "conditioning_time_s": state.source_time_s,
                "primary_rpm": state.primary_rpm,
                "secondary_rpm": state.secondary_rpm,
                "shift_mm": state.shift_mm,
                "shift_speed_mm_s": state.shift_speed_mm_s,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Stress-case construction
# ---------------------------------------------------------------------------


def build_candidates(
    *,
    restart_states: list[RestartState],
    ramp_times,
    grade_targets,
    secondary_torque_targets,
    primary_torque_targets,
    args,
) -> list[StressCandidate]:
    candidates: list[StressCandidate] = []
    index = 0
    for restart in restart_states:
        for ramp_s in ramp_times:
            for family, values in (
                ("grade", grade_targets),
                ("secondary_torque", secondary_torque_targets),
                ("primary_torque", primary_torque_targets),
            ):
                for amplitude in values:
                    index += 1
                    candidates.append(
                        StressCandidate(
                            case_id=f"C{index:04d}",
                            restart_key=restart.key,
                            restart_shift_percent=(
                                restart.target_shift_percent
                            ),
                            family=family,
                            amplitude=float(amplitude),
                            ramp_s=float(ramp_s),
                            onset_s=float(args.onset_s),
                            hold_s=float(args.hold_s),
                        )
                    )
    return candidates


def stress_programme(candidate: StressCandidate):
    if candidate.family == "grade":
        target = candidate.amplitude
    else:
        target = 0.0

    t0 = 0.0
    t1 = candidate.onset_s
    t2 = t1 + candidate.ramp_s
    t3 = candidate.duration_s
    return route.GradeProgramme(
        (
            route.GradePhase(
                name="pre-stress hold",
                start_s=t0,
                end_s=t1,
                start_degrees=0.0,
                end_degrees=0.0,
                transition=False,
            ),
            route.GradePhase(
                name="stress ramp",
                start_s=t1,
                end_s=t2,
                start_degrees=0.0,
                end_degrees=target,
                transition=True,
            ),
            route.GradePhase(
                name="stress hold",
                start_s=t2,
                end_s=t3,
                start_degrees=target,
                end_degrees=target,
                transition=False,
            ),
        )
    )


def build_stress_system(
    *,
    assembly,
    engine,
    road_load,
    constants,
    candidate: StressCandidate,
):
    programme = stress_programme(candidate)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    host = SecondaryShaftAngleHost()

    primary_boundary = FullThrottleEngineBoundary(
        engine,
        equivalent_rotational_inertia=(
            constants.engine_rotational_inertia
        ),
    )
    secondary_boundary = (
        route.TimeProgrammedLockedFinalDriveBoundary(
            road_load=road_load,
            programme=programme,
            direct_secondary_shaft_inertia=(
                constants.gearbox_input_rotational_inertia
            ),
        )
    )

    signal = SmoothStepSignal(
        onset_s=candidate.onset_s,
        ramp_s=candidate.ramp_s,
        target=candidate.amplitude,
    )
    if candidate.family == "primary_torque":
        primary_boundary = AddedTorqueBoundary(
            primary_boundary,
            signal,
        )
    elif candidate.family == "secondary_torque":
        secondary_boundary = AddedTorqueBoundary(
            secondary_boundary,
            signal,
        )

    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
        host=host,
    )
    return system, programme


def run_stress_variant(
    *,
    variant,
    candidate: StressCandidate,
    restart: RestartState,
    full_assembly,
    engine,
    road_load,
    constants,
    sample_step_s: float,
    args,
    screening: bool,
):
    assembly = ab.ablate_assembly(full_assembly, variant)
    system, programme = build_stress_system(
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        candidate=candidate,
    )

    if restart.variant_key != variant.key:
        raise RuntimeError(
            f"Restart {restart.key} belongs to {restart.variant_key}, "
            f"not requested variant {variant.key}."
        )

    initial_state = np.array(
        restart.full_state,
        dtype=float,
        copy=True,
    )
    # Preserve the exact active mode from this model's own interior baseline
    # trajectory. The stress signal is zero at t=0, so the boundary is
    # identical to the conditioning boundary at restart.
    initial_mode = restart.composed_mode

    # Resolve the shortest ramp with several genuine solver steps rather than
    # asking dense output to reconstruct a missed input transient.
    max_step = min(
        0.003 if screening else 0.001,
        max(0.00025, candidate.ramp_s / 5.0),
    )

    try:
        result = integrate_hybrid(
            system=system,
            time_span=(0.0, candidate.duration_s),
            initial_state=initial_state,
            initial_mode=initial_mode,
            settings=HybridIntegratorSettings(
                relative_tolerance=(
                    max(args.rtol, 3.0e-4)
                    if screening
                    else args.rtol
                ),
                absolute_tolerance=(
                    max(args.atol, 3.0e-7)
                    if screening
                    else args.atol
                ),
                method="LSODA",
                max_step=max_step,
                maximum_transitions=250,
                retain_dense_output=True,
            ),
        )
    except Exception as exc:
        return None, None, programme, f"{type(exc).__name__}: {exc}"

    if not result.completed:
        return (
            None,
            result,
            programme,
            result.termination_reason,
        )

    samples, contributions = ab.sample_variant(
        variant=variant,
        system=system,
        result=result,
        step_s=sample_step_s,
    )

    # Preserve stress inputs on every row for future post-processing.
    signal = SmoothStepSignal(
        onset_s=candidate.onset_s,
        ramp_s=candidate.ramp_s,
        target=candidate.amplitude,
    )
    for sample in samples:
        row = sample.row
        row["stress_case_id"] = candidate.case_id
        row["stress_family"] = candidate.family
        row["stress_amplitude"] = candidate.amplitude
        row["stress_ramp_s"] = candidate.ramp_s
        row["stress_onset_s"] = candidate.onset_s
        row["stress_restart_key"] = candidate.restart_key
        row["stress_restart_shift_percent"] = (
            candidate.restart_shift_percent
        )
        row["grade_deg"] = degrees(
            programme.grade_radians(sample.time)
        )
        row["stress_signal_fraction"] = (
            (
                signal.value(sample.time)
                / candidate.amplitude
            )
            if abs(candidate.amplitude) > 1.0e-12
            else 0.0
        )
        row["extra_primary_torque_Nm"] = (
            signal.value(sample.time)
            if candidate.family == "primary_torque"
            else 0.0
        )
        row["extra_secondary_torque_Nm"] = (
            signal.value(sample.time)
            if candidate.family == "secondary_torque"
            else 0.0
        )

    metrics = ab.compute_metrics(
        variant,
        result,
        samples,
        system.cvt.model.geometry.spec.max_shift,
    )
    return (
        ab.VariantResult(
            variant=variant,
            assembly=assembly,
            system=system,
            hybrid_result=result,
            samples=samples,
            contribution_rows=contributions,
            metrics=metrics,
        ),
        result,
        programme,
        None,
    )


# ---------------------------------------------------------------------------
# Screening metrics / classification
# ---------------------------------------------------------------------------


def _rows_after_onset(result, candidate):
    return [
        sample.row
        for sample in result.samples
        if sample.closure is not None
        and sample.time >= candidate.onset_s
    ]


def _finite(rows, key):
    values = np.asarray(
        [float(row.get(key, NAN)) for row in rows],
        dtype=float,
    )
    return values[np.isfinite(values)]


def _robust_fraction(
    numerator: np.ndarray,
    denominator: np.ndarray,
    *,
    floor: float,
):
    mask = np.isfinite(numerator) & np.isfinite(denominator)
    if not np.any(mask):
        return np.asarray([], dtype=float)
    den = np.maximum(np.abs(denominator[mask]), floor)
    return np.abs(numerator[mask]) / den


def classify_response(result, candidate):
    post = [
        record
        for record in result.hybrid_result.transitions
        if record.time >= candidate.onset_s
    ]
    reset_records = [
        record
        for record in post
        if record.transition.has_successor_state
    ]
    if reset_records:
        return "impact_reset"
    if post:
        return "contact_switching"
    return "clean_continuous"


def screen_metrics(
    *,
    candidate: StressCandidate,
    restart: RestartState,
    result,
):
    rows = _rows_after_onset(result, candidate)
    if not rows:
        raise RuntimeError("No engaged stress-window samples.")

    helix_delta = _finite(
        rows, "helix_dynamic_total_correction_N"
    )
    helix_qs = _finite(
        rows, "helix_qs_reaction_force_N"
    )
    fly_delta = _finite(
        rows, "fly_dynamic_total_correction_N"
    )
    fly_qs = _finite(
        rows, "fly_qs_centrifugal_force_N"
    )
    helix_shaft = _finite(
        rows,
        "helix_dynamic_shaft_torque_correction_vs_constant_Nm",
    )
    fly_shaft = _finite(
        rows,
        "fly_dynamic_shaft_torque_correction_vs_constant_Nm",
    )
    tau_s = _finite(rows, "tau_secondary_belt_Nm")
    tau_p = _finite(rows, "tau_primary_belt_Nm")
    sddot = _finite(
        rows, "rhs_shift_acceleration_m_s2"
    )
    shift = _finite(rows, "shift_m")
    shift_speed = _finite(rows, "shift_speed_m_s")

    # Same-state force-normalized effect sizes. Floors avoid declaring a
    # meaningless infinite percentage when a QS force happens to cross zero.
    n_helix = min(helix_delta.size, helix_qs.size)
    n_fly = min(fly_delta.size, fly_qs.size)
    hfrac = _robust_fraction(
        helix_delta[:n_helix],
        helix_qs[:n_helix],
        floor=500.0,
    )
    ffrac = _robust_fraction(
        fly_delta[:n_fly],
        fly_qs[:n_fly],
        floor=500.0,
    )

    n_hs = min(helix_shaft.size, tau_s.size)
    n_fs = min(fly_shaft.size, tau_p.size)
    hsfrac = _robust_fraction(
        helix_shaft[:n_hs],
        tau_s[:n_hs],
        floor=5.0,
    )
    fsfrac = _robust_fraction(
        fly_shaft[:n_fs],
        tau_p[:n_fs],
        floor=5.0,
    )

    spec = result.system.cvt.model.geometry.spec
    lower_margin = (
        float(np.min(shift - spec.deadzone_shift))
        if shift.size
        else NAN
    )
    upper_margin = (
        float(np.min(spec.max_shift - shift))
        if shift.size
        else NAN
    )

    classification = classify_response(result, candidate)
    helix_peak_fraction = (
        float(np.max(hfrac)) if hfrac.size else NAN
    )
    fly_peak_fraction = (
        float(np.max(ffrac)) if ffrac.size else NAN
    )
    helix_shaft_peak_fraction = (
        float(np.max(hsfrac)) if hsfrac.size else NAN
    )
    fly_shaft_peak_fraction = (
        float(np.max(fsfrac)) if fsfrac.size else NAN
    )

    # Ranking heuristic only; raw quantities are all saved. Axial clamp
    # correction receives the largest weight because it is the most directly
    # interpretable constitutive prediction difference.
    helix_score = (
        helix_peak_fraction
        + 0.25 * helix_shaft_peak_fraction
    )
    fly_score = (
        fly_peak_fraction
        + 0.25 * fly_shaft_peak_fraction
    )

    return {
        "case_id": candidate.case_id,
        "restart_key": restart.key,
        "restart_target_shift_percent": (
            restart.target_shift_percent
        ),
        "restart_actual_shift_percent": (
            restart.actual_shift_percent
        ),
        "restart_primary_rpm": restart.primary_rpm,
        "restart_secondary_rpm": restart.secondary_rpm,
        "restart_shift_mm": restart.shift_mm,
        "family": candidate.family,
        "amplitude": candidate.amplitude,
        "ramp_s": candidate.ramp_s,
        "onset_s": candidate.onset_s,
        "hold_s": candidate.hold_s,
        "response_class": classification,
        "transition_count_after_onset": sum(
            1
            for record in result.hybrid_result.transitions
            if record.time >= candidate.onset_s
        ),
        "reset_count_after_onset": sum(
            1
            for record in result.hybrid_result.transitions
            if record.time >= candidate.onset_s
            and record.transition.has_successor_state
        ),
        "minimum_lower_stop_margin_mm": (
            lower_margin / MILLIMETRE
        ),
        "minimum_upper_stop_margin_mm": (
            upper_margin / MILLIMETRE
        ),
        "peak_abs_shift_acceleration_m_s2": (
            float(np.max(np.abs(sddot)))
            if sddot.size else NAN
        ),
        "peak_abs_shift_speed_mm_s": (
            float(np.max(np.abs(shift_speed)))
            / MILLIMETRE
            if shift_speed.size else NAN
        ),
        "peak_abs_helix_dynamic_clamp_correction_N": (
            float(np.max(np.abs(helix_delta)))
            if helix_delta.size else NAN
        ),
        "p95_abs_helix_dynamic_clamp_correction_N": (
            float(np.percentile(np.abs(helix_delta), 95))
            if helix_delta.size else NAN
        ),
        "peak_helix_dynamic_clamp_fraction": (
            helix_peak_fraction
        ),
        "p95_helix_dynamic_clamp_fraction": (
            float(np.percentile(hfrac, 95))
            if hfrac.size else NAN
        ),
        "peak_abs_helix_shaft_torque_correction_Nm": (
            float(np.max(np.abs(helix_shaft)))
            if helix_shaft.size else NAN
        ),
        "peak_helix_shaft_torque_fraction": (
            helix_shaft_peak_fraction
        ),
        "peak_abs_flyweight_dynamic_clamp_correction_N": (
            float(np.max(np.abs(fly_delta)))
            if fly_delta.size else NAN
        ),
        "p95_abs_flyweight_dynamic_clamp_correction_N": (
            float(np.percentile(np.abs(fly_delta), 95))
            if fly_delta.size else NAN
        ),
        "peak_flyweight_dynamic_clamp_fraction": (
            fly_peak_fraction
        ),
        "p95_flyweight_dynamic_clamp_fraction": (
            float(np.percentile(ffrac, 95))
            if ffrac.size else NAN
        ),
        "peak_abs_flyweight_shaft_torque_correction_Nm": (
            float(np.max(np.abs(fly_shaft)))
            if fly_shaft.size else NAN
        ),
        "peak_flyweight_shaft_torque_fraction": (
            fly_shaft_peak_fraction
        ),
        "helix_direct_score": helix_score,
        "flyweight_direct_score": fly_score,
        "combined_direct_score": helix_score + fly_score,
        "status": "completed",
    }


def select_diverse_candidates(
    screening_rows,
    candidate_by_id,
    *,
    top_n: int,
):
    completed = [
        row for row in screening_rows
        if row.get("status") == "completed"
    ]
    selected_ids: list[str] = []

    def add_best(rows, key, count=1):
        candidates = [
            row for row in rows
            if isfinite(float(row.get(key, NAN)))
        ]
        candidates.sort(
            key=lambda row: float(row[key]),
            reverse=True,
        )
        added = 0
        for row in candidates:
            cid = row["case_id"]
            if cid in selected_ids:
                continue
            selected_ids.append(cid)
            added += 1
            if added >= count or len(selected_ids) >= top_n:
                break

    # Explicitly protect clean continuous cases from being drowned out by
    # impact/reset singularities.
    for response_class in (
        "clean_continuous",
        "contact_switching",
        "impact_reset",
    ):
        bucket = [
            row for row in completed
            if row["response_class"] == response_class
        ]
        add_best(bucket, "helix_direct_score", 2)
        add_best(bucket, "flyweight_direct_score", 1)
        add_best(bucket, "combined_direct_score", 1)

    # Ensure each excitation family is represented when it produced a
    # completed candidate.
    for family in (
        "grade",
        "secondary_torque",
        "primary_torque",
    ):
        bucket = [
            row for row in completed
            if row["family"] == family
        ]
        add_best(bucket, "combined_direct_score", 1)

    add_best(completed, "combined_direct_score", top_n)

    return [
        candidate_by_id[cid]
        for cid in selected_ids[:top_n]
    ]


# ---------------------------------------------------------------------------
# Pairwise trajectory divergence
# ---------------------------------------------------------------------------


def _series_for_interp(samples, key):
    pairs = []
    for sample in samples:
        value = float(sample.row.get(key, NAN))
        if not isfinite(value):
            continue
        pairs.append((float(sample.time), value))
    if not pairs:
        return (
            np.asarray([], dtype=float),
            np.asarray([], dtype=float),
        )

    # Retain the post-most sample at a duplicate hybrid boundary time. The
    # transition table preserves the exact pre/post jump separately.
    by_time: dict[float, float] = {}
    for time_s, value in pairs:
        by_time[time_s] = value
    times = np.asarray(sorted(by_time), dtype=float)
    values = np.asarray(
        [by_time[t] for t in times],
        dtype=float,
    )
    return times, values


def pairwise_metrics(
    *,
    candidate: StressCandidate,
    full: ab.VariantResult,
    other: ab.VariantResult,
    sample_step_s: float,
):
    start = candidate.onset_s
    end = min(
        full.hybrid_result.final_time,
        other.hybrid_result.final_time,
    )
    grid = np.arange(
        start,
        end + 0.5 * sample_step_s,
        sample_step_s,
    )

    metrics = {
        "case_id": candidate.case_id,
        "family": candidate.family,
        "amplitude": candidate.amplitude,
        "ramp_s": candidate.ramp_s,
        "restart_key": candidate.restart_key,
        "comparison_variant": other.variant.key,
        "comparison_label": other.variant.label,
    }

    fields = (
        ("shift_mm", "shift_mm"),
        ("shift_speed_mm_s", "shift_speed_mm_s"),
        ("primary_rpm", "primary_rpm"),
        ("secondary_rpm", "secondary_rpm"),
        (
            "rhs_shift_acceleration_m_s2",
            "shift_acceleration_m_s2",
        ),
        (
            "primary_actuator_closing_force_N",
            "primary_clamp_N",
        ),
        (
            "secondary_actuator_closing_force_N",
            "secondary_clamp_N",
        ),
        ("normal_primary_N", "normal_primary_N"),
        ("normal_secondary_N", "normal_secondary_N"),
        ("lambda_primary", "lambda_primary"),
        ("lambda_secondary", "lambda_secondary"),
    )

    for source_key, label in fields:
        ft, fv = _series_for_interp(
            full.samples,
            source_key,
        )
        ot, ov = _series_for_interp(
            other.samples,
            source_key,
        )
        if (
            ft.size < 2
            or ot.size < 2
            or grid.size == 0
        ):
            metrics[f"max_abs_delta_{label}"] = NAN
            metrics[f"rms_delta_{label}"] = NAN
            continue
        valid = (
            (grid >= max(ft[0], ot[0]))
            & (grid <= min(ft[-1], ot[-1]))
        )
        if not np.any(valid):
            metrics[f"max_abs_delta_{label}"] = NAN
            metrics[f"rms_delta_{label}"] = NAN
            continue
        g = grid[valid]
        delta = (
            np.interp(g, ot, ov)
            - np.interp(g, ft, fv)
        )
        metrics[f"max_abs_delta_{label}"] = float(
            np.max(np.abs(delta))
        )
        metrics[f"rms_delta_{label}"] = float(
            np.sqrt(np.mean(delta**2))
        )

    full_post = [
        r for r in full.hybrid_result.transitions
        if r.time >= start
    ]
    other_post = [
        r for r in other.hybrid_result.transitions
        if r.time >= start
    ]
    metrics["full_transition_count_after_onset"] = len(
        full_post
    )
    metrics["comparison_transition_count_after_onset"] = len(
        other_post
    )
    metrics["full_reset_count_after_onset"] = sum(
        r.transition.has_successor_state for r in full_post
    )
    metrics["comparison_reset_count_after_onset"] = sum(
        r.transition.has_successor_state for r in other_post
    )

    # Ranking heuristic only. Raw deltas remain the authoritative outputs.
    metrics["trajectory_divergence_score"] = (
        float(metrics.get("max_abs_delta_shift_mm", 0.0))
        / 0.10
        + float(
            metrics.get(
                "max_abs_delta_shift_speed_mm_s",
                0.0,
            )
        )
        / 10.0
        + float(
            metrics.get(
                "max_abs_delta_primary_rpm",
                0.0,
            )
        )
        / 25.0
        + float(
            metrics.get(
                "max_abs_delta_normal_secondary_N",
                0.0,
            )
        )
        / 250.0
    )
    return metrics


def paired_perturbation_metrics(
    *,
    candidate: StressCandidate,
    full_stress: ab.VariantResult,
    full_control: ab.VariantResult,
    other_stress: ab.VariantResult,
    other_control: ab.VariantResult,
    sample_step_s: float,
):
    """Difference-in-differences response to the imposed stress.

    Each model starts from its OWN natural baseline state at the requested
    shift fraction.  For each model first form

        response_m(t) = stressed_m(t) - control_m(t)

    and then compare

        response_other(t) - response_full(t).

    This removes ordinary baseline trajectory differences while preserving
    physically admissible model-specific starting states.
    """

    start = candidate.onset_s
    end = min(
        full_stress.hybrid_result.final_time,
        full_control.hybrid_result.final_time,
        other_stress.hybrid_result.final_time,
        other_control.hybrid_result.final_time,
    )
    grid = np.arange(
        start,
        end + 0.5 * sample_step_s,
        sample_step_s,
    )

    metrics = {
        "case_id": candidate.case_id,
        "family": candidate.family,
        "amplitude": candidate.amplitude,
        "ramp_s": candidate.ramp_s,
        "restart_key": candidate.restart_key,
        "restart_target_shift_percent": (
            candidate.restart_shift_percent
        ),
        "comparison_variant": other_stress.variant.key,
        "comparison_label": other_stress.variant.label,
        "comparison_method": (
            "(other_stress-other_control) - "
            "(full_stress-full_control)"
        ),
    }

    fields = (
        ("shift_mm", "shift_mm"),
        ("shift_speed_mm_s", "shift_speed_mm_s"),
        ("primary_rpm", "primary_rpm"),
        ("secondary_rpm", "secondary_rpm"),
        (
            "rhs_shift_acceleration_m_s2",
            "shift_acceleration_m_s2",
        ),
        (
            "primary_actuator_closing_force_N",
            "primary_clamp_N",
        ),
        (
            "secondary_actuator_closing_force_N",
            "secondary_clamp_N",
        ),
        ("normal_primary_N", "normal_primary_N"),
        ("normal_secondary_N", "normal_secondary_N"),
        ("lambda_primary", "lambda_primary"),
        ("lambda_secondary", "lambda_secondary"),
    )

    for source_key, label in fields:
        series = []
        valid_interval_start = start
        valid_interval_end = end
        for result in (
            full_stress,
            full_control,
            other_stress,
            other_control,
        ):
            times, values = _series_for_interp(
                result.samples,
                source_key,
            )
            series.append((times, values))
            if times.size:
                valid_interval_start = max(
                    valid_interval_start,
                    float(times[0]),
                )
                valid_interval_end = min(
                    valid_interval_end,
                    float(times[-1]),
                )

        if (
            grid.size == 0
            or any(times.size < 2 for times, _ in series)
            or valid_interval_end < valid_interval_start
        ):
            for prefix in (
                "max_abs_paired_delta_",
                "rms_paired_delta_",
                "max_abs_full_stress_response_",
                "max_abs_comparison_stress_response_",
            ):
                metrics[prefix + label] = NAN
            continue

        g = grid[
            (grid >= valid_interval_start)
            & (grid <= valid_interval_end)
        ]
        if g.size == 0:
            for prefix in (
                "max_abs_paired_delta_",
                "rms_paired_delta_",
                "max_abs_full_stress_response_",
                "max_abs_comparison_stress_response_",
            ):
                metrics[prefix + label] = NAN
            continue

        fs = np.interp(g, series[0][0], series[0][1])
        fc = np.interp(g, series[1][0], series[1][1])
        os = np.interp(g, series[2][0], series[2][1])
        oc = np.interp(g, series[3][0], series[3][1])

        full_response = fs - fc
        other_response = os - oc
        paired_delta = other_response - full_response

        metrics[f"max_abs_paired_delta_{label}"] = float(
            np.max(np.abs(paired_delta))
        )
        metrics[f"rms_paired_delta_{label}"] = float(
            np.sqrt(np.mean(paired_delta**2))
        )
        metrics[
            f"max_abs_full_stress_response_{label}"
        ] = float(np.max(np.abs(full_response)))
        metrics[
            f"max_abs_comparison_stress_response_{label}"
        ] = float(np.max(np.abs(other_response)))

    # Keep hybrid behavior explicit rather than folding discrete resets into
    # continuous response metrics.
    def counts(result):
        post = [
            record
            for record in result.hybrid_result.transitions
            if record.time >= start
        ]
        return (
            len(post),
            sum(
                record.transition.has_successor_state
                for record in post
            ),
        )

    fst, fsr = counts(full_stress)
    fct, fcr = counts(full_control)
    ost, osr = counts(other_stress)
    oct_, ocr = counts(other_control)

    metrics.update(
        {
            "full_stress_transition_count": fst,
            "full_control_transition_count": fct,
            "comparison_stress_transition_count": ost,
            "comparison_control_transition_count": oct_,
            "full_stress_reset_count": fsr,
            "full_control_reset_count": fcr,
            "comparison_stress_reset_count": osr,
            "comparison_control_reset_count": ocr,
        }
    )

    metrics["paired_trajectory_divergence_score"] = (
        float(
            metrics.get(
                "max_abs_paired_delta_shift_mm",
                0.0,
            )
        )
        / 0.10
        + float(
            metrics.get(
                "max_abs_paired_delta_shift_speed_mm_s",
                0.0,
            )
        )
        / 10.0
        + float(
            metrics.get(
                "max_abs_paired_delta_primary_rpm",
                0.0,
            )
        )
        / 25.0
        + float(
            metrics.get(
                "max_abs_paired_delta_normal_secondary_N",
                0.0,
            )
        )
        / 250.0
    )
    # Compatibility aliases intentionally point to the PAIRED
    # difference-in-differences quantities. Existing overview/summary helpers
    # can therefore keep their field names without accidentally reporting raw
    # baseline offsets between actuator models.
    for label in (
        "shift_mm",
        "shift_speed_mm_s",
        "primary_rpm",
        "secondary_rpm",
        "shift_acceleration_m_s2",
        "primary_clamp_N",
        "secondary_clamp_N",
        "normal_primary_N",
        "normal_secondary_N",
        "lambda_primary",
        "lambda_secondary",
    ):
        metrics[f"max_abs_delta_{label}"] = metrics.get(
            f"max_abs_paired_delta_{label}",
            NAN,
        )
        metrics[f"rms_delta_{label}"] = metrics.get(
            f"rms_paired_delta_{label}",
            NAN,
        )
    metrics["trajectory_divergence_score"] = metrics[
        "paired_trajectory_divergence_score"
    ]

    return metrics


def paired_stress_response_plot(
    *,
    candidate: StressCandidate,
    stress_by_key,
    control_by_key,
    output_dir: Path,
    sample_step_s: float,
):
    """Plot stress-minus-control response for all four models."""

    full_stress = stress_by_key["full"]
    full_control = control_by_key["full"]
    start = candidate.onset_s
    end = min(
        result.hybrid_result.final_time
        for result in (
            *stress_by_key.values(),
            *control_by_key.values(),
        )
    )
    grid = np.arange(
        start,
        end + 0.5 * sample_step_s,
        sample_step_s,
    )

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(10.5, 10.0),
        sharex=True,
        constrained_layout=True,
    )

    fields = (
        ("shift_mm", axes[0], "Stress-induced shift [mm]"),
        ("primary_rpm", axes[1], "Stress-induced primary speed [rpm]"),
        (
            "secondary_actuator_closing_force_N",
            axes[2],
            "Stress-induced secondary clamp [N]",
        ),
        (
            "normal_secondary_N",
            axes[3],
            r"Stress-induced $N_s$ [N]",
        ),
    )

    for variant in ab.VARIANTS:
        stress = stress_by_key[variant.key]
        control = control_by_key[variant.key]
        for source_key, axis, ylabel in fields:
            st, sv = _series_for_interp(stress.samples, source_key)
            ct, cv = _series_for_interp(control.samples, source_key)
            if st.size < 2 or ct.size < 2:
                continue
            valid = (
                (grid >= max(st[0], ct[0]))
                & (grid <= min(st[-1], ct[-1]))
            )
            g = grid[valid]
            if not g.size:
                continue
            response = (
                np.interp(g, st, sv)
                - np.interp(g, ct, cv)
            )
            axis.plot(
                g - start,
                response,
                label=variant.label,
            )
            axis.set_ylabel(ylabel)

    axes[0].set_title(
        f"{candidate.case_id}: paired stress-minus-control response "
        f"from natural {candidate.restart_shift_percent:.0f}% "
        "baseline states"
    )
    axes[-1].set_xlabel("Time since stress onset [s]")
    for axis in axes:
        axis.axhline(0.0, linewidth=0.8)
        axis.grid(True, alpha=0.25)
    axes[0].legend(fontsize=8)

    fig.savefig(
        output_dir / "12_paired_stress_response.png",
        dpi=180,
    )
    plt.close(fig)




# ---------------------------------------------------------------------------
# Stress-specific plots for selected cases
# ---------------------------------------------------------------------------


def _array(rows, key):
    return np.asarray(
        [float(row.get(key, NAN)) for row in rows],
        dtype=float,
    )


def _stress_input_series(rows, candidate):
    if candidate.family == "grade":
        return _array(rows, "grade_deg"), "Grade [deg]"
    if candidate.family == "secondary_torque":
        return (
            _array(rows, "extra_secondary_torque_Nm"),
            "Added secondary torque [N m]",
        )
    return (
        _array(rows, "extra_primary_torque_Nm"),
        "Added primary torque [N m]",
    )


def selected_case_plots(
    *,
    candidate: StressCandidate,
    results: list[ab.VariantResult],
    direct_rows,
    output_dir: Path,
):
    full = next(
        item for item in results
        if item.variant.key == "full"
    )
    full_rows = [
        sample.row for sample in full.samples
    ]
    t_full = _array(full_rows, "time_s")
    input_values, input_label = _stress_input_series(
        full_rows,
        candidate,
    )

    fig1, axes = plt.subplots(
        4,
        1,
        figsize=(10.5, 10.0),
        sharex=True,
        constrained_layout=True,
    )
    axes[0].plot(t_full, input_values)
    axes[0].set_ylabel(input_label)
    axes[0].set_title(
        f"{candidate.case_id}: direct dynamic terms on the full trajectory"
    )
    axes[1].plot(
        t_full,
        _array(
            full_rows,
            "helix_dynamic_total_correction_N",
        ),
        label="helix total dynamic clamp correction",
    )
    axes[1].plot(
        t_full,
        _array(
            full_rows,
            "fly_dynamic_total_correction_N",
        ),
        label="flyweight total dynamic clamp correction",
    )
    axes[1].set_ylabel("Dynamic clamp correction [N]")
    axes[1].legend(fontsize=8)
    axes[2].plot(
        t_full,
        _array(
            full_rows,
            "helix_dynamic_shaft_torque_correction_vs_constant_Nm",
        ),
        label="helix shaft correction",
    )
    axes[2].plot(
        t_full,
        _array(
            full_rows,
            "fly_dynamic_shaft_torque_correction_vs_constant_Nm",
        ),
        label="flyweight shaft correction",
    )
    axes[2].set_ylabel("Shaft correction [N m]")
    axes[2].legend(fontsize=8)
    axes[3].plot(
        t_full,
        _array(
            full_rows,
            "rhs_shift_acceleration_m_s2",
        ),
    )
    axes[3].set_ylabel(r"$\ddot{s}$ [m/s$^2$]")
    axes[3].set_xlabel("Restart time [s]")
    for ax in axes:
        ax.axvspan(
            candidate.onset_s,
            candidate.onset_s + candidate.ramp_s,
            alpha=0.12,
        )
        ax.grid(True, alpha=0.25)
    fig1.savefig(
        output_dir / "09_stress_direct_terms.png",
        dpi=180,
    )

    fig2, axes2 = plt.subplots(
        4,
        1,
        figsize=(10.5, 10.0),
        sharex=True,
        constrained_layout=True,
    )
    for item in results:
        rows = [sample.row for sample in item.samples]
        t = _array(rows, "time_s")
        axes2[0].plot(
            t,
            _array(rows, "primary_rpm"),
            label=item.variant.label,
        )
        axes2[1].plot(
            t,
            _array(rows, "shift_mm"),
            label=item.variant.label,
        )
        axes2[2].plot(
            t,
            _array(
                rows,
                "secondary_actuator_closing_force_N",
            ),
            label=item.variant.label,
        )
        axes2[3].plot(
            t,
            _array(rows, "normal_secondary_N"),
            label=item.variant.label,
        )
    axes2[0].set_ylabel("Primary rpm")
    axes2[0].set_title(
        f"{candidate.case_id}: trajectory consequence"
    )
    axes2[1].set_ylabel("Shift [mm]")
    axes2[2].set_ylabel("Secondary clamp [N]")
    axes2[3].set_ylabel(r"$N_s$ [N]")
    axes2[3].set_xlabel("Restart time [s]")
    for ax in axes2:
        ax.axvspan(
            candidate.onset_s,
            candidate.onset_s + candidate.ramp_s,
            alpha=0.12,
        )
        ax.grid(True, alpha=0.25)
    axes2[0].legend(fontsize=8)
    fig2.savefig(
        output_dir / "10_stress_trajectory_consequence.png",
        dpi=180,
    )

    # Same-state direct force comparison.
    if direct_rows:
        td = _array(direct_rows, "time_s")
        fig3, axes3 = plt.subplots(
            2,
            1,
            figsize=(10.5, 7.0),
            sharex=True,
            constrained_layout=True,
        )
        axes3[0].plot(
            td,
            _array(
                direct_rows,
                "primary_total_clamp__full_N",
            ),
            label="full",
        )
        axes3[0].plot(
            td,
            _array(
                direct_rows,
                "primary_total_clamp__quasi_static_flyweight_N",
            ),
            linestyle="--",
            label="QS flyweight",
        )
        axes3[0].set_ylabel("Primary clamp [N]")
        axes3[0].legend()
        axes3[1].plot(
            td,
            _array(
                direct_rows,
                "secondary_total_clamp__full_N",
            ),
            label="full",
        )
        axes3[1].plot(
            td,
            _array(
                direct_rows,
                "secondary_total_clamp__quasi_static_helix_N",
            ),
            linestyle="--",
            label="QS helix",
        )
        axes3[1].set_ylabel("Secondary clamp [N]")
        axes3[1].set_xlabel("Restart time [s]")
        axes3[1].legend()
        for ax in axes3:
            ax.axvspan(
                candidate.onset_s,
                candidate.onset_s + candidate.ramp_s,
                alpha=0.12,
            )
            ax.grid(True, alpha=0.25)
        fig3.suptitle(
            f"{candidate.case_id}: direct same-state clamp prediction"
        )
        fig3.savefig(
            output_dir / "11_stress_same_state_clamp.png",
            dpi=180,
        )

    plt.close("all")


# ---------------------------------------------------------------------------
# Global output / overview
# ---------------------------------------------------------------------------


def make_global_overview(
    *,
    screening_rows,
    pairwise_rows,
    output_dir: Path,
):
    complete = [
        row for row in screening_rows
        if row.get("status") == "completed"
    ]
    complete.sort(
        key=lambda row: float(
            row.get("combined_direct_score", -np.inf)
        ),
        reverse=True,
    )
    top = complete[:20]

    if top:
        labels = [
            (
                f"{row['case_id']} "
                f"{row['family']} "
                f"{row['amplitude']:+g}, "
                f"{1000*row['ramp_s']:.0f}ms, "
                f"s={row['restart_actual_shift_percent']:.0f}%"
            )
            for row in top
        ]
        x = np.arange(len(top))
        fig, ax = plt.subplots(
            figsize=(11.5, 8.5),
            constrained_layout=True,
        )
        ax.barh(
            x,
            [
                100.0
                * float(
                    row[
                        "peak_helix_dynamic_clamp_fraction"
                    ]
                )
                for row in top
            ],
            label="helix",
        )
        ax.barh(
            x,
            [
                100.0
                * float(
                    row[
                        "peak_flyweight_dynamic_clamp_fraction"
                    ]
                )
                for row in top
            ],
            left=[
                100.0
                * float(
                    row[
                        "peak_helix_dynamic_clamp_fraction"
                    ]
                )
                for row in top
            ],
            label="flyweight",
        )
        ax.set_yticks(x)
        ax.set_yticklabels(labels, fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel(
            "Peak direct dynamic clamp correction / QS clamp floor [%]"
        )
        ax.set_title(
            "Stress-screen ranking by direct actuator-dynamics correction"
        )
        ax.legend()
        ax.grid(True, axis="x", alpha=0.25)
        fig.savefig(
            output_dir / "00_screening_top_direct_effects.png",
            dpi=180,
        )
        plt.close(fig)

    if pairwise_rows:
        rows = [
            row
            for row in pairwise_rows
            if row["comparison_variant"]
            in (
                "quasi_static_flyweight",
                "quasi_static_helix",
                "fully_quasi_static",
            )
        ]
        rows.sort(
            key=lambda row: float(
                row.get(
                    "trajectory_divergence_score",
                    -np.inf,
                )
            ),
            reverse=True,
        )
        top_p = rows[:20]
        labels = [
            f"{r['case_id']} / {r['comparison_label']}"
            for r in top_p
        ]
        fig, ax = plt.subplots(
            figsize=(11.0, 8.0),
            constrained_layout=True,
        )
        y = np.arange(len(top_p))
        ax.barh(
            y,
            [
                float(
                    r.get(
                        "trajectory_divergence_score",
                        0.0,
                    )
                )
                for r in top_p
            ],
        )
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel(
            "Heuristic trajectory-divergence score"
        )
        ax.set_title(
            "Selected stress cases: largest trajectory consequences"
        )
        ax.grid(True, axis="x", alpha=0.25)
        fig.savefig(
            output_dir
            / "00_validation_top_trajectory_effects.png",
            dpi=180,
        )
        plt.close(fig)


def write_human_summary(
    *,
    screening_rows,
    pairwise_rows,
    selected_rows,
    output_dir: Path,
) -> None:
    completed = [
        row
        for row in screening_rows
        if row.get("status") == "completed"
    ]

    lines = [
        "ACTUATOR DYNAMICS STRESS SEARCH — MACHINE SUMMARY",
        "=" * 68,
        "",
        (
            "This file is a numerical locator, not a final scientific "
            "interpretation. Upload the full output directory for analysis."
        ),
        "",
    ]

    def best_rows(response_class, score_key, count=3):
        rows = [
            row
            for row in completed
            if (
                response_class is None
                or row.get("response_class") == response_class
            )
            and isfinite(float(row.get(score_key, NAN)))
        ]
        rows.sort(
            key=lambda row: float(row[score_key]),
            reverse=True,
        )
        return rows[:count]

    for title, response_class in (
        ("CLEAN CONTINUOUS", "clean_continuous"),
        ("CONTACT SWITCHING", "contact_switching"),
        ("IMPACT / RESET", "impact_reset"),
    ):
        lines.extend([title, "-" * len(title)])
        for score_key, label in (
            ("helix_direct_score", "helix"),
            ("flyweight_direct_score", "flyweight"),
        ):
            best = best_rows(response_class, score_key, 2)
            if not best:
                lines.append(f"  {label}: no completed cases")
                continue
            lines.append(f"  strongest {label} direct cases:")
            for row in best:
                lines.append(
                    "    "
                    f"{row['case_id']} | {row['family']} "
                    f"{float(row['amplitude']):+g} | "
                    f"{1000.0*float(row['ramp_s']):.1f} ms | "
                    f"restart {float(row['restart_actual_shift_percent']):.1f}% | "
                    f"helix clamp Δ={100.0*float(row.get('peak_helix_dynamic_clamp_fraction', NAN)):.3g}% | "
                    f"fly clamp Δ={100.0*float(row.get('peak_flyweight_dynamic_clamp_fraction', NAN)):.3g}% | "
                    f"peak |sddot|={float(row.get('peak_abs_shift_acceleration_m_s2', NAN)):.4g} m/s²"
                )
        lines.append("")

    if pairwise_rows:
        ordered = sorted(
            pairwise_rows,
            key=lambda row: float(
                row.get("trajectory_divergence_score", -np.inf)
            ),
            reverse=True,
        )
        lines.extend(
            [
                "LARGEST SELECTED-CASE TRAJECTORY DIVERGENCES",
                "-" * 45,
            ]
        )
        for row in ordered[:10]:
            lines.append(
                "  "
                f"{row['case_id']} vs {row['comparison_label']} | "
                f"Δs={float(row.get('max_abs_delta_shift_mm', NAN)):.4g} mm | "
                f"Δsdot={float(row.get('max_abs_delta_shift_speed_mm_s', NAN)):.4g} mm/s | "
                f"Δrpm_p={float(row.get('max_abs_delta_primary_rpm', NAN)):.4g} rpm | "
                f"ΔNs={float(row.get('max_abs_delta_normal_secondary_N', NAN)):.4g} N | "
                f"score={float(row.get('trajectory_divergence_score', NAN)):.4g}"
            )
        lines.append("")

    lines.extend(
        [
            "FILES TO UPLOAD FOR INTERPRETATION",
            "-" * 34,
            "  screening_candidates.csv",
            "  validation_pairwise_vs_full.csv",
            "  validation_variant_summary.csv",
            "  restart_states.csv",
            "  stress_test_manifest.json",
            "  selected_cases/*  (entire directories)",
            "",
        ]
    )

    (output_dir / "stress_test_summary.txt").write_text(
        "\\n".join(lines) + "\\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    if args.top_n < 1:
        raise ValueError("--top-n must be at least one.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected_root = args.output_dir / "selected_cases"
    selected_root.mkdir(parents=True, exist_ok=True)

    preset = (
        HERE
        / "presets"
        / "circular_traction_first_reference.json"
    )
    tune_candidate = route.load_candidate(preset)
    conditioning_programme = flat_programme(
        args.conditioning_s
    )
    resolved = route.resolve_primary_preload(
        tune_candidate,
        target_engagement_rpm=2000.0,
        programme=conditioning_programme,
    )
    full_assembly, engine, road_load = route.build_components(
        resolved.constants
    )

    (
        shift_percents,
        ramp_times,
        grade_targets,
        secondary_torque_targets,
        primary_torque_targets,
    ) = search_grid(args)

    restart_by_variant, conditioning_by_variant = (
        build_natural_restart_states(
            full_assembly=full_assembly,
            engine=engine,
            road_load=road_load,
            constants=resolved.constants,
            target_percents=shift_percents,
            duration_s=args.conditioning_s,
            args=args,
        )
    )

    all_restart_states = [
        state
        for variant in ab.VARIANTS
        for state in restart_by_variant[variant.key].values()
    ]
    ab._write_dict_rows(
        args.output_dir / "restart_states.csv",
        restart_rows(all_restart_states),
    )

    # The full-model natural baseline defines the physical screening points.
    # The same target fractions are later validated with each ablated model's
    # own natural baseline state plus a paired no-stress control.
    full_restart_states = [
        restart_by_variant["full"][
            f"s{int(round(target)):02d}"
        ]
        for target in shift_percents
    ]

    candidates = build_candidates(
        restart_states=full_restart_states,
        ramp_times=ramp_times,
        grade_targets=grade_targets,
        secondary_torque_targets=secondary_torque_targets,
        primary_torque_targets=primary_torque_targets,
        args=args,
    )
    candidate_by_id = {
        candidate.case_id: candidate
        for candidate in candidates
    }

    print(
        f"Screening {len(candidates)} finite stress cases "
        "with the full dynamic model..."
    )
    screening_rows: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates, start=1):
        restart = restart_by_variant["full"][candidate.restart_key]
        result, raw, programme, error = run_stress_variant(
            variant=ab.VARIANTS[0],
            candidate=candidate,
            restart=restart,
            full_assembly=full_assembly,
            engine=engine,
            road_load=road_load,
            constants=resolved.constants,
            sample_step_s=args.screen_sample_step_s,
            args=args,
            screening=True,
        )
        if result is None:
            screening_rows.append(
                {
                    "case_id": candidate.case_id,
                    "restart_key": candidate.restart_key,
                    "restart_actual_shift_percent": (
                        candidate.restart_shift_percent
                    ),
                    "family": candidate.family,
                    "amplitude": candidate.amplitude,
                    "ramp_s": candidate.ramp_s,
                    "status": "failed",
                    "error": error,
                }
            )
        else:
            try:
                screening_rows.append(
                    screen_metrics(
                        candidate=candidate,
                        restart=restart,
                        result=result,
                    )
                )
            except Exception as exc:
                screening_rows.append(
                    {
                        "case_id": candidate.case_id,
                        "restart_key": candidate.restart_key,
                        "family": candidate.family,
                        "amplitude": candidate.amplitude,
                        "ramp_s": candidate.ramp_s,
                        "status": "analysis_failed",
                        "error": (
                            f"{type(exc).__name__}: {exc}"
                        ),
                    }
                )

        if index % max(1, len(candidates) // 20) == 0:
            print(
                f"  screened {index}/{len(candidates)}"
            )

    screening_rows.sort(
        key=lambda row: (
            0
            if row.get("status") == "completed"
            else 1,
            -float(
                row.get(
                    "combined_direct_score",
                    -np.inf,
                )
            )
            if row.get("status") == "completed"
            else 0.0,
        )
    )
    ab._write_dict_rows(
        args.output_dir / "screening_candidates.csv",
        screening_rows,
    )

    selected = select_diverse_candidates(
        screening_rows,
        candidate_by_id,
        top_n=args.top_n,
    )
    (args.output_dir / "selected_cases.json").write_text(
        json.dumps(
            [asdict(item) for item in selected],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Re-running {len(selected)} selected cases with all "
        "four actuator models at high resolution..."
    )

    validation_variant_rows: list[dict[str, Any]] = []
    # Primary comparison: paired stress-minus-control difference-in-differences.
    validation_pairwise_rows: list[dict[str, Any]] = []
    validation_raw_pairwise_rows: list[dict[str, Any]] = []
    selected_case_summary_rows: list[dict[str, Any]] = []

    for selected_index, candidate in enumerate(
        selected,
        start=1,
    ):
        case_dir = (
            selected_root
            / (
                f"{selected_index:02d}_{candidate.case_id}_"
                f"{candidate.family}"
            )
        )
        case_dir.mkdir(parents=True, exist_ok=True)

        stress_results: list[ab.VariantResult] = []
        control_results: list[ab.VariantResult] = []
        errors: list[dict[str, Any]] = []

        # The control has the same horizon, ramp timing and input family but
        # zero amplitude. It begins from the exact same natural baseline state
        # as that variant's stressed run.
        control_candidate = replace(
            candidate,
            case_id=f"{candidate.case_id}_CONTROL",
            amplitude=0.0,
        )

        for variant in ab.VARIANTS:
            restart = restart_by_variant[variant.key][
                candidate.restart_key
            ]

            stress, raw, programme, stress_error = run_stress_variant(
                variant=variant,
                candidate=candidate,
                restart=restart,
                full_assembly=full_assembly,
                engine=engine,
                road_load=road_load,
                constants=resolved.constants,
                sample_step_s=args.selected_sample_step_s,
                args=args,
                screening=False,
            )
            control, control_raw, control_programme, control_error = (
                run_stress_variant(
                    variant=variant,
                    candidate=control_candidate,
                    restart=restart,
                    full_assembly=full_assembly,
                    engine=engine,
                    road_load=road_load,
                    constants=resolved.constants,
                    sample_step_s=args.selected_sample_step_s,
                    args=args,
                    screening=False,
                )
            )

            if stress is None or control is None:
                errors.append(
                    {
                        "variant": variant.key,
                        "stress_error": stress_error,
                        "control_error": control_error,
                    }
                )
                continue

            stress_results.append(stress)
            control_results.append(control)
            row = dict(stress.metrics)
            row.update(
                {
                    "case_id": candidate.case_id,
                    "selected_index": selected_index,
                    "family": candidate.family,
                    "amplitude": candidate.amplitude,
                    "ramp_s": candidate.ramp_s,
                    "restart_key": candidate.restart_key,
                    "restart_target_shift_percent": (
                        candidate.restart_shift_percent
                    ),
                    "restart_actual_shift_percent": (
                        restart.actual_shift_percent
                    ),
                    "restart_conditioning_time_s": (
                        restart.source_time_s
                    ),
                    "response_class": classify_response(
                        stress,
                        candidate,
                    ),
                    "control_response_class": classify_response(
                        control,
                        control_candidate,
                    ),
                }
            )
            validation_variant_rows.append(row)

        stress_by_key = {
            result.variant.key: result
            for result in stress_results
        }
        control_by_key = {
            result.variant.key: result
            for result in control_results
        }

        (case_dir / "case_manifest.json").write_text(
            json.dumps(
                {
                    "selected_index": selected_index,
                    "candidate": asdict(candidate),
                    "restart_by_variant": {
                        variant.key: {
                            "variant_key": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].variant_key,
                            "restart_key": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].key,
                            "target_shift_percent": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].target_shift_percent,
                            "actual_shift_percent": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].actual_shift_percent,
                            "conditioning_time_s": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].source_time_s,
                            "primary_rpm": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].primary_rpm,
                            "secondary_rpm": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].secondary_rpm,
                            "shift_mm": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].shift_mm,
                            "shift_speed_mm_s": restart_by_variant[
                                variant.key
                            ][candidate.restart_key].shift_speed_mm_s,
                        }
                        for variant in ab.VARIANTS
                    },
                    "comparison_design": (
                        "Each actuator model starts from its own natural "
                        "unchanged-baseline state at the requested shift "
                        "fraction. A paired zero-amplitude control is run from "
                        "the exact same state. Primary trajectory comparisons "
                        "are difference-in-differences: "
                        "(QS_stress-QS_control)-(full_stress-full_control)."
                    ),
                    "errors": errors,
                },
                indent=2,
                default=lambda value: (
                    value.tolist()
                    if isinstance(value, np.ndarray)
                    else str(value)
                ),
            )
            + "\n",
            encoding="utf-8",
        )

        if (
            "full" not in stress_by_key
            or "full" not in control_by_key
        ):
            continue

        full_stress = stress_by_key["full"]
        full_control = control_by_key["full"]

        pair_rows = []
        raw_pair_rows = []
        for variant in ab.VARIANTS:
            if variant.key == "full":
                continue
            if (
                variant.key not in stress_by_key
                or variant.key not in control_by_key
            ):
                continue

            pair = paired_perturbation_metrics(
                candidate=candidate,
                full_stress=full_stress,
                full_control=full_control,
                other_stress=stress_by_key[variant.key],
                other_control=control_by_key[variant.key],
                sample_step_s=args.selected_sample_step_s,
            )
            pair["selected_index"] = selected_index
            pair_rows.append(pair)
            validation_pairwise_rows.append(pair)

            # Raw stressed-trajectory differences are retained only as a
            # secondary diagnostic. They include natural baseline offsets and
            # are not the primary stress-response comparison.
            raw = pairwise_metrics(
                candidate=candidate,
                full=full_stress,
                other=stress_by_key[variant.key],
                sample_step_s=args.selected_sample_step_s,
            )
            raw["selected_index"] = selected_index
            raw["comparison_method"] = (
                "raw stressed trajectories; includes baseline offsets"
            )
            raw_pair_rows.append(raw)
            validation_raw_pairwise_rows.append(raw)

        ab._write_dict_rows(
            case_dir / "paired_response_vs_full.csv",
            pair_rows,
        )
        ab._write_dict_rows(
            case_dir / "raw_stressed_pairwise_vs_full.csv",
            raw_pair_rows,
        )
        screen_for_case = next(
            (
                row
                for row in screening_rows
                if row.get("case_id") == candidate.case_id
            ),
            {},
        )
        (case_dir / "screening_metrics.json").write_text(
            json.dumps(
                screen_for_case,
                indent=2,
                allow_nan=True,
            )
            + "\n",
            encoding="utf-8",
        )

        # Direct same-state actuator prediction remains evaluated on the FULL
        # stressed trajectory. This is the constitutive/mechanism comparison
        # and is intentionally separate from paired trajectory response.
        if (
            len(stress_results) == 4
            and len(control_results) == 4
        ):
            direct_rows, counterfactual = (
                ab.direct_prediction_on_full_trajectory(
                    stress_results
                )
            )
            mass_rows = ab.effective_mass_map(stress_results)
            ab.write_outputs(
                results=stress_results,
                direct_rows=direct_rows,
                counterfactual_contrib=counterfactual,
                mass_rows=mass_rows,
                candidate=tune_candidate,
                constants=resolved.constants,
                sample_step_s=(
                    args.selected_sample_step_s
                ),
                output_dir=case_dir,
                no_show=True,
            )
            selected_case_plots(
                candidate=candidate,
                results=stress_results,
                direct_rows=direct_rows,
                output_dir=case_dir,
            )
            paired_stress_response_plot(
                candidate=candidate,
                stress_by_key=stress_by_key,
                control_by_key=control_by_key,
                output_dir=case_dir,
                sample_step_s=args.selected_sample_step_s,
            )

            ab._write_dict_rows(
                case_dir / "control_trajectory_diagnostics.csv",
                [
                    sample.row
                    for item in control_results
                    for sample in item.samples
                ],
            )
            ab._write_dict_rows(
                case_dir / "control_hybrid_transitions.csv",
                [
                    row
                    for item in control_results
                    for row in ab.transition_rows(item)
                ],
            )
        else:
            direct_rows = []
            ab._write_dict_rows(
                case_dir / "trajectory_diagnostics.csv",
                [
                    sample.row
                    for item in stress_results
                    for sample in item.samples
                ],
            )
            ab._write_dict_rows(
                case_dir / "control_trajectory_diagnostics.csv",
                [
                    sample.row
                    for item in control_results
                    for sample in item.samples
                ],
            )

        screen_row = next(
            (
                row for row in screening_rows
                if row.get("case_id") == candidate.case_id
            ),
            {},
        )
        selected_case_summary_rows.append(
            {
                "selected_index": selected_index,
                "case_id": candidate.case_id,
                "family": candidate.family,
                "amplitude": candidate.amplitude,
                "ramp_s": candidate.ramp_s,
                "restart_key": candidate.restart_key,
                "restart_shift_percent": (
                    candidate.restart_shift_percent
                ),
                "screen_response_class": screen_row.get(
                    "response_class"
                ),
                "screen_peak_helix_dynamic_clamp_fraction": (
                    screen_row.get(
                        "peak_helix_dynamic_clamp_fraction"
                    )
                ),
                "screen_peak_flyweight_dynamic_clamp_fraction": (
                    screen_row.get(
                        "peak_flyweight_dynamic_clamp_fraction"
                    )
                ),
                "screen_peak_abs_shift_acceleration_m_s2": (
                    screen_row.get(
                        "peak_abs_shift_acceleration_m_s2"
                    )
                ),
                "max_paired_trajectory_divergence_score": (
                    max(
                        (
                            float(
                                row[
                                    "trajectory_divergence_score"
                                ]
                            )
                            for row in pair_rows
                        ),
                        default=NAN,
                    )
                ),
                "all_four_completed": (
                    len(stress_results) == 4
                    and len(control_results) == 4
                ),
            }
        )

        print(
            f"  selected {selected_index}/{len(selected)}: "
            f"{candidate.case_id} {candidate.family} "
            f"{candidate.amplitude_label}, "
            f"{1000*candidate.ramp_s:.0f} ms, "
            f"restart={candidate.restart_shift_percent:.1f}%"
        )

    ab._write_dict_rows(
        args.output_dir / "validation_variant_summary.csv",
        validation_variant_rows,
    )
    ab._write_dict_rows(
        args.output_dir / "validation_pairwise_vs_full.csv",
        validation_pairwise_rows,
    )
    ab._write_dict_rows(
        args.output_dir / "validation_raw_stressed_pairwise_vs_full.csv",
        validation_raw_pairwise_rows,
    )
    ab._write_dict_rows(
        args.output_dir / "selected_case_summary.csv",
        selected_case_summary_rows,
    )

    manifest = {
        "study": "actuator_dynamics_stress_search_natural_baseline_paired",
        "purpose": (
            "Search for direct and trajectory impacts of dynamic "
            "flyweight/helix mechanics while preserving the unchanged Baja "
            "baseline. Each model is conditioned naturally to each requested "
            "shift fraction; stress response is compared by paired "
            "stress-minus-control difference-in-differences."
        ),
        "restart_method": (
            "No physical tune is modified. Full, QS-flyweight, QS-helix and "
            "fully-QS models each run the same baseline launch and contribute "
            "their own physically admissible state at 10/30/50/70/90% shift."
        ),
        "trajectory_comparison_method": (
            "(other_stress-other_control) - "
            "(full_stress-full_control)"
        ),
        "direct_force_comparison_method": (
            "All actuator laws evaluated on the same full-model stressed "
            "state and full-model ClosureUnknowns."
        ),
        "conditioning_s": args.conditioning_s,
        "onset_s": args.onset_s,
        "hold_s": args.hold_s,
        "screen_sample_step_s": (
            args.screen_sample_step_s
        ),
        "selected_sample_step_s": (
            args.selected_sample_step_s
        ),
        "restart_shift_targets_percent": list(
            shift_percents
        ),
        "ramp_times_s": list(ramp_times),
        "grade_targets_deg": list(grade_targets),
        "secondary_torque_targets_Nm": list(
            secondary_torque_targets
        ),
        "primary_torque_targets_Nm": list(
            primary_torque_targets
        ),
        "screen_candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "ranking_notes": {
            "direct_scores": (
                "Heuristic used only to rank candidates. Raw force/torque "
                "corrections are authoritative."
            ),
            "trajectory_score": (
                "Heuristic used only to rank selected-case divergence. "
                "Raw delta columns are authoritative."
            ),
            "response_classes": {
                "clean_continuous": (
                    "No hybrid transition after stress onset."
                ),
                "contact_switching": (
                    "Hybrid mode transition(s), but no successor-state reset."
                ),
                "impact_reset": (
                    "At least one transition applies a successor-state reset."
                ),
            },
        },
        "sign_conventions": {
            "secondary_added_torque": (
                "Positive assists positive secondary rotation; negative "
                "adds resisting torque."
            ),
            "primary_added_torque": (
                "Positive assists engine/primary positive rotation; negative "
                "opposes it."
            ),
        },
    }
    (args.output_dir / "stress_test_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    make_global_overview(
        screening_rows=screening_rows,
        pairwise_rows=validation_pairwise_rows,
        output_dir=args.output_dir,
    )
    write_human_summary(
        screening_rows=screening_rows,
        pairwise_rows=validation_pairwise_rows,
        selected_rows=selected_case_summary_rows,
        output_dir=args.output_dir,
    )

    completed_screen = sum(
        row.get("status") == "completed"
        for row in screening_rows
    )
    clean_count = sum(
        row.get("response_class") == "clean_continuous"
        for row in screening_rows
    )
    switch_count = sum(
        row.get("response_class") == "contact_switching"
        for row in screening_rows
    )
    impact_count = sum(
        row.get("response_class") == "impact_reset"
        for row in screening_rows
    )

    print()
    print("ACTUATOR DYNAMICS STRESS SEARCH COMPLETE")
    print("=" * 72)
    print(
        f"screen completed: {completed_screen}/{len(candidates)}"
    )
    print(
        "response classes: "
        f"clean={clean_count}, switching={switch_count}, "
        f"impact/reset={impact_count}"
    )
    print(
        f"selected high-resolution cases: {len(selected)}"
    )
    print(f"output: {args.output_dir}")
    print()
    print(
        "Upload the ENTIRE output directory for interpretation; "
        "the global CSVs plus selected_cases/* contain enough "
        "data for new post-hoc plots without rerunning CINDER."
    )

    if args.no_show:
        plt.close("all")
    else:
        plt.show()


if __name__ == "__main__":
    main()
