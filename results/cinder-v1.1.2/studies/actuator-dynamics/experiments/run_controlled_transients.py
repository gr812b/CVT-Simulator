"""Equation-led controlled transient validation of actuator quasi-static limits.

The screen is not itself the result. It uses finite smooth shaft-torque ramps
from naturally reached engaged states to find cases whose *achieved* exact
dynamic correction numbers Pi_fw or Pi_h lie near prescribed levels.

Only clean-continuous full-model candidates are eligible for the official
validation set. Each selected case is then rerun with the corresponding
quasi-static actuator reduction and with a zero-perturbation control. The
reported trajectory consequence is a difference-in-differences:

    (QS_stress - QS_control) - (FULL_stress - FULL_control)

so pre-existing baseline offsets do not masquerade as stress-response error.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import ARTIFACTS, load_json, load_tagged_modules, verify_environment, write_rows  # noqa: E402

from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import SecondaryShaftAngleHost
from cinder.model.boundaries.shaft import FullThrottleEngineBoundary
from cinder.model.system import MechanicalCVTPlant, ShaftBoundaryValue


@dataclass(frozen=True)
class Restart:
    variant_key: str
    shift_percent: float
    time_s: float
    full_state: np.ndarray
    mode: object
    primary_rpm: float
    secondary_rpm: float
    shift_mm: float


@dataclass(frozen=True)
class Candidate:
    actuator: str
    shift_percent: float
    amplitude_Nm: float
    ramp_s: float
    onset_s: float
    hold_s: float

    @property
    def duration_s(self):
        return self.onset_s + self.ramp_s + self.hold_s

    @property
    def case_id(self):
        prefix = "P" if self.actuator == "primary" else "S"
        sign = "p" if self.amplitude_Nm >= 0 else "m"
        return (
            f"{prefix}_s{int(round(self.shift_percent)):02d}_"
            f"{sign}{abs(self.amplitude_Nm):g}_r{1000*self.ramp_s:g}ms"
        )


class SmoothStep:
    def __init__(self, onset_s: float, ramp_s: float, target: float):
        self.onset_s = float(onset_s)
        self.ramp_s = float(ramp_s)
        self.target = float(target)

    def value(self, t: float) -> float:
        if t <= self.onset_s:
            return 0.0
        if t >= self.onset_s + self.ramp_s:
            return self.target
        u = (t - self.onset_s) / self.ramp_s
        return self.target * u*u*(3.0 - 2.0*u)


class AddedTorqueBoundary:
    def __init__(self, base, signal: SmoothStep):
        self.base = base
        self.signal = signal

    def evaluate(self, context):
        base = self.base.evaluate(context)
        extra = self.signal.value(context.time)
        metadata = dict(base.metadata)
        metadata["actuator_validity_added_torque_Nm"] = extra
        return ShaftBoundaryValue(
            external_torque=base.external_torque + extra,
            equivalent_inertia=base.equivalent_inertia,
            metadata=metadata,
        )


def flat_programme(route, duration_s: float):
    return route.GradeProgramme(
        (
            route.GradePhase(
                name="flat",
                start_s=0.0,
                end_s=float(duration_s),
                start_degrees=0.0,
                end_degrees=0.0,
                transition=False,
            ),
        )
    )


def build_components(ab, route, duration_s: float):
    programme = flat_programme(route, duration_s)
    candidate = route.load_candidate(route.DEFAULT_FIXED_PIVOT_PRESET)
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    assembly, engine, road_load = route.build_components(resolved.constants)
    return programme, resolved, assembly, engine, road_load


def condition_variant(ab, route, variant, *, assembly, engine, road_load, constants, duration_s, rtol, atol):
    programme = flat_programme(route, duration_s)
    return ab.run_variant(
        variant=variant,
        full_assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        duration_s=duration_s,
        sample_step_s=0.001,
        rtol=rtol,
        atol=atol,
        max_step_s=0.005,
    )


def select_restart(result, target_percent: float) -> Restart:
    spec = result.system.cvt.model.geometry.spec
    span = spec.max_shift - spec.deadzone_shift
    choices = []
    for sample in result.samples:
        if sample.closure is None or sample.row.get("sample_location") != "interior":
            continue
        frac = 100.0 * (sample.cvt_state.shift_position - spec.deadzone_shift) / span
        if 1.0 < frac < 99.0:
            choices.append((abs(frac-target_percent), frac, sample))
    if not choices:
        raise RuntimeError(f"No interior engaged state for {result.variant.label}.")
    error, actual, sample = min(choices, key=lambda item: item[0])
    if error > 0.75:
        raise RuntimeError(
            f"{result.variant.label} did not reach {target_percent}% closely enough; "
            f"nearest was {actual:.3f}%."
        )
    return Restart(
        variant_key=result.variant.key,
        shift_percent=float(actual),
        time_s=float(sample.time),
        full_state=np.array(sample.full_state, dtype=float, copy=True),
        mode=sample.composed_mode,
        primary_rpm=float(sample.row["primary_rpm"]),
        secondary_rpm=float(sample.row["secondary_rpm"]),
        shift_mm=float(sample.row["shift_mm"]),
    )


def build_perturbed_system(ab, route, variant, *, full_assembly, engine, road_load, constants, candidate, amplitude_override=None):
    assembly = ab.ablate_assembly(full_assembly, variant)
    programme = flat_programme(route, candidate.duration_s)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    host = SecondaryShaftAngleHost()

    primary = FullThrottleEngineBoundary(
        engine,
        equivalent_rotational_inertia=constants.engine_rotational_inertia,
    )
    secondary = route.TimeProgrammedLockedFinalDriveBoundary(
        road_load=road_load,
        programme=programme,
        direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
    )

    amplitude = candidate.amplitude_Nm if amplitude_override is None else float(amplitude_override)
    signal = SmoothStep(candidate.onset_s, candidate.ramp_s, amplitude)
    if candidate.actuator == "primary":
        primary = AddedTorqueBoundary(primary, signal)
    else:
        secondary = AddedTorqueBoundary(secondary, signal)

    return ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=primary,
        secondary_boundary=secondary,
        host=host,
    )


def run_from_restart(ab, route, variant, restart, *, full_assembly, engine, road_load, constants, candidate, amplitude_override, rtol, atol, sample_step, screening):
    system = build_perturbed_system(
        ab, route, variant,
        full_assembly=full_assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        candidate=candidate,
        amplitude_override=amplitude_override,
    )
    max_step = min(
        0.003 if screening else 0.001,
        max(0.00025, candidate.ramp_s / (5.0 if screening else 8.0)),
    )
    result = integrate_hybrid(
        system=system,
        time_span=(0.0, candidate.duration_s),
        initial_state=np.array(restart.full_state, dtype=float, copy=True),
        initial_mode=restart.mode,
        settings=HybridIntegratorSettings(
            relative_tolerance=rtol,
            absolute_tolerance=atol,
            method="LSODA",
            max_step=max_step,
            maximum_transitions=250,
            retain_dense_output=True,
        ),
    )
    if not result.completed:
        return None, result.termination_reason

    samples, contributions = ab.sample_variant(
        variant=variant,
        system=system,
        result=result,
        step_s=sample_step,
    )
    wrapped = ab.VariantResult(
        variant=variant,
        assembly=ab.ablate_assembly(full_assembly, variant),
        system=system,
        hybrid_result=result,
        samples=samples,
        contribution_rows=contributions,
        metrics=ab.compute_metrics(
            variant, result, samples, system.cvt.model.geometry.spec.max_shift
        ),
    )
    return wrapped, None


def response_class(result, onset_s):
    post = [r for r in result.hybrid_result.transitions if r.time >= onset_s]
    if any(r.transition.has_successor_state for r in post):
        return "impact_reset"
    if post:
        return "contact_switching"
    return "clean_continuous"


def dynamic_number_rows(result, candidate):
    rows = [
        s.row for s in result.samples
        if s.closure is not None and s.time >= candidate.onset_s
    ]
    vals = []
    components = []
    for row in rows:
        if candidate.actuator == "primary":
            num = float(row["fly_dynamic_total_correction_N"])
            den = float(row["fly_qs_centrifugal_force_N"])
            parts = (
                float(row["fly_dynamic_axial_inertia_force_N"]),
                float(row["fly_dynamic_curvature_force_N"]),
            )
        else:
            num = float(row["helix_dynamic_total_correction_N"])
            den = float(row["helix_qs_reaction_force_N"])
            parts = (
                float(row["helix_dynamic_shaft_accel_force_N"]),
                float(row["helix_dynamic_shift_accel_force_N"]),
                float(row["helix_dynamic_curvature_force_N"]),
            )
        if math.isfinite(num) and math.isfinite(den) and abs(den) > 1.0e-9:
            vals.append(abs(num/den))
            components.append(parts)
    return np.asarray(vals, dtype=float), components


def screen_candidate(ab, route, full_variant, restart, *, assembly, engine, road_load, constants, candidate, cfg):
    result, error = run_from_restart(
        ab, route, full_variant, restart,
        full_assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        candidate=candidate,
        amplitude_override=None,
        rtol=float(cfg["screen_solver"]["relative_tolerance"]),
        atol=float(cfg["screen_solver"]["absolute_tolerance"]),
        sample_step=float(cfg["screen_solver"]["sample_step_s"]),
        screening=True,
    )
    base = {
        "case_id": candidate.case_id,
        "actuator": candidate.actuator,
        "restart_target_shift_percent": candidate.shift_percent,
        "restart_actual_shift_percent": restart.shift_percent,
        "amplitude_Nm": candidate.amplitude_Nm,
        "ramp_s": candidate.ramp_s,
        "onset_s": candidate.onset_s,
        "hold_s": candidate.hold_s,
    }
    if result is None:
        return {**base, "status": "failed", "error": error}

    vals, _ = dynamic_number_rows(result, candidate)
    return {
        **base,
        "status": "completed",
        "response_class": response_class(result, candidate.onset_s),
        "peak_dynamic_number": float(np.max(vals)) if vals.size else float("nan"),
        "p95_dynamic_number": float(np.percentile(vals, 95)) if vals.size else float("nan"),
        "transition_count_after_onset": sum(
            r.time >= candidate.onset_s for r in result.hybrid_result.transitions
        ),
        "reset_count_after_onset": sum(
            r.time >= candidate.onset_s and r.transition.has_successor_state
            for r in result.hybrid_result.transitions
        ),
    }


def select_targets(screen_rows, actuator: str, targets, *, maximum_relative_error: float):
    pool = [
        r for r in screen_rows
        if r.get("actuator") == actuator
        and r.get("status") == "completed"
        and r.get("response_class") == "clean_continuous"
        and math.isfinite(float(r.get("peak_dynamic_number", float("nan"))))
        and float(r["peak_dynamic_number"]) > 0.0
    ]
    selected = []
    used = set()
    for target in targets:
        candidates = []
        for row in pool:
            if row["case_id"] in used:
                continue
            achieved = float(row["peak_dynamic_number"])
            distance = abs(math.log10(achieved / float(target)))
            candidates.append((distance, row))
        if not candidates:
            selected.append({
                "actuator": actuator,
                "target_dynamic_number": float(target),
                "selection_status": "unreached_no_clean_continuous_candidate",
            })
            continue
        _, row = min(candidates, key=lambda item: item[0])
        achieved = float(row["peak_dynamic_number"])
        relative_error = abs(achieved-float(target))/float(target)
        if relative_error > maximum_relative_error:
            selected.append({
                "actuator": actuator,
                "target_dynamic_number": float(target),
                "selection_status": "unreached_outside_target_tolerance",
                "nearest_case_id": row["case_id"],
                "nearest_achieved_dynamic_number": achieved,
                "nearest_relative_target_error": relative_error,
            })
            continue
        used.add(row["case_id"])
        selected.append({
            **row,
            "target_dynamic_number": float(target),
            "selection_log10_error": abs(math.log10(achieved/float(target))),
            "selection_relative_target_error": relative_error,
            "selection_status": "selected",
        })
    return selected


def _series(result, key):
    by_t = {}
    for s in result.samples:
        try:
            v = float(s.row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(v):
            by_t[float(s.time)] = v
    t = np.asarray(sorted(by_t), dtype=float)
    v = np.asarray([by_t[x] for x in t], dtype=float)
    return t, v


def paired_metric(stress_full, control_full, stress_qs, control_qs, *, onset, sample_step):
    end = min(
        stress_full.hybrid_result.final_time,
        control_full.hybrid_result.final_time,
        stress_qs.hybrid_result.final_time,
        control_qs.hybrid_result.final_time,
    )
    grid = np.arange(onset, end + 0.5*sample_step, sample_step)
    fields = {
        "shift_mm": "shift_mm",
        "primary_rpm": "primary_rpm",
        "secondary_rpm": "secondary_rpm",
        "primary_clamp_N": "primary_actuator_closing_force_N",
        "secondary_clamp_N": "secondary_actuator_closing_force_N",
        "normal_primary_N": "normal_primary_N",
        "normal_secondary_N": "normal_secondary_N",
    }
    out = {}
    for label, key in fields.items():
        series = [_series(r, key) for r in (stress_full, control_full, stress_qs, control_qs)]
        if any(t.size < 2 for t, _ in series):
            out[f"max_abs_paired_delta_{label}"] = float("nan")
            out[f"rms_paired_delta_{label}"] = float("nan")
            continue
        lo = max(onset, *(float(t[0]) for t,_ in series))
        hi = min(end, *(float(t[-1]) for t,_ in series))
        g = grid[(grid >= lo) & (grid <= hi)]
        fs, fc, qs, qc = [
            np.interp(g, t, v) for t, v in series
        ]
        delta = (qs-qc) - (fs-fc)
        out[f"max_abs_paired_delta_{label}"] = float(np.max(np.abs(delta)))
        out[f"rms_paired_delta_{label}"] = float(np.sqrt(np.mean(delta**2)))
    return out


def candidate_from_row(row):
    return Candidate(
        actuator=str(row["actuator"]),
        shift_percent=float(row["restart_target_shift_percent"]),
        amplitude_Nm=float(row["amplitude_Nm"]),
        ramp_s=float(row["ramp_s"]),
        onset_s=float(row["onset_s"]),
        hold_s=float(row["hold_s"]),
    )


def validate_selection(ab, route, row, *, variants, restarts, assembly, engine, road_load, constants, cfg, out):
    if row.get("selection_status") != "selected":
        return {**row, "validation_status": "not_run"}

    candidate = candidate_from_row(row)
    full = variants["full"]
    qs_key = "quasi_static_flyweight" if candidate.actuator == "primary" else "quasi_static_helix"
    qs = variants[qs_key]
    solver = cfg["validation_solver"]
    ss = float(solver["sample_step_s"])

    results = {}
    for key, variant in (("full", full), ("qs", qs)):
        restart = restarts[variant.key][candidate.shift_percent]
        stress, error = run_from_restart(
            ab, route, variant, restart,
            full_assembly=assembly, engine=engine, road_load=road_load,
            constants=constants, candidate=candidate,
            amplitude_override=None,
            rtol=float(solver["relative_tolerance"]),
            atol=float(solver["absolute_tolerance"]),
            sample_step=ss, screening=False,
        )
        if stress is None:
            return {**row, "validation_status": "failed", "error": f"{key} stress: {error}"}
        control, error = run_from_restart(
            ab, route, variant, restart,
            full_assembly=assembly, engine=engine, road_load=road_load,
            constants=constants, candidate=candidate,
            amplitude_override=0.0,
            rtol=float(solver["relative_tolerance"]),
            atol=float(solver["absolute_tolerance"]),
            sample_step=ss, screening=False,
        )
        if control is None:
            return {**row, "validation_status": "failed", "error": f"{key} control: {error}"}
        results[f"{key}_stress"] = stress
        results[f"{key}_control"] = control

    vals, _ = dynamic_number_rows(results["full_stress"], candidate)
    metrics = paired_metric(
        results["full_stress"], results["full_control"],
        results["qs_stress"], results["qs_control"],
        onset=candidate.onset_s,
        sample_step=ss,
    )

    case_dir = out / "selected-cases" / candidate.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    # Rich trajectory rows for later paper plots.
    all_rows = []
    for label, result in results.items():
        for sample in result.samples:
            r = dict(sample.row)
            r["run_role"] = label
            r["case_id"] = candidate.case_id
            all_rows.append(r)
    write_rows(case_dir / "trajectory.csv", all_rows)

    return {
        **row,
        "validation_status": "completed",
        "validated_peak_dynamic_number": float(np.max(vals)) if vals.size else float("nan"),
        "full_response_class": response_class(results["full_stress"], candidate.onset_s),
        "qs_response_class": response_class(results["qs_stress"], candidate.onset_s),
        **metrics,
    }


def plot_screen(rows, actuator, out):
    subset = [
        r for r in rows
        if r.get("actuator") == actuator and r.get("status") == "completed"
    ]
    if not subset:
        return
    for shift in sorted(set(float(r["restart_target_shift_percent"]) for r in subset)):
        group = [r for r in subset if float(r["restart_target_shift_percent"]) == shift]
        fig, ax = plt.subplots(figsize=(8.6, 5.6))
        for sign, marker, label in ((1.0, "o", "positive torque"), (-1.0, "s", "negative torque")):
            g = [r for r in group if math.copysign(1.0, float(r["amplitude_Nm"])) == sign]
            if not g:
                continue
            x = [1000.0*float(r["ramp_s"]) for r in g]
            y = [abs(float(r["amplitude_Nm"])) for r in g]
            c = [math.log10(max(float(r["peak_dynamic_number"]), 1e-8)) for r in g]
            scatter = ax.scatter(x, y, c=c, marker=marker, s=55, label=label)
        ax.set_xscale("log")
        ax.set_xlabel("Torque-ramp duration [ms]")
        ax.set_ylabel("|Added shaft torque| [N m]")
        ax.set_title(f"{actuator.capitalize()} coupling: achieved dynamic number at {shift:g}% shift")
        ax.grid(True, alpha=0.25)
        ax.legend()
        cb = fig.colorbar(scatter, ax=ax)
        cb.set_label(r"$\log_{10}(\Pi)$")
        fig.tight_layout()
        fig.savefig(out / f"{actuator}_screen_shift_{int(round(shift)):02d}.png", dpi=180)
        plt.close(fig)


def plot_validation(rows, out):
    complete = [r for r in rows if r.get("validation_status") == "completed"]
    if not complete:
        return
    for actuator in ("primary", "secondary"):
        group = [r for r in complete if r["actuator"] == actuator]
        if not group:
            continue

        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        x = [float(r["validated_peak_dynamic_number"]) for r in group]
        y = [float(r["max_abs_paired_delta_shift_mm"]) for r in group]
        ax.scatter(x, y, s=70)
        for r, xx, yy in zip(group, x, y):
            ax.annotate(
                f"target {100*float(r['target_dynamic_number']):g}%, achieved {100*xx:.3g}%",
                (xx, yy),
                xytext=(5, 4),
                textcoords="offset points",
                fontsize=8,
            )
        ax.set_xscale("log")
        ax.set_xlabel(r"Achieved peak dynamic number $\Pi$")
        ax.set_ylabel("Max paired shift-response difference [mm]")
        ax.set_title(f"{actuator.capitalize()} coupling: constitutive correction vs trajectory consequence")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(out / f"{actuator}_dynamic_number_vs_shift_response.png", dpi=180)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        y = [float(r["max_abs_paired_delta_primary_rpm"]) for r in group]
        ax.scatter(x, y, s=70)
        for r, xx, yy in zip(group, x, y):
            ax.annotate(
                f"target {100*float(r['target_dynamic_number']):g}%, achieved {100*xx:.3g}%",
                (xx, yy),
                xytext=(5, 4),
                textcoords="offset points",
                fontsize=8,
            )
        ax.set_xscale("log")
        ax.set_xlabel(r"Achieved peak dynamic number $\Pi$")
        ax.set_ylabel("Max paired primary-speed response difference [rpm]")
        ax.set_title(f"{actuator.capitalize()} coupling: constitutive correction vs shaft response")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(out / f"{actuator}_dynamic_number_vs_primary_rpm_response.png", dpi=180)
        plt.close(fig)


def main() -> int:
    verify_environment()
    spec = load_json(STUDY_ROOT / "study.json")
    cfg = spec["experiments"]["controlled_transients"]
    out = ARTIFACTS / "controlled-transients"
    out.mkdir(parents=True, exist_ok=True)

    _, ab, route = load_tagged_modules()
    _, resolved, assembly, engine, road_load = build_components(
        ab, route, float(cfg["conditioning_duration_s"])
    )

    variants = {v.key: v for v in ab.VARIANTS}
    needed = ("full", "quasi_static_flyweight", "quasi_static_helix")

    # Natural baseline conditioning states for each comparator.
    conditioning = {}
    restarts = {}
    for key in needed:
        v = variants[key]
        print(f"Conditioning {v.label}...")
        result = condition_variant(
            ab, route, v,
            assembly=assembly, engine=engine, road_load=road_load,
            constants=resolved.constants,
            duration_s=float(cfg["conditioning_duration_s"]),
            rtol=float(cfg["validation_solver"]["relative_tolerance"]),
            atol=float(cfg["validation_solver"]["absolute_tolerance"]),
        )
        conditioning[key] = result
        restarts[key] = {}
        for pct in cfg["restart_shift_percents"]:
            r = select_restart(result, float(pct))
            # Key by requested target, not achieved fraction, so model-specific
            # natural states pair cleanly at the same nominal shift fraction.
            restarts[key][float(pct)] = r

    restart_rows = []
    for key, by_pct in restarts.items():
        for target, r in by_pct.items():
            restart_rows.append({
                "variant": key,
                "requested_shift_percent": target,
                "actual_shift_percent": r.shift_percent,
                "conditioning_time_s": r.time_s,
                "primary_rpm": r.primary_rpm,
                "secondary_rpm": r.secondary_rpm,
                "shift_mm": r.shift_mm,
            })
    write_rows(out / "restart_states.csv", restart_rows)

    # Equation-led screen: physical axes are applied torque and ramp time; the
    # selection coordinate is achieved Pi, not an arbitrary ranking score.
    candidates = []
    for pct in cfg["restart_shift_percents"]:
        for ramp in cfg["ramp_times_s"]:
            for amp in cfg["primary_added_torques_Nm"]:
                candidates.append(Candidate(
                    "primary", float(pct), float(amp), float(ramp),
                    float(cfg["onset_s"]), float(cfg["hold_s"])
                ))
            for amp in cfg["secondary_added_torques_Nm"]:
                candidates.append(Candidate(
                    "secondary", float(pct), float(amp), float(ramp),
                    float(cfg["onset_s"]), float(cfg["hold_s"])
                ))

    screen_rows = []
    full_variant = variants["full"]
    for i, candidate in enumerate(candidates, 1):
        print(f"[screen {i}/{len(candidates)}] {candidate.case_id}")
        restart = restarts["full"][candidate.shift_percent]
        try:
            screen_rows.append(screen_candidate(
                ab, route, full_variant, restart,
                assembly=assembly, engine=engine, road_load=road_load,
                constants=resolved.constants, candidate=candidate, cfg=cfg,
            ))
        except Exception as exc:
            screen_rows.append({
                "case_id": candidate.case_id,
                "actuator": candidate.actuator,
                "restart_target_shift_percent": candidate.shift_percent,
                "amplitude_Nm": candidate.amplitude_Nm,
                "ramp_s": candidate.ramp_s,
                "status": "analysis_failed",
                "error": f"{type(exc).__name__}: {exc}",
            })
    write_rows(out / "screen.csv", screen_rows)
    plot_screen(screen_rows, "primary", out)
    plot_screen(screen_rows, "secondary", out)

    targets_by_actuator = cfg["target_dynamic_numbers_by_actuator"]
    max_rel = float(cfg["maximum_relative_target_error"])
    selections = (
        select_targets(screen_rows, "primary", [float(x) for x in targets_by_actuator["primary"]], maximum_relative_error=max_rel)
        + select_targets(screen_rows, "secondary", [float(x) for x in targets_by_actuator["secondary"]], maximum_relative_error=max_rel)
    )
    write_rows(out / "selected_cases.csv", selections)

    validated = []
    for row in selections:
        print(
            f"[validate] {row.get('actuator')} target="
            f"{row.get('target_dynamic_number')} case={row.get('case_id')}"
        )
        validated.append(validate_selection(
            ab, route, row,
            variants=variants, restarts=restarts,
            assembly=assembly, engine=engine, road_load=road_load,
            constants=resolved.constants, cfg=cfg, out=out,
        ))
    write_rows(out / "validation_summary.csv", validated)
    plot_validation(validated, out)

    summary = {
        "screen_candidate_count": len(candidates),
        "completed_screen_count": sum(r.get("status") == "completed" for r in screen_rows),
        "clean_continuous_count": sum(
            r.get("status") == "completed" and r.get("response_class") == "clean_continuous"
            for r in screen_rows
        ),
        "selection_policy": cfg["selection_policy"],
        "selected": selections,
        "validated": validated,
        "interpretation": (
            "The screen is experiment design. The scientific outputs are the achieved "
            "dimensionless correction values and the controlled full-vs-QS response differences "
            "for the validated selected cases."
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=True) + "\n")
    print(f"Wrote controlled-transient validity study to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
