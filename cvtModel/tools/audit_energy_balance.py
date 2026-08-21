"""Run the baseline hill programme and audit CVT mechanical-energy closure.

The audit independently integrates

    external shaft work
      = stored-energy change + kinetic-slip dissipation
        + discrete impact/capture dissipation + numerical residual.

Discrete losses are read from the momentum-consistent impact projection
metadata.  Continuous slip power is recomputed from the physical contact
solution as ``-lambda N v_rel`` only at interfaces in kinetic slip.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_TOOLS = REPO_ROOT / "launchTools"
if str(LAUNCH_TOOLS) not in sys.path:
    sys.path.insert(0, str(LAUNCH_TOOLS))

import run_route_grade_response as route  # noqa: E402

from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid  # noqa: E402
from cinder.execution.hybrid.cvt_impact import (  # noqa: E402
    CVTVelocityTopology,
    kinetic_energy_for_topology,
)
from cinder.execution.hybrid.cvt_regime import CVTEngagementState  # noqa: E402
from cinder.model.cvt.actuation import (  # noqa: E402
    AxialSpringForce,
    HelicalTorqueReactionForce,
)
from cinder.model.cvt.contact import ContactInterface  # noqa: E402
from cinder.model.system import CVTState  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/energy_audit"))
    parser.add_argument("--rtol", type=float, default=1.0e-4)
    parser.add_argument("--atol", type=float, default=1.0e-7)
    parser.add_argument("--max-step", type=float, default=0.05)
    parser.add_argument("--audit-step", type=float, default=0.05)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    programme = route.GradeProgramme.default()
    candidate = route.load_candidate(
        LAUNCH_TOOLS / "presets" / "circular_traction_first_reference.json"
    )
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    system, _engine, _road = route.build_composed_system(
        resolved.constants,
        programme,
    )
    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(secondary_shaft_angle=0.0),
    )
    initial_mode = system.classify_initial_mode(initial_full)

    settings = HybridIntegratorSettings(
        relative_tolerance=args.rtol,
        absolute_tolerance=args.atol,
        method="LSODA",
        max_step=args.max_step,
        maximum_transitions=160,
        retain_dense_output=True,
    )
    result = integrate_hybrid(
        system=system,
        time_span=(0.0, 45.0),
        initial_state=initial_full,
        initial_mode=initial_mode,
        settings=settings,
    )
    if not result.completed:
        raise RuntimeError(result.termination_reason)

    impact_loss_total = sum(_impact_loss_from_transition(rec) for rec in result.transitions)

    initial_energy = stored_energy(
        system=system,
        time=0.0,
        full_state=initial_full,
        mode=initial_mode,
    )

    rows: list[dict[str, float | str]] = []
    cumulative_primary_work = 0.0
    cumulative_secondary_work = 0.0
    cumulative_external = 0.0
    cumulative_slip = 0.0

    for segment in result.segments:
        times = _segment_times(
            segment.start_time,
            segment.end_time,
            step=args.audit_step,
        )
        states = (
            segment.dense_state_at(times)
            if segment.has_dense_output
            else _linear_native_fallback(segment, times)
        )
        primary_power = np.empty(times.size, dtype=float)
        secondary_power = np.empty(times.size, dtype=float)
        external_power = np.empty(times.size, dtype=float)
        slip_power = np.empty(times.size, dtype=float)
        energies = np.empty(times.size, dtype=float)

        for i, (time_s, full_state) in enumerate(zip(times, states.T, strict=True)):
            boundaries = system._shaft_boundaries(time=float(time_s), state=full_state)
            cvt_vector = system.layout.view(full_state, "cvt")
            cvt_state = CVTState.from_vector(cvt_vector)
            primary_power[i] = (
                boundaries.primary.external_torque * cvt_state.primary_angular_speed
            )
            secondary_power[i] = (
                boundaries.secondary.external_torque * cvt_state.secondary_angular_speed
            )
            external_power[i] = primary_power[i] + secondary_power[i]
            slip_power[i] = kinetic_slip_dissipation_power(
                system=system,
                time=float(time_s),
                full_state=full_state,
                mode=segment.mode,
                boundaries=boundaries,
            )
            energies[i] = stored_energy(
                system=system,
                time=float(time_s),
                full_state=full_state,
                mode=segment.mode,
                boundaries=boundaries,
            )

        primary_increments = _cumulative_trapezoid(primary_power, times)
        secondary_increments = _cumulative_trapezoid(secondary_power, times)
        ext_increments = _cumulative_trapezoid(external_power, times)
        slip_increments = _cumulative_trapezoid(slip_power, times)
        for i, time_s in enumerate(times):
            impact_to_time = sum(
                _impact_loss_from_transition(rec)
                for rec in result.transitions
                if rec.time <= float(time_s) + 1.0e-12
            )
            primary_work = cumulative_primary_work + primary_increments[i]
            secondary_work = cumulative_secondary_work + secondary_increments[i]
            external_work = cumulative_external + ext_increments[i]
            slip_loss = cumulative_slip + slip_increments[i]
            stored_change = energies[i] - initial_energy
            residual = (
                external_work - stored_change - slip_loss - impact_to_time
            )
            rows.append(
                {
                    "time_s": float(time_s),
                    "mode": str(segment.mode.cvt),
                    "primary_work_J": float(primary_work),
                    "secondary_work_J": float(secondary_work),
                    "external_work_J": float(external_work),
                    "stored_energy_change_J": float(stored_change),
                    "slip_dissipation_J": float(slip_loss),
                    "impact_capture_dissipation_J": float(impact_to_time),
                    "balance_residual_J": float(residual),
                }
            )

        cumulative_primary_work += float(primary_increments[-1])
        cumulative_secondary_work += float(secondary_increments[-1])
        cumulative_external += float(ext_increments[-1])
        cumulative_slip += float(slip_increments[-1])

    # Remove repeated segment-boundary rows, keeping the later/post-transition
    # bookkeeping entry at the same timestamp.
    dedup: dict[float, dict[str, float | str]] = {}
    for row in rows:
        dedup[round(float(row["time_s"]), 12)] = row
    rows = list(dedup.values())
    rows.sort(key=lambda row: float(row["time_s"]))

    final_state = result.final_state
    final_mode = result.segments[-1].mode
    final_energy = stored_energy(
        system=system,
        time=result.final_time,
        full_state=final_state,
        mode=final_mode,
    )
    stored_change = final_energy - initial_energy
    residual = cumulative_external - stored_change - cumulative_slip - impact_loss_total

    print(f"completed: {result.completed} ({len(result.transitions)} transitions)")
    print(f"primary boundary work: {cumulative_primary_work/1000:.6f} kJ")
    print(f"secondary/road boundary work: {cumulative_secondary_work/1000:.6f} kJ")
    print(f"primary+secondary net external work: {cumulative_external/1000:.6f} kJ")
    print(f"kinetic-slip dissipation: {cumulative_slip/1000:.6f} kJ")
    print(f"discrete impact/capture dissipation: {impact_loss_total:.9f} J")
    print(f"stored-energy increase: {stored_change/1000:.6f} kJ")
    print(f"balance residual: {residual:.6f} J")
    print(
        "residual / |net external work|: "
        f"{100.0*abs(residual)/max(abs(cumulative_external),1.0):.6f}%"
    )

    csv_path = args.output_dir / "energy_audit_trace.csv"
    _write_rows(csv_path, rows)
    _plot_audit(args.output_dir, rows, result)
    _write_transition_audit(args.output_dir / "transition_energy_audit.csv", result)


def stored_energy(*, system, time: float, full_state, mode, boundaries=None) -> float:
    if boundaries is None:
        boundaries = system._shaft_boundaries(time=time, state=full_state)
    cvt_state = CVTState.from_vector(system.layout.view(full_state, "cvt"))
    topology = (
        CVTVelocityTopology.DEADZONE
        if mode.cvt.engagement is CVTEngagementState.DEADZONE
        else CVTVelocityTopology.ENGAGED
    )
    kinetic = kinetic_energy_for_topology(
        model=system.cvt.model,
        state=cvt_state,
        topology=topology,
        shaft_boundaries=boundaries,
    )
    primary_x, secondary_x = _local_axial_positions(
        model=system.cvt.model,
        state=cvt_state,
        topology=topology,
    )
    potential = _actuator_potential(
        model=system.cvt.model,
        side="primary",
        axial_position=primary_x,
    ) + _actuator_potential(
        model=system.cvt.model,
        side="secondary",
        axial_position=secondary_x,
    )
    return float(kinetic + potential)


def kinetic_slip_dissipation_power(*, system, time, full_state, mode, boundaries) -> float:
    if mode.cvt.engagement is CVTEngagementState.DEADZONE:
        return 0.0
    contact = mode.cvt.contact_regime
    assert contact is not None
    # Static contact transfers power but dissipates no interfacial work because
    # v_rel = 0.  Avoid needlessly re-solving the nonlinear contact closure for
    # the long stick-stick portions of the audit.
    if not contact.mode.slipping_interfaces:
        return 0.0
    physics = system.cvt._evaluate_physics(
        time=time,
        state=system.layout.view(full_state, "cvt"),
        mode=mode.cvt,
        shaft_boundaries=boundaries,
    )
    total = 0.0
    for interface in contact.mode.slipping_interfaces:
        if interface is ContactInterface.PRIMARY:
            lam = physics.traction_utilization.primary_lambda
        else:
            lam = physics.traction_utilization.secondary_lambda
        normal = physics.normal_at(interface)
        rel = physics.relative_motion.relative_speed_at(interface)
        power = -float(lam) * float(normal) * float(rel)
        # Tiny negative values can occur at an event endpoint where the kinetic
        # branch is about to reverse.  A materially negative value means the
        # imposed Coulomb direction is inconsistent and must not be hidden.
        if power < -1.0e-5:
            raise RuntimeError(
                f"Kinetic contact injected {power:.6g} W at t={time:.9g} s."
            )
        total += max(0.0, power)
    return total


def _local_axial_positions(*, model, state: CVTState, topology: CVTVelocityTopology):
    if topology is CVTVelocityTopology.ENGAGED:
        geometry = model.geometry.evaluate_engaged(state.shift_position)
        return (
            geometry.primary_axial_coordinate.value,
            geometry.secondary_axial_coordinate.value,
        )
    primary = model.geometry.evaluate_deadzone(state.shift_position)
    locked = model.geometry.evaluate_deadzone(model.geometry.spec.deadzone_shift)
    return (
        primary.primary_axial_coordinate.value,
        locked.secondary_axial_coordinate.value,
    )


def _actuator_potential(*, model, side: str, axial_position: float) -> float:
    actuator = model.primary_actuator if side == "primary" else model.secondary_actuator
    coupling = (
        model.primary_helical_coupling
        if side == "primary"
        else model.secondary_helical_coupling
    )
    energy = 0.0
    for law in actuator.force_laws:
        if isinstance(law, AxialSpringForce):
            spec = law.spec
            compression = (
                spec.initial_compression
                + spec.compression_per_axial_position * axial_position
            )
            energy += 0.5 * spec.stiffness * compression * compression
        elif isinstance(law, HelicalTorqueReactionForce):
            if coupling is None:
                raise RuntimeError("Helical force exists without coupling.")
            kinematics = coupling.evaluate_from_local_coordinate(
                axial_position=axial_position,
                d_axial_position_ds=0.0,
                d2_axial_position_ds2=0.0,
            )
            twist = law.spec.initial_twist - kinematics.theta
            energy += 0.5 * law.spec.torsional_stiffness * twist * twist
    return float(energy)


def _impact_loss_from_transition(record) -> float:
    metadata = record.transition.metadata
    cvt_meta = metadata.get("cvt", metadata)
    if not isinstance(cvt_meta, dict):
        return 0.0
    return float(cvt_meta.get("impact_dissipated_energy_J", 0.0))


def _segment_times(start: float, end: float, *, step: float) -> np.ndarray:
    if end <= start:
        return np.asarray((start,), dtype=float)
    count = max(1, int(np.floor((end - start) / step)))
    values = start + step * np.arange(count + 1, dtype=float)
    values = values[values < end]
    values = np.append(values, end)
    return values


def _cumulative_trapezoid(values: np.ndarray, times: np.ndarray) -> np.ndarray:
    output = np.zeros(values.size, dtype=float)
    if values.size > 1:
        output[1:] = np.cumsum(
            0.5 * (values[:-1] + values[1:]) * np.diff(times)
        )
    return output


def _linear_native_fallback(segment, times):
    return np.vstack(
        [np.interp(times, segment.time, row) for row in segment.state]
    )


def _write_rows(path: Path, rows: Iterable[dict[str, float | str]]) -> None:
    rows = list(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_transition_audit(path: Path, result) -> None:
    fields = [
        "time_s",
        "reason",
        "pre_kinetic_energy_J",
        "post_kinetic_energy_J",
        "dissipated_energy_J",
        "constraint_residual",
        "momentum_residual",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in result.transitions:
            meta = record.transition.metadata.get("cvt", record.transition.metadata)
            if not isinstance(meta, dict) or "impact_model" not in meta:
                continue
            writer.writerow(
                {
                    "time_s": record.time,
                    "reason": record.transition.reason,
                    "pre_kinetic_energy_J": meta["impact_pre_kinetic_energy_J"],
                    "post_kinetic_energy_J": meta["impact_post_kinetic_energy_J"],
                    "dissipated_energy_J": meta["impact_dissipated_energy_J"],
                    "constraint_residual": meta["impact_constraint_residual"],
                    "momentum_residual": meta["impact_momentum_residual"],
                }
            )


def _plot_audit(output_dir: Path, rows, result) -> None:
    time = np.asarray([float(row["time_s"]) for row in rows])
    primary = np.asarray([float(row["primary_work_J"]) for row in rows])
    secondary = np.asarray([float(row["secondary_work_J"]) for row in rows])
    external = np.asarray([float(row["external_work_J"]) for row in rows])
    stored = np.asarray([float(row["stored_energy_change_J"]) for row in rows])
    slip = np.asarray([float(row["slip_dissipation_J"]) for row in rows])
    impact = np.asarray([float(row["impact_capture_dissipation_J"]) for row in rows])
    residual = np.asarray([float(row["balance_residual_J"]) for row in rows])


    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(time, primary / 1000.0, label="Primary boundary work")
    ax.plot(time, secondary / 1000.0, label="Secondary / road boundary work")
    ax.plot(time, external / 1000.0, label="Net external work")
    ax.set(
        title="Boundary work carried through the CVT",
        xlabel="Time [s]",
        ylabel="Cumulative work [kJ]",
    )
    ax.axhline(0.0, linewidth=1.0)
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "energy_boundary_work.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(time, external / 1000.0, label="Net external work")
    ax.plot(time, stored / 1000.0, label="Stored mechanical energy")
    ax.plot(time, (stored + slip + impact) / 1000.0, label="Stored + modeled losses")
    ax.set(title="CINDER 45 s mechanical-energy audit", xlabel="Time [s]", ylabel="Cumulative energy [kJ]")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "energy_balance_cumulative.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(time, residual)
    ax.axhline(0.0, linewidth=1.0)
    ax.set(title="Energy-balance residual (magnified)", xlabel="Time [s]", ylabel="Residual [J]")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "energy_balance_residual.png", dpi=180)
    plt.close(fig)

    event_times = []
    event_losses = []
    for record in result.transitions:
        loss = _impact_loss_from_transition(record)
        if loss > 0.0:
            event_times.append(record.time)
            event_losses.append(loss)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    if event_times:
        ax.scatter(event_times, np.asarray(event_losses) * 1000.0)
        ax.set_yscale("log")
    ax.set(title="Discrete plastic capture / stop losses", xlabel="Time [s]", ylabel="Loss per event [mJ]")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "energy_discrete_event_losses.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
