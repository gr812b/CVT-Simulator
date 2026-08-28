"""Secondary-helix inertia / load sensitivity sweep.

Purpose
-------
Determine whether the small continuous helix-dynamics corrections found for
the Baja baseline are a general feature of the equations or mainly a
consequence of the present movable-secondary inertia and load scale.

This is deliberately NOT a geometrically scaled CVT model.  It holds the Baja
geometry, spring, helix profile, belt, vehicle and tune fixed while varying two
quantities independently:

    1. secondary movable-member rotational inertia I_M / I_M0
    2. imposed secondary-shaft stress torque

That isolates the governing sensitivity instead of conflating it with an
assumed geometric scaling law.

For every full-model screen case the script records:
- dynamic helix clamp correction and its individual alpha_s / s_ddot /
  curvature terms;
- correction relative to both the QS helix reaction and the complete
  QS secondary actuator clamp;
- realized secondary shaft acceleration and shift acceleration;
- whether shaft and shift inertial terms reinforce or cancel;
- clean-continuous vs hybrid impact/reset classification.

Threshold tables answer:
    At what I_M factor does the correction first exceed 5/10/20/50%?

Selected clean threshold-crossing cases are then validated using the physically
consistent QS-helix ablation with natural baseline states and paired zero-stress
controls.

Requires these already-installed launch tools:
    run_dynamic_actuator_ablation.py
    run_actuator_dynamics_stress_search.py

The latter must be the natural-baseline + paired-control version.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace, asdict
import json
from math import isfinite
from pathlib import Path
import sys
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_dynamic_actuator_ablation as ab  # noqa: E402
import run_actuator_dynamics_stress_search as stress  # noqa: E402
import run_route_grade_response as route  # noqa: E402


MILLIMETRE = 1.0e-3
NAN = float("nan")

THRESHOLDS = (0.05, 0.10, 0.20, 0.50)


@dataclass(frozen=True, slots=True)
class ScaleCase:
    case_id: str
    inertia_factor: float
    target_shift_percent: float
    torque_Nm: float
    ramp_s: float
    onset_s: float
    hold_s: float

    @property
    def restart_key(self) -> str:
        return f"s{int(round(self.target_shift_percent)):02d}"

    def stress_candidate(self) -> stress.StressCandidate:
        return stress.StressCandidate(
            case_id=self.case_id,
            restart_key=self.restart_key,
            restart_shift_percent=self.target_shift_percent,
            family="secondary_torque",
            amplitude=self.torque_Nm,
            ramp_s=self.ramp_s,
            onset_s=self.onset_s,
            hold_s=self.hold_s,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/helix_inertia_torque_scaling"),
    )
    parser.add_argument(
        "--conditioning-s",
        type=float,
        default=7.5,
        help=(
            "Unchanged-baseline launch horizon used to reach requested "
            "shift fractions for each inertia factor."
        ),
    )
    parser.add_argument(
        "--max-conditioning-s",
        type=float,
        default=30.0,
        help=(
            "Maximum automatically extended unchanged-baseline horizon. "
            "Only simulation time changes; no physical tune is modified."
        ),
    )
    parser.add_argument("--onset-s", type=float, default=0.05)
    parser.add_argument("--hold-s", type=float, default=0.35)
    parser.add_argument(
        "--screen-sample-step-s",
        type=float,
        default=0.001,
        help="1 ms default; selected validations use 0.5 ms.",
    )
    parser.add_argument(
        "--validation-sample-step-s",
        type=float,
        default=0.0005,
    )
    parser.add_argument(
        "--validate-top-n",
        type=int,
        default=18,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse completed and integration-failed rows already present in "
            "helix_scaling_screen.csv. Rows marked analysis_failed are always "
            "rerun. This is safe only when the sweep grid/model are unchanged."
        ),
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=5,
        help=(
            "Rewrite helix_scaling_screen.csv after this many newly processed "
            "cases. Successful cases are therefore not lost if a later case "
            "fails or the process is interrupted."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Small runtime-verification matrix only.",
    )
    parser.add_argument("--no-show", action="store_true")
    parser.add_argument("--rtol", type=float, default=1.0e-4)
    parser.add_argument("--atol", type=float, default=1.0e-7)
    return parser.parse_args()


def sweep_grid(args: argparse.Namespace):
    if args.quick:
        return {
            "inertia_factors": (1.0, 8.0),
            "shift_percents": (50.0,),
            "torques_Nm": (-120.0, 120.0),
            "ramp_times_s": (0.010, 0.100),
        }

    return {
        # 0.25x is included to show the low-inertia asymptote; 32x turns the
        # current 0.0025 kg m^2 movable secondary into ~0.080 kg m^2.
        "inertia_factors": (
            0.25,
            0.5,
            1.0,
            2.0,
            4.0,
            8.0,
            16.0,
            32.0,
        ),
        # Early / middle / late ratio gives the H(s) dependence without
        # exploding runtime.
        "shift_percents": (10.0, 50.0, 90.0),
        # Sign matters because alpha_s and theta_ddot can reinforce or cancel.
        "torques_Nm": (
            -480.0,
            -240.0,
            -120.0,
            -80.0,
            -40.0,
            40.0,
            80.0,
            120.0,
            240.0,
            480.0,
        ),
        "ramp_times_s": (0.005, 0.050, 0.250),
    }


def scale_secondary_movable_inertia(assembly, factor: float):
    """Scale only the secondary movable-member rotational inertia.

    Geometry, moving-sheave translational mass, fixed-side inertia, belt,
    contact, spring and actuator laws are unchanged.

    This intentionally isolates I_M sensitivity.  It is not presented as a
    complete geometrically similar larger-CVT construction.
    """

    if not isfinite(factor) or factor <= 0.0:
        raise ValueError("inertia factor must be finite and positive.")

    secondary = assembly.inertias.secondary
    scaled_secondary = replace(
        secondary,
        movable_sheave_rotational_inertia=(
            secondary.movable_sheave_rotational_inertia * factor
        ),
    )
    scaled_inertias = replace(
        assembly.inertias,
        secondary=scaled_secondary,
    )
    return replace(
        assembly,
        inertias=scaled_inertias,
    )



def build_scaled_ablation_assembly(
    scaled_full_assembly,
    variant,
):
    """Apply an actuator ablation while preserving the SCALED hardware inertia.

    The normal ablation helper in run_dynamic_actuator_ablation intentionally
    checks that the unscaled Baja secondary decomposition recovers the SCVT CAD
    total. That assertion is correct for the ordinary Baja study but is
    intentionally false here after I_M has been scaled.

    For the QS-helix reduction, the movable member still rotates with the
    secondary shaft; only its *relative helix dynamic coupling* is removed.
    Therefore its entire scaled rotational inertia is returned to the
    classical constant shaft inertia:

        I_fixed,QS = I_fixed,full + I_M,scaled
        I_M,relative,QS = 0

    This exactly preserves total rotating hardware between full and QS helix at
    each sensitivity point while deleting only the dynamic helix coupling.
    """

    primary_actuator = ab._replace_flyweight_law(
        scaled_full_assembly.pulleys.primary.actuator,
        dynamic=variant.dynamic_flyweight,
    )
    secondary_actuator = ab._replace_helix_law(
        scaled_full_assembly.pulleys.secondary.actuator,
        dynamic=variant.dynamic_helix,
    )

    primary_inertia = scaled_full_assembly.inertias.primary
    secondary_inertia = scaled_full_assembly.inertias.secondary

    if not variant.dynamic_flyweight:
        primary_inertia = ab.PrimaryInertia(
            fixed_rotating_hardware_inertia=(
                ab.PCVT_TOTAL_MOI_KG_M2
            ),
            movable_sheave_rotational_inertia=0.0,
            moving_sheave_mass=(
                scaled_full_assembly.inertias.primary.moving_sheave_mass
            ),
        )

    if not variant.dynamic_helix:
        full_fixed = float(secondary_inertia.fixed_side.total)
        full_movable = float(
            secondary_inertia.movable_sheave_rotational_inertia
        )
        scaled_total = full_fixed + full_movable

        secondary_inertia = ab.ResolvedSecondaryInertia(
            fixed_side=ab.SecondaryFixedInertia(
                fixed_rotating_hardware_inertia=scaled_total
            ),
            movable_sheave_rotational_inertia=0.0,
        )

        qs_total = (
            float(secondary_inertia.fixed_side.total)
            + float(
                secondary_inertia.movable_sheave_rotational_inertia
            )
        )
        if not np.isclose(
            qs_total,
            scaled_total,
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise RuntimeError(
                "Scaled QS-helix ablation failed to preserve total "
                "secondary rotating inertia."
            )

    return replace(
        scaled_full_assembly,
        pulleys=replace(
            scaled_full_assembly.pulleys,
            primary=replace(
                scaled_full_assembly.pulleys.primary,
                actuator=primary_actuator,
            ),
            secondary=replace(
                scaled_full_assembly.pulleys.secondary,
                actuator=secondary_actuator,
            ),
        ),
        inertias=replace(
            scaled_full_assembly.inertias,
            primary=primary_inertia,
            secondary=secondary_inertia,
        ),
    )


def run_scaled_conditioning(
    *,
    variant,
    scaled_full_assembly,
    engine,
    road_load,
    constants,
    duration_s: float,
    args,
):
    """Natural baseline conditioning using the scaled-aware ablation."""

    programme = stress.flat_programme(duration_s)
    assembly = build_scaled_ablation_assembly(
        scaled_full_assembly,
        variant,
    )
    system = stress.build_standard_system(
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
    result = stress.integrate_hybrid(
        system=system,
        time_span=(0.0, duration_s),
        initial_state=initial_full,
        initial_mode=system.classify_initial_mode(initial_full),
        settings=stress.HybridIntegratorSettings(
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
            f"{variant.label} scaled conditioning launch failed: "
            + result.termination_reason
        )

    samples, _ = ab.sample_variant(
        variant=variant,
        system=system,
        result=result,
        step_s=0.001,
    )
    return assembly, system, result, samples


def run_scaled_stress_variant(
    *,
    variant,
    candidate,
    restart,
    scaled_full_assembly,
    engine,
    road_load,
    constants,
    sample_step_s: float,
    args,
    screening: bool,
):
    """Stress integration using the scaled-aware actuator ablation."""

    assembly = build_scaled_ablation_assembly(
        scaled_full_assembly,
        variant,
    )
    system, programme = stress.build_stress_system(
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
    initial_mode = restart.composed_mode

    max_step = min(
        0.003 if screening else 0.001,
        max(0.00025, candidate.ramp_s / 5.0),
    )

    try:
        result = stress.integrate_hybrid(
            system=system,
            time_span=(0.0, candidate.duration_s),
            initial_state=initial_state,
            initial_mode=initial_mode,
            settings=stress.HybridIntegratorSettings(
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

    signal = stress.SmoothStepSignal(
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
        row["grade_deg"] = float(
            np.degrees(programme.grade_radians(sample.time))
        )
        row["stress_signal_fraction"] = (
            signal.value(sample.time) / candidate.amplitude
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



def build_cases(grid, args) -> list[ScaleCase]:
    cases: list[ScaleCase] = []
    index = 0
    for factor in grid["inertia_factors"]:
        for shift in grid["shift_percents"]:
            for ramp_s in grid["ramp_times_s"]:
                for torque in grid["torques_Nm"]:
                    index += 1
                    cases.append(
                        ScaleCase(
                            case_id=f"H{index:04d}",
                            inertia_factor=float(factor),
                            target_shift_percent=float(shift),
                            torque_Nm=float(torque),
                            ramp_s=float(ramp_s),
                            onset_s=float(args.onset_s),
                            hold_s=float(args.hold_s),
                        )
                    )
    return cases


def _finite_row_values(rows, key):
    values = []
    for sample in rows:
        value = float(sample.row.get(key, NAN))
        if isfinite(value):
            values.append((sample, value))
    return values


def screen_case_metrics(
    *,
    case: ScaleCase,
    restart,
    result: ab.VariantResult,
    baseline_I_M: float,
):
    samples = [
        sample
        for sample in result.samples
        if sample.closure is not None
        and sample.time >= case.onset_s
    ]
    if not samples:
        raise RuntimeError("No engaged samples after stress onset.")

    # Find the sample with the largest dynamic helix clamp correction.
    candidates = []
    for sample in samples:
        row = sample.row
        delta = float(
            row.get("helix_dynamic_total_correction_N", NAN)
        )
        if not isfinite(delta):
            continue
        qs_helix = float(
            row.get("helix_qs_reaction_force_N", NAN)
        )
        full_total = float(
            row.get("secondary_actuator_closing_force_N", NAN)
        )
        shaft_force = float(
            row.get("helix_dynamic_shaft_accel_force_N", NAN)
        )
        shift_force = float(
            row.get("helix_dynamic_shift_accel_force_N", NAN)
        )
        curvature = float(
            row.get("helix_dynamic_curvature_force_N", NAN)
        )
        alpha_s = float(
            row.get("rhs_alpha_secondary_rad_s2", NAN)
        )
        sddot = float(
            row.get("rhs_shift_acceleration_m_s2", NAN)
        )

        qs_total = (
            full_total - delta
            if isfinite(full_total)
            else NAN
        )
        candidates.append(
            (
                abs(delta),
                sample,
                delta,
                qs_helix,
                qs_total,
                shaft_force,
                shift_force,
                curvature,
                alpha_s,
                sddot,
            )
        )

    if not candidates:
        raise RuntimeError(
            "No finite helix dynamic correction samples."
        )

    (
        _,
        peak_sample,
        delta,
        qs_helix,
        qs_total,
        shaft_force,
        shift_force,
        curvature,
        alpha_s,
        sddot,
    ) = max(candidates, key=lambda item: item[0])

    # Raw physical fractions. Separate floor-normalized fractions are supplied
    # for stable ranking near a QS zero crossing.
    helix_fraction_raw = (
        abs(delta) / abs(qs_helix)
        if isfinite(qs_helix) and abs(qs_helix) > 1.0e-12
        else NAN
    )
    total_fraction_raw = (
        abs(delta) / abs(qs_total)
        if isfinite(qs_total) and abs(qs_total) > 1.0e-12
        else NAN
    )
    helix_fraction_floor = (
        abs(delta) / max(abs(qs_helix), 500.0)
        if isfinite(qs_helix)
        else NAN
    )
    total_fraction_floor = (
        abs(delta) / max(abs(qs_total), 500.0)
        if isfinite(qs_total)
        else NAN
    )

    same_sign = bool(
        isfinite(shaft_force)
        and isfinite(shift_force)
        and shaft_force != 0.0
        and shift_force != 0.0
        and np.sign(shaft_force) == np.sign(shift_force)
    )
    component_abs_sum = sum(
        abs(value)
        for value in (shaft_force, shift_force, curvature)
        if isfinite(value)
    )
    cancellation_ratio = (
        abs(delta) / component_abs_sum
        if component_abs_sum > 0.0
        else NAN
    )

    transitions = [
        record
        for record in result.hybrid_result.transitions
        if record.time >= case.onset_s
    ]
    reset_count = sum(
        record.transition.has_successor_state
        for record in transitions
    )
    response_class = (
        "impact_reset"
        if reset_count
        else (
            "contact_switching"
            if transitions
            else "clean_continuous"
        )
    )

    secondary_inertia = (
        result.assembly.inertias.secondary
        .movable_sheave_rotational_inertia
    )

    # Peak realized acceleration magnitudes over the entire stress window.
    shift_accels = [
        abs(float(sample.row.get(
            "rhs_shift_acceleration_m_s2", NAN
        )))
        for sample in samples
        if isfinite(float(sample.row.get(
            "rhs_shift_acceleration_m_s2", NAN
        )))
    ]
    secondary_accels = []
    for sample in samples:
        row = sample.row
        value = float(
            row.get("rhs_alpha_secondary_rad_s2", NAN)
        )
        if isfinite(value):
            secondary_accels.append(abs(value))

    return {
        "case_id": case.case_id,
        "inertia_factor": case.inertia_factor,
        "baseline_movable_secondary_inertia_kg_m2": baseline_I_M,
        "movable_secondary_inertia_kg_m2": secondary_inertia,
        "target_shift_percent": case.target_shift_percent,
        "actual_restart_shift_percent": restart.actual_shift_percent,
        "restart_conditioning_time_s": restart.source_time_s,
        "stress_torque_Nm": case.torque_Nm,
        "ramp_s": case.ramp_s,
        "ramp_ms": 1000.0 * case.ramp_s,
        "response_class": response_class,
        "transition_count_after_onset": len(transitions),
        "reset_count_after_onset": reset_count,
        "peak_correction_time_s": peak_sample.time,
        "peak_helix_dynamic_correction_N": delta,
        "peak_abs_helix_dynamic_correction_N": abs(delta),
        "qs_helix_reaction_at_peak_N": qs_helix,
        "qs_total_secondary_clamp_at_peak_N": qs_total,
        "peak_dynamic_vs_qs_helix_fraction_raw": helix_fraction_raw,
        "peak_dynamic_vs_qs_helix_percent_raw": 100.0 * helix_fraction_raw,
        "peak_dynamic_vs_qs_total_clamp_fraction_raw": total_fraction_raw,
        "peak_dynamic_vs_qs_total_clamp_percent_raw": (
            100.0 * total_fraction_raw
        ),
        "peak_dynamic_vs_qs_helix_fraction_floor500": helix_fraction_floor,
        "peak_dynamic_vs_qs_total_clamp_fraction_floor500": total_fraction_floor,
        "helix_shaft_accel_force_at_peak_N": shaft_force,
        "helix_shift_accel_force_at_peak_N": shift_force,
        "helix_curvature_force_at_peak_N": curvature,
        "shaft_and_shift_terms_reinforce_at_peak": same_sign,
        "component_cancellation_ratio_at_peak": cancellation_ratio,
        "secondary_alpha_at_peak_rad_s2": alpha_s,
        "shift_acceleration_at_peak_m_s2": sddot,
        "peak_abs_secondary_alpha_rad_s2": (
            max(secondary_accels)
            if secondary_accels else NAN
        ),
        "peak_abs_shift_acceleration_m_s2": (
            max(shift_accels)
            if shift_accels else NAN
        ),
        "status": "completed",
    }


def threshold_rows(screen_rows):
    """Minimum I_M factor reaching each threshold for each stress condition.

    Only clean-continuous cases participate. Two separate threshold metrics are
    reported: relative to the QS helix reaction alone and relative to the
    complete QS secondary actuator clamp.
    """

    clean = [
        row
        for row in screen_rows
        if row.get("status") == "completed"
        and row.get("response_class") == "clean_continuous"
    ]

    groups: dict[tuple[float, float, float], list[dict[str, Any]]] = {}
    for row in clean:
        key = (
            float(row["target_shift_percent"]),
            float(row["stress_torque_Nm"]),
            float(row["ramp_s"]),
        )
        groups.setdefault(key, []).append(row)

    output = []
    for (shift, torque, ramp), rows in sorted(groups.items()):
        rows = sorted(
            rows,
            key=lambda row: float(row["inertia_factor"]),
        )
        for metric, label in (
            (
                "peak_dynamic_vs_qs_helix_fraction_raw",
                "qs_helix_reaction",
            ),
            (
                "peak_dynamic_vs_qs_total_clamp_fraction_raw",
                "qs_total_secondary_clamp",
            ),
        ):
            for threshold in THRESHOLDS:
                crossing = next(
                    (
                        row
                        for row in rows
                        if isfinite(float(row.get(metric, NAN)))
                        and float(row[metric]) >= threshold
                    ),
                    None,
                )
                output.append(
                    {
                        "target_shift_percent": shift,
                        "stress_torque_Nm": torque,
                        "ramp_s": ramp,
                        "ramp_ms": 1000.0 * ramp,
                        "normalization": label,
                        "threshold_fraction": threshold,
                        "threshold_percent": 100.0 * threshold,
                        "crossed": crossing is not None,
                        "minimum_inertia_factor": (
                            float(crossing["inertia_factor"])
                            if crossing else NAN
                        ),
                        "minimum_inertia_kg_m2": (
                            float(
                                crossing[
                                    "movable_secondary_inertia_kg_m2"
                                ]
                            )
                            if crossing else NAN
                        ),
                        "correction_percent_at_crossing": (
                            100.0 * float(crossing[metric])
                            if crossing else NAN
                        ),
                    }
                )
    return output


def select_validation_cases(screen_rows, top_n: int):
    """Select diverse clean cases around threshold crossings + strongest cases."""

    clean = [
        row
        for row in screen_rows
        if row.get("status") == "completed"
        and row.get("response_class") == "clean_continuous"
    ]
    selected: list[str] = []

    def add(row):
        if row is None:
            return
        cid = row["case_id"]
        if cid not in selected and len(selected) < top_n:
            selected.append(cid)

    # For each ratio, keep the strongest baseline-I case and the first clean
    # 5/10/20/50% total-clamp threshold crossings.
    shifts = sorted(
        {float(row["target_shift_percent"]) for row in clean}
    )
    for shift in shifts:
        bucket = [
            row for row in clean
            if float(row["target_shift_percent"]) == shift
        ]

        baseline = [
            row for row in bucket
            if np.isclose(float(row["inertia_factor"]), 1.0)
        ]
        if baseline:
            add(max(
                baseline,
                key=lambda row: float(
                    row[
                        "peak_dynamic_vs_qs_total_clamp_fraction_raw"
                    ]
                ),
            ))

        for threshold in THRESHOLDS:
            crossing = [
                row
                for row in bucket
                if isfinite(float(
                    row[
                        "peak_dynamic_vs_qs_total_clamp_fraction_raw"
                    ]
                ))
                and float(
                    row[
                        "peak_dynamic_vs_qs_total_clamp_fraction_raw"
                    ]
                ) >= threshold
            ]
            if crossing:
                crossing.sort(
                    key=lambda row: (
                        float(row["inertia_factor"]),
                        abs(float(row["stress_torque_Nm"])),
                        float(row["ramp_s"]),
                    )
                )
                add(crossing[0])

    # Fill remaining slots with globally strongest clean cases while avoiding
    # all slots being consumed by one shift position.
    ordered = sorted(
        clean,
        key=lambda row: float(
            row[
                "peak_dynamic_vs_qs_total_clamp_fraction_raw"
            ]
        ),
        reverse=True,
    )
    for row in ordered:
        add(row)
        if len(selected) >= top_n:
            break

    by_id = {row["case_id"]: row for row in screen_rows}
    return [by_id[cid] for cid in selected]


def make_screen_plots(
    *,
    screen_rows,
    grid,
    output_dir: Path,
):
    clean = [
        row
        for row in screen_rows
        if row.get("status") == "completed"
        and row.get("response_class") == "clean_continuous"
    ]

    # Plot one figure per requested shift at the middle ramp duration.
    ramp_values = tuple(grid["ramp_times_s"])
    reference_ramp = ramp_values[len(ramp_values) // 2]

    for shift in grid["shift_percents"]:
        rows = [
            row
            for row in clean
            if np.isclose(
                float(row["target_shift_percent"]),
                float(shift),
            )
            and np.isclose(
                float(row["ramp_s"]),
                float(reference_ramp),
            )
        ]
        if not rows:
            continue

        fig, ax = plt.subplots(
            figsize=(10.0, 6.5),
            constrained_layout=True,
        )
        torques = sorted(
            {float(row["stress_torque_Nm"]) for row in rows}
        )
        for torque in torques:
            subset = sorted(
                (
                    row for row in rows
                    if np.isclose(
                        float(row["stress_torque_Nm"]),
                        torque,
                    )
                ),
                key=lambda row: float(row["inertia_factor"]),
            )
            ax.plot(
                [float(row["inertia_factor"]) for row in subset],
                [
                    100.0
                    * float(
                        row[
                            "peak_dynamic_vs_qs_total_clamp_fraction_raw"
                        ]
                    )
                    for row in subset
                ],
                marker="o",
                label=f"{torque:+.0f} N m",
            )

        for threshold in (5.0, 10.0, 20.0, 50.0):
            ax.axhline(
                threshold,
                linewidth=0.8,
                linestyle="--",
                alpha=0.5,
            )

        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xlabel(r"Movable-secondary inertia factor $I_M/I_{M,0}$")
        ax.set_ylabel(
            "Peak helix dynamic correction / QS total secondary clamp [%]"
        )
        ax.set_title(
            f"{shift:.0f}% shift, {1000*reference_ramp:.0f} ms "
            "secondary-torque ramp — clean cases"
        )
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=7, ncol=2)
        fig.savefig(
            output_dir
            / f"01_correction_vs_inertia_{int(round(shift)):02d}pct.png",
            dpi=180,
        )
        plt.close(fig)



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

    # At duplicate hybrid boundary times use the last retained value; exact
    # pre/post reset information remains separately in the transition CSV.
    by_time = {}
    for time_s, value in pairs:
        by_time[time_s] = value
    times = np.asarray(sorted(by_time), dtype=float)
    values = np.asarray(
        [by_time[time_s] for time_s in times],
        dtype=float,
    )
    return times, values


def plot_two_model_paired_response(
    *,
    candidate,
    full_stress,
    full_control,
    qs_stress,
    qs_control,
    output_dir: Path,
    sample_step_s: float,
):
    """Plot stress-minus-control response for full vs QS helix only."""

    start = candidate.onset_s
    end = min(
        full_stress.hybrid_result.final_time,
        full_control.hybrid_result.final_time,
        qs_stress.hybrid_result.final_time,
        qs_control.hybrid_result.final_time,
    )
    grid = np.arange(
        start,
        end + 0.5 * sample_step_s,
        sample_step_s,
    )

    fields = (
        ("shift_mm", "Stress-induced shift [mm]"),
        ("primary_rpm", "Stress-induced primary speed [rpm]"),
        (
            "secondary_actuator_closing_force_N",
            "Stress-induced secondary clamp [N]",
        ),
        ("normal_secondary_N", r"Stress-induced $N_s$ [N]"),
    )

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(10.5, 10.0),
        sharex=True,
        constrained_layout=True,
    )

    for axis, (key, ylabel) in zip(axes, fields, strict=True):
        for label, stressed, control in (
            ("Full dynamic", full_stress, full_control),
            ("QS helix", qs_stress, qs_control),
        ):
            st, sv = _series_for_interp(stressed.samples, key)
            ct, cv = _series_for_interp(control.samples, key)
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
                label=label,
            )
        axis.set_ylabel(ylabel)
        axis.axhline(0.0, linewidth=0.8)
        axis.grid(True, alpha=0.25)

    axes[0].set_title(
        f"{candidate.case_id}: full vs QS-helix paired stress response"
    )
    axes[0].legend()
    axes[-1].set_xlabel("Time since stress onset [s]")

    fig.savefig(
        output_dir / "paired_full_vs_qs_helix_response.png",
        dpi=180,
    )
    plt.close(fig)




def condition_and_select_with_extension(
    *,
    variant,
    full_assembly,
    engine,
    road_load,
    constants,
    target_percents,
    args,
):
    """Run unchanged baseline long enough to actually reach requested ratios."""

    duration = float(args.conditioning_s)
    maximum = float(args.max_conditioning_s)
    if duration <= 0.0 or maximum < duration:
        raise ValueError(
            "--conditioning-s must be positive and "
            "--max-conditioning-s must be >= it."
        )

    last_error = None
    while True:
        assembly, system, raw, samples = run_scaled_conditioning(
            variant=variant,
            scaled_full_assembly=full_assembly,
            engine=engine,
            road_load=road_load,
            constants=constants,
            duration_s=duration,
            args=args,
        )
        try:
            states = stress.select_restart_states(
                variant=variant,
                conditioning_system=system,
                samples=samples,
                target_percents=target_percents,
            )
        except RuntimeError as exc:
            last_error = exc
            if duration >= maximum - 1.0e-12:
                raise RuntimeError(
                    f"{variant.label} did not naturally reach all requested "
                    f"shift fractions by {maximum:.3f} s with the unchanged "
                    "physical baseline."
                ) from last_error
            new_duration = min(maximum, max(duration * 1.6, duration + 2.0))
            print(
                f"    requested ratio not yet reached by {duration:.3f} s; "
                f"extending unchanged-baseline conditioning to "
                f"{new_duration:.3f} s..."
            )
            duration = new_duration
            continue

        return system, raw, samples, states, duration



def validate_selected_cases(
    *,
    selected_rows,
    baseline_assembly,
    engine,
    road_load,
    constants,
    args,
    output_dir: Path,
):
    """Validate full-vs-QS-helix trajectory response for selected clean cases."""

    if not selected_rows:
        return [], []

    full_variant = next(
        variant for variant in ab.VARIANTS
        if variant.key == "full"
    )
    qs_helix_variant = next(
        variant for variant in ab.VARIANTS
        if variant.key == "quasi_static_helix"
    )

    # Conditioning is cached by (inertia factor, variant), because many
    # threshold cases reuse one hardware point.
    factors = sorted(
        {float(row["inertia_factor"]) for row in selected_rows}
    )
    shifts_by_factor = {
        factor: sorted(
            {
                float(row["target_shift_percent"])
                for row in selected_rows
                if np.isclose(
                    float(row["inertia_factor"]),
                    factor,
                )
            }
        )
        for factor in factors
    }

    restart_cache: dict[
        tuple[float, str],
        dict[str, object],
    ] = {}

    for factor in factors:
        scaled = scale_secondary_movable_inertia(
            baseline_assembly,
            factor,
        )
        for variant in (full_variant, qs_helix_variant):
            system, raw, samples, states, used_duration = (
                condition_and_select_with_extension(
                    variant=variant,
                    full_assembly=scaled,
                    engine=engine,
                    road_load=road_load,
                    constants=constants,
                    target_percents=shifts_by_factor[factor],
                    args=args,
                )
            )
            restart_cache[(factor, variant.key)] = {
                state.key: state for state in states
            }

    pair_rows = []
    case_rows = []

    selected_root = output_dir / "selected_validation_cases"
    selected_root.mkdir(parents=True, exist_ok=True)

    for index, screen_row in enumerate(selected_rows, start=1):
        factor = float(screen_row["inertia_factor"])
        case_id = str(screen_row["case_id"])
        case = ScaleCase(
            case_id=case_id,
            inertia_factor=factor,
            target_shift_percent=float(
                screen_row["target_shift_percent"]
            ),
            torque_Nm=float(screen_row["stress_torque_Nm"]),
            ramp_s=float(screen_row["ramp_s"]),
            onset_s=float(args.onset_s),
            hold_s=float(args.hold_s),
        )
        candidate = case.stress_candidate()
        control_candidate = replace(
            candidate,
            case_id=f"{case_id}_CONTROL",
            amplitude=0.0,
        )
        scaled = scale_secondary_movable_inertia(
            baseline_assembly,
            factor,
        )

        runs = {}
        errors = []
        for variant in (full_variant, qs_helix_variant):
            restart = restart_cache[(factor, variant.key)][
                case.restart_key
            ]
            stress_result, _, _, stress_error = (
                run_scaled_stress_variant(
                    variant=variant,
                    candidate=candidate,
                    restart=restart,
                    scaled_full_assembly=scaled,
                    engine=engine,
                    road_load=road_load,
                    constants=constants,
                    sample_step_s=(
                        args.validation_sample_step_s
                    ),
                    args=args,
                    screening=False,
                )
            )
            control_result, _, _, control_error = (
                run_scaled_stress_variant(
                    variant=variant,
                    candidate=control_candidate,
                    restart=restart,
                    scaled_full_assembly=scaled,
                    engine=engine,
                    road_load=road_load,
                    constants=constants,
                    sample_step_s=(
                        args.validation_sample_step_s
                    ),
                    args=args,
                    screening=False,
                )
            )
            if stress_result is None or control_result is None:
                errors.append(
                    {
                        "variant": variant.key,
                        "stress_error": stress_error,
                        "control_error": control_error,
                    }
                )
                continue
            runs[(variant.key, "stress")] = stress_result
            runs[(variant.key, "control")] = control_result

        case_dir = (
            selected_root
            / f"{index:02d}_{case_id}_I{factor:g}"
        )
        case_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "selected_index": index,
            "screen_row": screen_row,
            "case": asdict(case),
            "errors": errors,
            "comparison": (
                "(QS_helix_stress-QS_helix_control) - "
                "(full_stress-full_control)"
            ),
        }
        (case_dir / "case_manifest.json").write_text(
            json.dumps(
                manifest,
                indent=2,
                allow_nan=True,
            )
            + "\n",
            encoding="utf-8",
        )

        required = (
            ("full", "stress"),
            ("full", "control"),
            ("quasi_static_helix", "stress"),
            ("quasi_static_helix", "control"),
        )
        if not all(key in runs for key in required):
            continue

        pair = stress.paired_perturbation_metrics(
            candidate=candidate,
            full_stress=runs[("full", "stress")],
            full_control=runs[("full", "control")],
            other_stress=runs[
                ("quasi_static_helix", "stress")
            ],
            other_control=runs[
                ("quasi_static_helix", "control")
            ],
            sample_step_s=args.validation_sample_step_s,
        )
        pair.update(
            {
                "inertia_factor": factor,
                "movable_secondary_inertia_kg_m2": (
                    scaled.inertias.secondary
                    .movable_sheave_rotational_inertia
                ),
                "target_shift_percent": (
                    case.target_shift_percent
                ),
                "stress_torque_Nm": case.torque_Nm,
                "ramp_s": case.ramp_s,
            }
        )
        pair_rows.append(pair)

        # Save both stress and control trajectories for independent analysis.
        stress_rows = []
        control_rows = []
        transitions = []
        control_transitions = []
        for key in (("full", "stress"), ("quasi_static_helix", "stress")):
            result = runs[key]
            for sample in result.samples:
                row = dict(sample.row)
                row["inertia_factor"] = factor
                row["scaling_case_id"] = case_id
                stress_rows.append(row)
            transitions.extend(ab.transition_rows(result))

        for key in (("full", "control"), ("quasi_static_helix", "control")):
            result = runs[key]
            for sample in result.samples:
                row = dict(sample.row)
                row["inertia_factor"] = factor
                row["scaling_case_id"] = case_id
                control_rows.append(row)
            control_transitions.extend(ab.transition_rows(result))

        ab._write_dict_rows(
            case_dir / "trajectory_diagnostics.csv",
            stress_rows,
        )
        ab._write_dict_rows(
            case_dir / "control_trajectory_diagnostics.csv",
            control_rows,
        )
        ab._write_dict_rows(
            case_dir / "hybrid_transitions.csv",
            transitions,
        )
        ab._write_dict_rows(
            case_dir / "control_hybrid_transitions.csv",
            control_transitions,
        )
        ab._write_dict_rows(
            case_dir / "paired_qs_helix_vs_full.csv",
            [pair],
        )

        plot_two_model_paired_response(
            candidate=candidate,
            full_stress=runs[("full", "stress")],
            full_control=runs[("full", "control")],
            qs_stress=runs[
                ("quasi_static_helix", "stress")
            ],
            qs_control=runs[
                ("quasi_static_helix", "control")
            ],
            output_dir=case_dir,
            sample_step_s=args.validation_sample_step_s,
        )

        case_rows.append(
            {
                "selected_index": index,
                "case_id": case_id,
                "inertia_factor": factor,
                "target_shift_percent": (
                    case.target_shift_percent
                ),
                "stress_torque_Nm": case.torque_Nm,
                "ramp_s": case.ramp_s,
                "screen_peak_total_clamp_correction_percent": (
                    screen_row[
                        "peak_dynamic_vs_qs_total_clamp_percent_raw"
                    ]
                ),
                "paired_max_shift_delta_mm": pair.get(
                    "max_abs_paired_delta_shift_mm"
                ),
                "paired_max_primary_rpm_delta": pair.get(
                    "max_abs_paired_delta_primary_rpm"
                ),
                "paired_max_secondary_normal_delta_N": pair.get(
                    "max_abs_paired_delta_normal_secondary_N"
                ),
                "paired_divergence_score": pair.get(
                    "paired_trajectory_divergence_score"
                ),
            }
        )

    return pair_rows, case_rows



def _load_resume_rows(path: Path) -> dict[str, dict[str, Any]]:
    """Load reusable rows from a previous identical-grid run.

    - completed: expensive simulation + analysis already succeeded; reuse it.
    - failed: integration/hybrid failure already established; reuse it.
    - analysis_failed: NEVER reuse, because this means post-processing code
      failed and the physical simulation may actually have completed.
    """

    if not path.exists() or path.stat().st_size == 0:
        return {}

    import csv

    reusable: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            case_id = row.get("case_id")
            status = row.get("status")
            if not case_id:
                continue
            if status in ("completed", "failed"):
                reusable[case_id] = dict(row)
    return reusable


def _normalise_resume_row(
    row: dict[str, Any],
    case: ScaleCase,
) -> dict[str, Any]:
    """Restore stable typed fields on a row read from CSV."""

    restored = dict(row)

    # Old integration-failure rows were written directly from asdict(case),
    # hence they used torque_Nm instead of the analyzed row's
    # stress_torque_Nm. Keep the current schema coherent.
    if (
        "stress_torque_Nm" not in restored
        or restored.get("stress_torque_Nm") in ("", None)
    ):
        old = restored.get("torque_Nm")
        restored["stress_torque_Nm"] = (
            float(old) if old not in ("", None) else case.torque_Nm
        )

    restored.update(
        {
            "case_id": case.case_id,
            "inertia_factor": case.inertia_factor,
            "target_shift_percent": case.target_shift_percent,
            "ramp_s": case.ramp_s,
            "ramp_ms": 1000.0 * case.ramp_s,
            "stress_torque_Nm": case.torque_Nm,
        }
    )
    return restored


def _write_screen_checkpoint(
    *,
    path: Path,
    rows_by_id: dict[str, dict[str, Any]],
    case_order: list[ScaleCase],
) -> None:
    """Persist all processed screen rows in deterministic case order."""

    ordered = [
        rows_by_id[case.case_id]
        for case in case_order
        if case.case_id in rows_by_id
    ]
    ab._write_dict_rows(path, ordered)



def main() -> None:
    args = parse_args()
    if args.validate_top_n < 0:
        raise ValueError("--validate-top-n must be non-negative.")
    if args.checkpoint_every < 1:
        raise ValueError("--checkpoint-every must be at least one.")

    # Verify the installed stress tool is the corrected natural-baseline
    # version before doing a long sweep.
    required_api = (
        "run_conditioning",
        "select_restart_states",
        "run_stress_variant",
        "paired_perturbation_metrics",
    )
    missing = [
        name for name in required_api
        if not hasattr(stress, name)
    ]
    if missing:
        raise RuntimeError(
            "Installed run_actuator_dynamics_stress_search.py is too old. "
            "Install the natural-baseline paired-control version first. "
            "Missing: " + ", ".join(missing)
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    preset = (
        HERE
        / "presets"
        / "circular_traction_first_reference.json"
    )
    tune_candidate = route.load_candidate(preset)
    resolved = route.resolve_primary_preload(
        tune_candidate,
        target_engagement_rpm=2000.0,
        programme=stress.flat_programme(args.conditioning_s),
    )
    baseline_assembly, engine, road_load = route.build_components(
        resolved.constants
    )

    baseline_I_M = (
        baseline_assembly.inertias.secondary
        .movable_sheave_rotational_inertia
    )
    grid = sweep_grid(args)
    cases = build_cases(grid, args)

    print(
        "HELIX INERTIA / TORQUE SENSITIVITY SWEEP\n"
        f"Baseline movable-secondary inertia: {baseline_I_M:.9g} kg m^2\n"
        f"Screen cases: {len(cases)}"
    )

    # Condition full dynamic model once per I_M factor and extract all requested
    # ratio states. This keeps each scaled system on its own natural baseline.
    restart_by_factor = {}
    scaled_assembly_by_factor = {}

    full_variant = next(
        variant for variant in ab.VARIANTS
        if variant.key == "full"
    )

    for factor in grid["inertia_factors"]:
        factor = float(factor)
        scaled = scale_secondary_movable_inertia(
            baseline_assembly,
            factor,
        )
        scaled_assembly_by_factor[factor] = scaled

        print(
            f"Conditioning full model at I_M/I_M0={factor:g} "
            f"(I_M={scaled.inertias.secondary.movable_sheave_rotational_inertia:.6g})..."
        )
        system, raw, samples, states, used_duration = (
            condition_and_select_with_extension(
                variant=full_variant,
                full_assembly=scaled,
                engine=engine,
                road_load=road_load,
                constants=resolved.constants,
                target_percents=grid["shift_percents"],
                args=args,
            )
        )
        print(
            f"    natural restart states resolved using "
            f"{used_duration:.3f} s conditioning horizon"
        )
        restart_by_factor[factor] = {
            state.key: state for state in states
        }

    screen_path = args.output_dir / "helix_scaling_screen.csv"
    reusable = (
        _load_resume_rows(screen_path)
        if args.resume
        else {}
    )
    rows_by_id: dict[str, dict[str, Any]] = {}
    reused_count = 0

    if reusable:
        valid_case_ids = {case.case_id for case in cases}
        reusable = {
            case_id: row
            for case_id, row in reusable.items()
            if case_id in valid_case_ids
        }
        print(
            f"Resume enabled: {len(reusable)} completed/integration-failed "
            "screen rows can be reused. analysis_failed rows will be rerun."
        )

    newly_processed = 0

    for index, case in enumerate(cases, start=1):
        prior = reusable.get(case.case_id)
        if prior is not None:
            rows_by_id[case.case_id] = _normalise_resume_row(
                prior,
                case,
            )
            reused_count += 1
            continue

        factor = case.inertia_factor
        restart = restart_by_factor[factor][case.restart_key]
        candidate = case.stress_candidate()

        result, raw, programme, error = stress.run_stress_variant(
            variant=full_variant,
            candidate=candidate,
            restart=restart,
            full_assembly=scaled_assembly_by_factor[factor],
            engine=engine,
            road_load=road_load,
            constants=resolved.constants,
            sample_step_s=args.screen_sample_step_s,
            args=args,
            screening=True,
        )

        if result is None:
            row = {
                **asdict(case),
                "stress_torque_Nm": case.torque_Nm,
                "ramp_ms": 1000.0 * case.ramp_s,
                "status": "failed",
                "error": error,
            }
        else:
            # IMPORTANT: analysis exceptions are programming/data-schema bugs,
            # not physical model failures. Fail immediately so an expensive
            # sweep can never silently turn hundreds of successful simulations
            # into analysis_failed rows again.
            try:
                row = screen_case_metrics(
                    case=case,
                    restart=restart,
                    result=result,
                    baseline_I_M=baseline_I_M,
                )
            except Exception as exc:
                rows_by_id[case.case_id] = {
                    **asdict(case),
                    "stress_torque_Nm": case.torque_Nm,
                    "ramp_ms": 1000.0 * case.ramp_s,
                    "status": "analysis_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                _write_screen_checkpoint(
                    path=screen_path,
                    rows_by_id=rows_by_id,
                    case_order=cases,
                )
                raise RuntimeError(
                    "POST-PROCESSING FAILED AFTER A COMPLETED PHYSICAL "
                    f"SIMULATION IN {case.case_id}. The sweep has been "
                    "checkpointed and is stopping immediately rather than "
                    "discarding later expensive solves. Fix the analysis error "
                    "and rerun with --resume."
                ) from exc

        rows_by_id[case.case_id] = row
        newly_processed += 1

        if (
            newly_processed % args.checkpoint_every == 0
            or index == len(cases)
        ):
            _write_screen_checkpoint(
                path=screen_path,
                rows_by_id=rows_by_id,
                case_order=cases,
            )

        if index % max(1, len(cases) // 20) == 0:
            print(
                f"  processed {index}/{len(cases)} "
                f"(new={newly_processed}, reused={reused_count})"
            )

    # Final deterministic checkpoint.
    _write_screen_checkpoint(
        path=screen_path,
        rows_by_id=rows_by_id,
        case_order=cases,
    )
    screen_rows = [
        rows_by_id[case.case_id]
        for case in cases
        if case.case_id in rows_by_id
    ]

    analysis_failed = [
        row
        for row in screen_rows
        if row.get("status") == "analysis_failed"
    ]
    if analysis_failed:
        raise RuntimeError(
            f"{len(analysis_failed)} analysis_failed rows remain after "
            "screening. Refusing to generate thresholds from an invalid "
            "screen."
        )

    completed_screen = sum(
        row.get("status") == "completed"
        for row in screen_rows
    )
    if completed_screen == 0:
        raise RuntimeError(
            "No screen cases completed successfully. Refusing to print a "
            "misleading 'sweep complete' message."
        )

    thresholds = threshold_rows(screen_rows)
    ab._write_dict_rows(
        args.output_dir / "helix_scaling_thresholds.csv",
        thresholds,
    )

    selected_rows = select_validation_cases(
        screen_rows,
        top_n=args.validate_top_n,
    )
    (args.output_dir / "selected_validation_cases.json").write_text(
        json.dumps(
            selected_rows,
            indent=2,
            allow_nan=True,
        )
        + "\n",
        encoding="utf-8",
    )

    pair_rows, selected_summary = validate_selected_cases(
        selected_rows=selected_rows,
        baseline_assembly=baseline_assembly,
        engine=engine,
        road_load=road_load,
        constants=resolved.constants,
        args=args,
        output_dir=args.output_dir,
    )
    ab._write_dict_rows(
        args.output_dir / "selected_paired_qs_helix_vs_full.csv",
        pair_rows,
    )
    ab._write_dict_rows(
        args.output_dir / "selected_validation_summary.csv",
        selected_summary,
    )

    make_screen_plots(
        screen_rows=screen_rows,
        grid=grid,
        output_dir=args.output_dir,
    )

    manifest = {
        "study": "helix_inertia_torque_scaling_sensitivity",
        "baseline_movable_secondary_inertia_kg_m2": baseline_I_M,
        "conditioning_s_initial": args.conditioning_s,
        "conditioning_s_max": args.max_conditioning_s,
        "resume_used": bool(args.resume),
        "checkpoint_every_cases": args.checkpoint_every,
        "inertia_factors": list(grid["inertia_factors"]),
        "shift_percents": list(grid["shift_percents"]),
        "secondary_stress_torques_Nm": list(
            grid["torques_Nm"]
        ),
        "ramp_times_s": list(grid["ramp_times_s"]),
        "screen_case_count": len(cases),
        "selected_validation_count": len(selected_rows),
        "thresholds_percent": [
            100.0 * value for value in THRESHOLDS
        ],
        "physical_interpretation": (
            "I_M is varied independently while Baja geometry, translational "
            "mass, helix, springs, belt, engine, vehicle and tune are fixed. "
            "This is a sensitivity study, NOT a geometrically scaled larger "
            "CVT. Torque is swept independently to expose the competition "
            "between inertial reaction and quasi-static torque reaction."
        ),
        "threshold_policy": (
            "Thresholds use CLEAN-CONTINUOUS cases only. Impact/reset cases "
            "remain in the screen CSV but cannot define a reliable continuous "
            "force threshold because rigid-stop event peaks are model-local."
        ),
        "trajectory_validation": (
            "Selected clean cases compare QS-helix vs full through paired "
            "stress-minus-control difference-in-differences using each model's "
            "own natural restart state at the requested ratio. At every I_M "
            "factor, the QS-helix model preserves the SAME scaled total "
            "secondary rotating inertia by transferring the scaled movable "
            "member inertia into constant shaft inertia; only relative helix "
            "dynamic coupling is removed."
        ),
    }
    (args.output_dir / "helix_scaling_manifest.json").write_text(
        json.dumps(manifest, indent=2)
        + "\n",
        encoding="utf-8",
    )

    completed = sum(
        row.get("status") == "completed"
        for row in screen_rows
    )
    failed_integrations = sum(
        row.get("status") == "failed"
        for row in screen_rows
    )
    clean = sum(
        row.get("response_class") == "clean_continuous"
        for row in screen_rows
    )
    impacts = sum(
        row.get("response_class") == "impact_reset"
        for row in screen_rows
    )
    print()
    print("HELIX SCALING SWEEP COMPLETE")
    print("=" * 72)
    print(f"completed screen cases: {completed}/{len(cases)}")
    print(f"integration/hybrid failures: {failed_integrations}")
    print(f"clean continuous: {clean}")
    print(f"impact/reset: {impacts}")
    print(f"selected paired validations: {len(selected_rows)}")
    print(f"output: {args.output_dir}")
    print()
    print(
        "Upload the ENTIRE output directory. The screen + threshold CSVs "
        "answer whether the Baja smallness survives increased I_M; the "
        "selected paired cases show how much those force corrections actually "
        "change the CVT trajectory."
    )

    if args.no_show:
        plt.close("all")
    else:
        plt.show()


if __name__ == "__main__":
    main()
