"""Shared helpers for the exploratory helix contact-topology study."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

STUDY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = STUDY_ROOT.parents[1]
ARTIFACTS = STUDY_ROOT / "artifacts"
STUDY_FILE = STUDY_ROOT / "study.json"
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
EXPECTED_VERSION = "1.1.2"

if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_environment() -> None:
    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    import cinder
    if cinder.__version__ != EXPECTED_VERSION:
        raise RuntimeError(
            f"Expected cinder-cvt=={EXPECTED_VERSION}, found {cinder.__version__} "
            f"from {Path(cinder.__file__).resolve()}."
        )


def reset_artifacts() -> None:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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


def build_reference_components(route, *, duration_s: float):
    programme = flat_programme(route, duration_s)
    candidate = route.load_candidate(route.DEFAULT_FIXED_PIVOT_PRESET)
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    assembly, engine, road_load = route.build_components(resolved.constants)
    return programme, resolved, assembly, engine, road_load


class SmoothStep:
    """C1 smooth step used for controlled secondary-torque perturbations."""

    def __init__(self, *, onset_s: float, ramp_s: float, target: float):
        self.onset_s = float(onset_s)
        self.ramp_s = float(ramp_s)
        self.target = float(target)
        if self.ramp_s <= 0.0:
            raise ValueError("ramp_s must be positive")

    def value(self, time_s: float) -> float:
        t = float(time_s)
        if t <= self.onset_s:
            return 0.0
        if t >= self.onset_s + self.ramp_s:
            return self.target
        u = (t - self.onset_s) / self.ramp_s
        return self.target * u * u * (3.0 - 2.0 * u)


class AddedTorqueBoundary:
    """Add a prescribed torque signal to an existing shaft boundary."""

    def __init__(self, base, signal: SmoothStep, *, label: str = "added_torque"):
        self.base = base
        self.signal = signal
        self.label = str(label)

    def evaluate(self, context):
        from cinder.model.system import ShaftBoundaryValue

        base = self.base.evaluate(context)
        extra = self.signal.value(context.time)
        metadata = dict(base.metadata)
        metadata[f"helix_topology_{self.label}_Nm"] = extra
        return ShaftBoundaryValue(
            external_torque=base.external_torque + extra,
            equivalent_inertia=base.equivalent_inertia,
            metadata=metadata,
        )


class BlendToTorqueBoundary:
    """Smoothly replace a base boundary's torque with an absolute target.

    Before ``onset_s`` the base boundary is unchanged.  During the ramp its
    external torque is blended to ``target_torque_Nm`` while its equivalent
    inertia is retained.  This is useful for a controlled full-throttle to
    engine-braking transition without inventing a second engine model.
    """

    def __init__(
        self,
        base,
        *,
        onset_s: float,
        ramp_s: float,
        target_torque_Nm: float,
        label: str = "target_torque",
    ):
        self.base = base
        self.blend = SmoothStep(onset_s=onset_s, ramp_s=ramp_s, target=1.0)
        self.target_torque_Nm = float(target_torque_Nm)
        self.label = str(label)

    def evaluate(self, context):
        from cinder.model.system import ShaftBoundaryValue

        base = self.base.evaluate(context)
        w = self.blend.value(context.time)
        torque = (1.0 - w) * base.external_torque + w * self.target_torque_Nm
        metadata = dict(base.metadata)
        metadata[f"helix_topology_{self.label}_blend_fraction"] = w
        metadata[f"helix_topology_{self.label}_Nm"] = self.target_torque_Nm
        return ShaftBoundaryValue(
            external_torque=torque,
            equivalent_inertia=base.equivalent_inertia,
            metadata=metadata,
        )


class BlendTorqueScaleBoundary:
    """Smoothly scale an existing shaft boundary torque.

    The underlying boundary is unchanged before ``onset_s``.  During the
    transition its torque is multiplied by a factor moving smoothly from 1 to
    ``target_scale`` while the boundary inertia and metadata are preserved.
    This is useful for throttle-chop / torque-rise experiments where the
    perturbation should remain relative to the local engine torque curve.
    """

    def __init__(
        self,
        base,
        *,
        onset_s: float,
        ramp_s: float,
        target_scale: float,
        label: str = "torque_scale",
    ):
        self.base = base
        self.blend = SmoothStep(onset_s=onset_s, ramp_s=ramp_s, target=1.0)
        self.target_scale = float(target_scale)
        self.label = str(label)

    def evaluate(self, context):
        from cinder.model.system import ShaftBoundaryValue

        base = self.base.evaluate(context)
        w = self.blend.value(context.time)
        scale = (1.0 - w) + w * self.target_scale
        metadata = dict(base.metadata)
        metadata[f"helix_topology_{self.label}_blend_fraction"] = w
        metadata[f"helix_topology_{self.label}"] = scale
        return ShaftBoundaryValue(
            external_torque=scale * base.external_torque,
            equivalent_inertia=base.equivalent_inertia,
            metadata=metadata,
        )


class PrescribedTorqueBoundary:
    """Standalone smooth torque boundary for bench-style discovery cases."""

    def __init__(
        self,
        *,
        equivalent_inertia: float,
        onset_s: float,
        ramp_s: float,
        target_torque_Nm: float,
        initial_torque_Nm: float = 0.0,
        label: str = "prescribed_torque",
    ):
        self.equivalent_inertia = float(equivalent_inertia)
        self.initial_torque_Nm = float(initial_torque_Nm)
        self.target_torque_Nm = float(target_torque_Nm)
        self.blend = SmoothStep(onset_s=onset_s, ramp_s=ramp_s, target=1.0)
        self.label = str(label)

    def evaluate(self, context):
        from cinder.model.system import ShaftBoundaryValue

        w = self.blend.value(context.time)
        torque = (1.0 - w) * self.initial_torque_Nm + w * self.target_torque_Nm
        return ShaftBoundaryValue(
            external_torque=torque,
            equivalent_inertia=self.equivalent_inertia,
            metadata={
                f"helix_topology_{self.label}_blend_fraction": w,
                f"helix_topology_{self.label}_Nm": torque,
            },
        )


def build_slotted_system(
    *,
    route,
    assembly,
    engine,
    road_load,
    constants,
    programme,
    added_secondary_torque: SmoothStep | None = None,
    primary_boundary=None,
    secondary_boundary=None,
):
    """Build a composed system using the shared results slotted helix policy."""

    from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
    from cinder.hosts import SecondaryShaftAngleHost
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary
    from cinder.model.system import MechanicalCVTPlant
    from defaults.reference_model import (
        reference_model_status,
        use_bilateral_secondary_helix,
    )

    plant = MechanicalCVTPlant.from_assembly(assembly)
    use_bilateral_secondary_helix(plant)
    topology_status = reference_model_status(plant)
    host = SecondaryShaftAngleHost()
    primary = primary_boundary
    if primary is None:
        primary = FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        )
    secondary = secondary_boundary
    if secondary is None:
        secondary = route.TimeProgrammedLockedFinalDriveBoundary(
            road_load=road_load,
            programme=programme,
            direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
        )
    if added_secondary_torque is not None:
        secondary = AddedTorqueBoundary(
            secondary, added_secondary_torque, label="added_secondary_torque"
        )

    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=primary,
        secondary_boundary=secondary,
        host=host,
    )
    return system, topology_status


@dataclass(slots=True)
class SlottedRun:
    system: object
    result: object
    samples: list[Any]
    contribution_rows: list[dict[str, Any]]
    topology_status: object


def integrate_system(
    *,
    system,
    initial_state,
    initial_mode,
    duration_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
    maximum_transitions: int = 250,
):
    from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid

    return integrate_hybrid(
        system=system,
        time_span=(0.0, float(duration_s)),
        initial_state=initial_state,
        initial_mode=initial_mode,
        settings=HybridIntegratorSettings(
            relative_tolerance=float(rtol),
            absolute_tolerance=float(atol),
            method="LSODA",
            max_step=float(max_step_s),
            maximum_transitions=int(maximum_transitions),
            retain_dense_output=True,
        ),
    )


def _full_variant(ab):
    return next(item for item in ab.VARIANTS if item.key == "full")


def _sample_result_with_fresh_system(
    *,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    programme,
    result,
    sample_step_s: float,
    added_secondary_torque: SmoothStep | None = None,
    primary_boundary=None,
    secondary_boundary=None,
    deadzone_lock_absolute_tolerance: float | None = None,
):
    """Sample an integrated result with a fresh contact evaluator.

    The engaged-contact evaluator intentionally caches continuation data for
    nonlinear stick solves.  Reusing the *integration* system for a reporting
    pass starts the chronological resampling at t=0 with continuation data
    left over from the end of the trajectory.  In multi-root regions that can
    select a different algebraic closure even though the stored state and mode
    are unchanged.

    Build an equivalent fresh system, then let ``sample_variant`` walk the
    retained dense trajectory forward in time.  The reporting continuation is
    therefore reconstructed in the same temporal direction as integration.
    """

    reporting_system, _ = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        added_secondary_torque=added_secondary_torque,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
    )
    if deadzone_lock_absolute_tolerance is not None:
        reporting_system.cvt.deadzone_evaluator.belt_secondary_lock_absolute_tolerance = float(
            deadzone_lock_absolute_tolerance
        )
    samples, contributions = ab.sample_variant(
        variant=_full_variant(ab),
        system=reporting_system,
        result=result,
        step_s=sample_step_s,
    )
    augment_helix_contact_rows(samples, reporting_system.cvt.model)
    return reporting_system, samples, contributions


def _assert_restart_reporting_consistency(
    *,
    restart: "Restart",
    samples: list[Any],
    margin_tolerance_Nm: float = 1.0e-5,
) -> None:
    """Guard unchanged-boundary restarts against algebraic branch drift.

    The caller may use this only when the boundary at scenario t=0 is exactly
    the same as at the conditioning state.  A mismatch means that a restart or
    reporting solve selected a different contact-closure branch, in which case
    the candidate metrics are not trustworthy.
    """

    expected = restart.baseline_margin_Nm
    if expected is None:
        return
    first = next(
        (sample for sample in samples if abs(float(sample.time)) <= 1.0e-12),
        None,
    )
    if first is None:
        raise RuntimeError("Restart reporting produced no t=0 sample.")
    actual = finite_float(first.row.get("helix_reacted_torque_margin_Nm"))
    if actual is None or abs(actual - expected) > margin_tolerance_Nm:
        raise RuntimeError(
            "Restart closure mismatch at t=0: expected baseline helix margin "
            f"{expected:.9g} N m, reporting recovered {actual!r} N m. "
            "This indicates algebraic contact-closure branch drift; candidate "
            "metrics must not be used."
        )


def augment_helix_contact_rows(samples: list[Any], model) -> list[dict[str, Any]]:
    """Add the exact production reacted-torque decomposition to sample rows."""

    from cinder.model.cvt.actuation import HelicalTorqueReactionForce

    laws = [
        law for law in model.secondary_actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(f"Expected exactly one secondary helix law; found {len(laws)}")
    helix = laws[0]
    inertia = float(model.inertias.secondary.movable_sheave_rotational_inertia)

    rows: list[dict[str, Any]] = []
    for sample in samples:
        row = sample.row
        closure = sample.closure
        if closure is None:
            row.update(
                {
                    "helix_belt_reaction_torque_Nm": float("nan"),
                    "helix_torsional_spring_torque_Nm": float("nan"),
                    "helix_shaft_accel_reaction_torque_Nm": float("nan"),
                    "helix_shift_accel_reaction_torque_Nm": float("nan"),
                    "helix_curvature_reaction_torque_Nm": float("nan"),
                    "helix_reacted_torque_margin_Nm": float("nan"),
                    "helix_motion_ratio_rad_per_m": float("nan"),
                    "helix_force_reconstruction_N": float("nan"),
                    "helix_force_reconstruction_residual_N": float("nan"),
                    "helix_opposite_flank_required": "",
                    "helix_secondary_closure_torque_Nm": float("nan"),
                    "helix_secondary_angular_acceleration_rad_s2": float("nan"),
                    "helix_shift_acceleration_m_s2": float("nan"),
                    "helix_secondary_internal_power_W": float("nan"),
                }
            )
            rows.append(row)
            continue

        theta = float(row["helix_theta_rad"])
        dtheta_ds = float(row["helix_dtheta_ds_rad_per_m"])
        d2theta_ds2 = float(row["helix_d2theta_ds2_rad_per_m2"])
        sdot = float(row["shift_speed_m_s"])
        sddot = float(closure.shift_acceleration)
        alpha_s = float(closure.secondary_angular_acceleration)
        tau_s = float(closure.secondary_torque)

        belt_torque = helix.spec.movable_member_torque_fraction * tau_s
        spring_torque = helix.spec.torsional_stiffness * (
            helix.spec.initial_twist - theta
        )
        shaft_inertia_torque = -inertia * alpha_s
        shift_inertia_torque = -inertia * dtheta_ds * sddot
        curvature_inertia_torque = -inertia * d2theta_ds2 * sdot**2
        margin = (
            belt_torque
            + spring_torque
            + shaft_inertia_torque
            + shift_inertia_torque
            + curvature_inertia_torque
        )

        dx_ds = float(row["secondary_dx_ds"])
        motion_ratio = dtheta_ds / dx_ds if abs(dx_ds) > 1.0e-15 else float("nan")
        reconstructed_force = margin * motion_ratio
        reported_force = float(row["helix_full_reaction_force_N"])
        residual = reported_force - reconstructed_force

        row.update(
            {
                "helix_belt_reaction_torque_Nm": belt_torque,
                "helix_torsional_spring_torque_Nm": spring_torque,
                "helix_shaft_accel_reaction_torque_Nm": shaft_inertia_torque,
                "helix_shift_accel_reaction_torque_Nm": shift_inertia_torque,
                "helix_curvature_reaction_torque_Nm": curvature_inertia_torque,
                "helix_reacted_torque_margin_Nm": margin,
                "helix_motion_ratio_rad_per_m": motion_ratio,
                "helix_force_reconstruction_N": reconstructed_force,
                "helix_force_reconstruction_residual_N": residual,
                "helix_opposite_flank_required": int(margin < 0.0),
                "helix_secondary_closure_torque_Nm": tau_s,
                "helix_secondary_angular_acceleration_rad_s2": alpha_s,
                "helix_shift_acceleration_m_s2": sddot,
                "helix_secondary_internal_power_W": (
                    tau_s * float(sample.cvt_state.secondary_angular_speed)
                ),
            }
        )
        rows.append(row)
    return rows


def run_flat_slotted_reference(
    *,
    duration_s: float,
    sample_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
):
    ab, route = load_study_modules()
    programme, resolved, assembly, engine, road_load = build_reference_components(
        route, duration_s=duration_s
    )
    system, topology_status = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=resolved.constants,
        programme=programme,
    )
    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(secondary_shaft_angle=0.0),
    )
    result = integrate_system(
        system=system,
        initial_state=initial_full,
        initial_mode=system.classify_initial_mode(initial_full),
        duration_s=duration_s,
        rtol=rtol,
        atol=atol,
        max_step_s=max_step_s,
    )
    if not result.completed:
        raise RuntimeError("Slotted reference launch failed: " + result.termination_reason)

    reporting_system, samples, contributions = _sample_result_with_fresh_system(
        route=route,
        ab=ab,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=resolved.constants,
        programme=programme,
        result=result,
        sample_step_s=sample_step_s,
    )
    return (
        SlottedRun(
            system=reporting_system,
            result=result,
            samples=samples,
            contribution_rows=contributions,
            topology_status=topology_status,
        ),
        resolved,
        assembly,
        engine,
        road_load,
        ab,
        route,
    )


def run_flat_slotted_reference_with_constants(
    *,
    route,
    ab,
    constants,
    duration_s: float,
    sample_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
):
    """Run a flat slotted conditioning launch for an explicit constants set.

    This is the coupled-hardware counterpart to ``run_flat_slotted_reference``:
    callers may change a physical constant (for example secondary torsional
    preload), rebuild the entire assembly, and then let that hardware develop
    its own launch / ratio history before selecting restart states.
    """

    programme = flat_programme(route, duration_s)
    assembly, engine, road_load = route.build_components(constants)
    system, topology_status = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
    )
    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(secondary_shaft_angle=0.0),
    )
    result = integrate_system(
        system=system,
        initial_state=initial_full,
        initial_mode=system.classify_initial_mode(initial_full),
        duration_s=duration_s,
        rtol=rtol,
        atol=atol,
        max_step_s=max_step_s,
    )
    if not result.completed:
        return None, result, assembly, engine, road_load, topology_status

    reporting_system, samples, contributions = _sample_result_with_fresh_system(
        route=route,
        ab=ab,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        result=result,
        sample_step_s=sample_step_s,
    )
    return (
        SlottedRun(
            system=reporting_system,
            result=result,
            samples=samples,
            contribution_rows=contributions,
            topology_status=topology_status,
        ),
        result,
        assembly,
        engine,
        road_load,
        topology_status,
    )

@dataclass(frozen=True)
class Restart:
    target_shift_percent: float
    actual_shift_percent: float
    time_s: float
    full_state: Any
    mode: object
    baseline_margin_Nm: float | None = None


def select_restart(run: SlottedRun, target_percent: float, *, maximum_error_percent=1.0):
    import numpy as np

    spec = run.system.cvt.model.geometry.spec
    span = spec.max_shift - spec.deadzone_shift
    choices = []
    for sample in run.samples:
        if sample.closure is None:
            continue
        frac = 100.0 * (sample.cvt_state.shift_position - spec.deadzone_shift) / span
        if 0.5 < frac < 99.5:
            choices.append((abs(frac - target_percent), frac, sample))
    if not choices:
        raise RuntimeError(f"No engaged interior state found for {target_percent}% restart")
    error, actual, sample = min(choices, key=lambda item: item[0])
    if error > maximum_error_percent:
        raise RuntimeError(
            f"Nearest state to {target_percent}% shift was {actual:.3f}% "
            f"(error {error:.3f}%)."
        )
    return Restart(
        target_shift_percent=float(target_percent),
        actual_shift_percent=float(actual),
        time_s=float(sample.time),
        full_state=np.array(sample.full_state, dtype=float, copy=True),
        mode=sample.composed_mode,
        baseline_margin_Nm=finite_float(
            sample.row.get("helix_reacted_torque_margin_Nm")
        ),
    )


def run_secondary_torque_probe(
    *,
    route,
    ab,
    restart: Restart,
    assembly,
    engine,
    road_load,
    constants,
    added_torque_Nm: float,
    onset_s: float,
    ramp_s: float,
    hold_s: float,
    sample_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
):
    duration_s = float(onset_s + ramp_s + hold_s)
    programme = flat_programme(route, duration_s)
    signal = SmoothStep(
        onset_s=onset_s,
        ramp_s=ramp_s,
        target=added_torque_Nm,
    )
    system, topology_status = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        added_secondary_torque=signal,
    )
    # Added secondary torque is exactly zero at t=0, so preserve the
    # naturally reached hybrid mode from conditioning.
    initial_mode = restart.mode
    result = integrate_system(
        system=system,
        initial_state=restart.full_state,
        initial_mode=initial_mode,
        duration_s=duration_s,
        rtol=rtol,
        atol=atol,
        max_step_s=max_step_s,
    )
    if not result.completed:
        return None, result, topology_status

    reporting_system, samples, contributions = _sample_result_with_fresh_system(
        route=route,
        ab=ab,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        result=result,
        sample_step_s=sample_step_s,
        added_secondary_torque=signal,
    )
    _assert_restart_reporting_consistency(restart=restart, samples=samples)
    return (
        SlottedRun(
            system=reporting_system,
            result=result,
            samples=samples,
            contribution_rows=contributions,
            topology_status=topology_status,
        ),
        result,
        topology_status,
    )


def transient_grade_programme(
    route,
    *,
    onset_s: float,
    ramp_s: float,
    hold_s: float,
    target_degrees: float,
):
    """Flat hold -> smooth grade ramp -> constant-grade hold."""

    t0 = 0.0
    t1 = float(onset_s)
    t2 = t1 + float(ramp_s)
    t3 = t2 + float(hold_s)
    return route.GradeProgramme(
        (
            route.GradePhase(
                name="pre-transient flat",
                start_s=t0,
                end_s=t1,
                start_degrees=0.0,
                end_degrees=0.0,
                transition=False,
            ),
            route.GradePhase(
                name="grade transition",
                start_s=t1,
                end_s=t2,
                start_degrees=0.0,
                end_degrees=float(target_degrees),
                transition=True,
            ),
            route.GradePhase(
                name="grade hold",
                start_s=t2,
                end_s=t3,
                start_degrees=float(target_degrees),
                end_degrees=float(target_degrees),
                transition=False,
            ),
        )
    )


def select_dynamic_restart(
    run: SlottedRun,
    *,
    minimum_shift_percent: float = 5.0,
    maximum_shift_percent: float = 95.0,
):
    """Select the naturally reached state with the strongest helix dynamics.

    The score is the sum of absolute shaft-acceleration, shift-acceleration,
    and curvature reacted-torque terms.  This deliberately complements the
    ratio-based restarts used by the ordinary torque screen.
    """

    import numpy as np

    spec = run.system.cvt.model.geometry.spec
    span = spec.max_shift - spec.deadzone_shift
    candidates = []
    for sample in run.samples:
        if sample.closure is None:
            continue
        frac = 100.0 * (sample.cvt_state.shift_position - spec.deadzone_shift) / span
        if not minimum_shift_percent <= frac <= maximum_shift_percent:
            continue
        row = sample.row
        try:
            terms = (
                float(row["helix_shaft_accel_reaction_torque_Nm"]),
                float(row["helix_shift_accel_reaction_torque_Nm"]),
                float(row["helix_curvature_reaction_torque_Nm"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in terms):
            continue
        score = sum(abs(x) for x in terms)
        candidates.append((score, frac, sample))
    if not candidates:
        raise RuntimeError("No engaged interior state was available for dynamic restart selection.")
    score, actual, sample = max(candidates, key=lambda item: item[0])
    restart = Restart(
        target_shift_percent=float(actual),
        actual_shift_percent=float(actual),
        time_s=float(sample.time),
        full_state=np.array(sample.full_state, dtype=float, copy=True),
        mode=sample.composed_mode,
        baseline_margin_Nm=finite_float(
            sample.row.get("helix_reacted_torque_margin_Nm")
        ),
    )
    return restart, float(score)


def run_custom_restart_case(
    *,
    route,
    ab,
    restart: Restart,
    assembly,
    engine,
    road_load,
    constants,
    programme,
    duration_s: float,
    sample_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
    primary_boundary=None,
    secondary_boundary=None,
    reclassify_initial_mode: bool = False,
    deadzone_lock_absolute_tolerance: float | None = None,
):
    """Integrate one arbitrary slotted-topology restart experiment.

    Reuse the restart's exact hybrid mode when the new boundary is identical at
    ``t=0``.  When a scenario intentionally swaps the boundary at the restart
    instant (the bench families), request reclassification under the new
    boundary instead.
    """

    system, topology_status = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
    )
    if deadzone_lock_absolute_tolerance is not None:
        system.cvt.deadzone_evaluator.belt_secondary_lock_absolute_tolerance = float(
            deadzone_lock_absolute_tolerance
        )
    initial_mode = (
        system.classify_initial_mode(restart.full_state)
        if reclassify_initial_mode
        else restart.mode
    )
    result = integrate_system(
        system=system,
        initial_state=restart.full_state,
        initial_mode=initial_mode,
        duration_s=duration_s,
        rtol=rtol,
        atol=atol,
        max_step_s=max_step_s,
    )
    if not result.completed:
        return None, result, topology_status

    reporting_system, samples, contributions = _sample_result_with_fresh_system(
        route=route,
        ab=ab,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        result=result,
        sample_step_s=sample_step_s,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
        deadzone_lock_absolute_tolerance=deadzone_lock_absolute_tolerance,
    )
    if not reclassify_initial_mode:
        _assert_restart_reporting_consistency(restart=restart, samples=samples)
    return (
        SlottedRun(
            system=reporting_system,
            result=result,
            samples=samples,
            contribution_rows=contributions,
            topology_status=topology_status,
        ),
        result,
        topology_status,
    )


def run_slotted_full_launch_programme(
    *,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    programme,
    duration_s: float,
    sample_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
    maximum_transitions: int = 500,
):
    """Run one full natural launch under an arbitrary slotted route programme.

    Unlike the short restart screens, this preserves the complete causal history
    leading into the disturbance.  It is used to replay legacy hill studies
    whose pre-hill vehicle/CVT state may be essential to the helix reaction
    reversal.  Reporting again uses a fresh evaluator so nonlinear-contact
    continuation is rebuilt chronologically.
    """

    system, topology_status = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
    )
    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(secondary_shaft_angle=0.0),
    )
    result = integrate_system(
        system=system,
        initial_state=initial_full,
        initial_mode=system.classify_initial_mode(initial_full),
        duration_s=duration_s,
        rtol=rtol,
        atol=atol,
        max_step_s=max_step_s,
        maximum_transitions=maximum_transitions,
    )
    if not result.completed:
        return None, result, topology_status

    reporting_system, samples, contributions = _sample_result_with_fresh_system(
        route=route,
        ab=ab,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        result=result,
        sample_step_s=sample_step_s,
    )
    return (
        SlottedRun(
            system=reporting_system,
            result=result,
            samples=samples,
            contribution_rows=contributions,
            topology_status=topology_status,
        ),
        result,
        topology_status,
    )

def finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def write_reference_provenance(directory: Path, *, plant, extra=None) -> Path:
    from defaults.reference_model import write_reference_model_provenance

    return write_reference_model_provenance(
        Path(directory), plant=plant, extra=extra
    )


def load_study_modules():
    """Return helix-study mechanics and shared Baja defaults."""
    from . import helix_mechanics as ab
    from defaults.baja import reference as route
    return ab, route


def copy_provenance() -> None:
    out = ARTIFACTS / "provenance"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STUDY_FILE, out / "study.json")
    policy = RELEASE_ROOT / "defaults" / "reference_model" / "policy.json"
    if policy.is_file():
        shutil.copy2(policy, out / "reference_model_policy.json")
