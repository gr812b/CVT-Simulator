"""Replay selected secondary comparisons from archived states and audit wrap fields.

Run each kind/variant/level in a separate process: the two maintained studies
have intentionally separate modules named infrastructure. No live source is
imported; the release environment verifier runs before any mechanics.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]


def write_rows(path, rows):
    stream = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))


def audit_samples(system, samples):
    from cinder.results.inspection import inspect_cvt_state
    from cinder.results.fields import recover_belt_tension_boundaries
    from cinder.model.cvt.contact import ContactInterface

    rows = []
    for sample in samples:
        base = {k: sample.row[k] for k in ("time_s", "segment_index", "sample_location", "cvt_mode")}
        if sample.closure is None:
            rows.append(dict(base, engaged=False))
            continue
        vector = system.layout.view(sample.full_state, "cvt")
        inspection = inspect_cvt_state(
            system=system.cvt, time=sample.time, vector=vector,
            mode=sample.composed_mode.cvt,
            shaft_boundaries=system._shaft_boundaries(time=sample.time, state=sample.full_state),
            include_closure_audit=True,
        )
        contact = inspection.contact
        audit = inspection.closure_audit
        tension = recover_belt_tension_boundaries(inspection)
        if contact is None or audit is None or tension is None:
            raise RuntimeError("An engaged sample has no recovered contact/closure/tension")
        unknowns = audit.unknowns
        difference = np.max(np.abs(np.asarray(unknowns.as_tuple()) - np.asarray(sample.closure.as_tuple())))
        snap = contact.snapshot
        row = dict(base, engaged=True, closure_resolve_difference=float(difference))
        A = np.asarray(audit.matrix); b = np.asarray(audit.right_hand_side)
        row["balance_max_absolute_residual"] = float(np.max(np.abs(A @ np.asarray(unknowns.as_tuple()) - b)))
        for side in ("primary", "secondary"):
            interface = ContactInterface.PRIMARY if side == 'primary' else ContactInterface.SECONDARY
            row[side+'_relative_speed_m_s'] = float(contact.relative_motion.relative_speed_at(interface))
            row[side+'_lambda'] = float(getattr(contact.traction_utilization, side+'_lambda'))
            row[side+'_sticking'] = interface in contact.mode.sticking_interfaces
            radius = getattr(snap.geometry, side)
            rddot = radius.d2_center_of_mass_ds2 * snap.state.shift_speed**2 + radius.d_center_of_mass_ds * unknowns.shift_acceleration
            radial = snap.belt_linear_density * (snap.state.belt_speed**2 - radius.center_of_mass * rddot)
            tin = float(getattr(tension, side + "_in")); tout = float(getattr(tension, side + "_out"))
            row[side + "_min_tension_N"] = min(tin, tout)
            row[side + "_min_local_normal_N_per_rad"] = float((min(tin, tout) - radial) / np.sin(snap.sheave_half_angle))
            row[side + "_normal_N"] = float(getattr(contact, "normal_" + side))
        rows.append(row)
    engaged = [r for r in rows if r["engaged"]]
    minima = {key: min(r[key] for r in engaged) for key in (
        "primary_min_tension_N", "secondary_min_tension_N",
        "primary_min_local_normal_N_per_rad", "secondary_min_local_normal_N_per_rad")}
    summary = {"sample_count": len(rows), "engaged_count": len(engaged),
               "max_closure_resolve_difference": max(r["closure_resolve_difference"] for r in engaged),
               "max_balance_residual": max(r["balance_max_absolute_residual"] for r in engaged),
               "minima": minima,
               "negative_local_load_count": sum(min(r["primary_min_local_normal_N_per_rad"], r["secondary_min_local_normal_N_per_rad"]) < -1e-6 for r in engaged)}
    summary['initial_engaged_state'] = engaged[0]
    summary['first_negative_local_state'] = next((r for r in engaged if min(r['primary_min_local_normal_N_per_rad'],r['secondary_min_local_normal_N_per_rad']) < -1e-6), None)
    summary['maximum_sticking_speed_mismatch_m_s'] = max(abs(r[side+'_relative_speed_m_s']) for r in engaged for side in ('primary','secondary') if r[side+'_sticking'])
    summary['minimum_static_margin'] = min(.65-abs(r[side+'_lambda']) for r in engaged for side in ('primary','secondary') if r[side+'_sticking'])
    return rows, summary


def initial_state(system, vector):
    from cinder.model.system import CVTState
    return system.initial_state(cvt_state=CVTState.from_vector(np.asarray(vector)),
                                host_state=system.host.initial_state(secondary_shaft_angle=0.0))


def stick_mode():
    from cinder.execution.hybrid.composed import ComposedCVTMode
    from cinder.execution.hybrid.cvt_regime import CVTOperatingRegime
    from cinder.model.cvt.contact.regime import ContactRegime
    return ComposedCVTMode(cvt=CVTOperatingRegime.engaged_free(contact_regime=ContactRegime.stick_stick()), host=None)


def commercial(args, cfg, out):
    sys.path[:0] = [str(STUDY), str(STUDY / "commercial-case"), str(RELEASE)]
    import run_trajectory_demo as demo
    from infrastructure.study_support import load_study_modules
    ab, route = load_study_modules()
    ct = demo.ct
    _, resolved, base, engine, road = ct.build_components(ab, route, 10.0)
    # Read the explicitly registered inputs, not the baseline diagnostic columns.
    estimates = {"low": (0.0055559999999228, .06), "nominal": (0.0128750000004766, .05), "high": (0.0204689999995864, .045)}
    inertia, radius = estimates[args.estimate]
    assembly = demo.transplant_full_secondary(base, movable_inertia=inertia, helix_radius=radius, helix_angle_deg=31.0)
    if args.variant == "qs":
        assembly = demo.make_qs_helix_assembly(ab, assembly)
    variant = demo.identity_variant(ab, "publication_" + args.variant, args.variant)
    initial = cfg["commercial"][args.estimate][args.variant]
    candidate = ct.Candidate("secondary", 50.0, -120.0, .025, .05, .35)
    setup = dict(full_assembly=assembly, engine=engine, road_load=road, constants=resolved.constants, candidate=candidate)
    results = {}
    for role, amplitude in (("stress", None), ("control", 0.0)):
        system = ct.build_perturbed_system(ab, route, variant, **setup, amplitude_override=amplitude)
        mode = stick_mode()
        if str(mode.cvt) != initial["expected_mode"]:
            raise RuntimeError("Archived commercial mode does not match reconstructed mode")
        restart = ct.Restart(variant.key, 50.0, 0.0, initial_state(system, initial["cvt_vector"]), mode, 0., 0., initial["cvt_vector"][3]*1000)
        result, error = ct.run_from_restart(ab, route, variant, restart, **setup, amplitude_override=amplitude,
            rtol=args.rtol, atol=args.atol, sample_step=.0005, screening=False)
        if result is None:
            raise RuntimeError(error)
        target = out / role; target.mkdir(parents=True, exist_ok=True)
        write_rows(target / "trajectory.csv.gz", [s.row for s in result.samples])
        write_rows(target / "components.csv.gz", demo.secondary_dynamic_trace(result, 0.0))
        fresh = ct.build_perturbed_system(ab, route, variant, **setup, amplitude_override=amplitude)
        local, local_summary = audit_samples(fresh, result.samples)
        write_rows(target / "local_wrap_audit.csv.gz", local)
        (target / "events.json").write_text(json.dumps(ab.transition_rows(result), indent=2)+"\n")
        results[role] = {"completed": result.hybrid_result.completed, "end_s": float(result.samples[-1].time),
                         "segment_count": len(result.hybrid_result.segments), "local_audit": local_summary}
    return results, [STUDY / "commercial-case/run_trajectory_demo.py", STUDY / "experiments/run_controlled_transients.py", STUDY / "infrastructure/ablation_core.py"]


def paired(args, cfg, out):
    helix = RELEASE / "studies/helix-topology"
    sys.path[:0] = [str(helix), str(helix / "experiments"), str(RELEASE)]
    import run_paired_helix_performance as e58
    from infrastructure import study_support as hs
    ab, route = hs.load_study_modules()
    _, resolved, _, _, _ = hs.build_reference_components(route, duration_s=10.)
    study = json.loads((helix / "study.json").read_text())["experiments"]["paired_helix_performance"]
    initial = cfg["paired"][args.kind]
    case = next(c for c in e58._build_cases(study, quick=False) if c.case_id == initial["case_id"])
    if args.end_s is not None:
        case = replace(case, hold_s=args.end_s-case.onset_s-case.ramp_s)
    constants = resolved.constants
    full, engine, road = route.build_components(constants)
    # Current release inputs store preload on the actual force law, not on
    # the host constants. Update that law explicitly (the archived physics).
    from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator
    laws = [type(law)(spec=replace(law.spec, initial_twist=np.deg2rad(case.preload_deg)))
            if isinstance(law, HelicalTorqueReactionForce) else law
            for law in full.pulleys.secondary.actuator.force_laws]
    full = replace(full, pulleys=replace(full.pulleys, secondary=replace(
        full.pulleys.secondary, actuator=PulleyActuator(*laws))))
    if args.extra_compression_mm:
        from cinder.model.cvt.actuation.forces.axial_spring import AxialSpringForce
        laws = [type(law)(spec=replace(law.spec, initial_compression=law.spec.initial_compression+args.extra_compression_mm*.001))
                if isinstance(law, AxialSpringForce) else law for law in laws]
        full = replace(full, pulleys=replace(full.pulleys, secondary=replace(
            full.pulleys.secondary, actuator=PulleyActuator(*laws))))
    variant = next(v for v in ab.VARIANTS if v.key == ("full" if args.variant == "full" else "quasi_static_helix"))
    assembly = full if args.variant == "full" else ab.ablate_assembly(full, variant)
    programme = hs.flat_programme(route, case.onset_s + case.ramp_s + case.hold_s)
    p, s = e58._case_boundaries(case=case, route=route, engine=engine, road_load=road, constants=constants, programme=programme)
    def fresh():
        system, _ = hs.build_slotted_system(route=route, assembly=assembly, engine=engine, road_load=road,
            constants=constants, programme=programme, primary_boundary=p, secondary_boundary=s)
        system.cvt.deadzone_evaluator.belt_secondary_lock_absolute_tolerance = 1e-6
        return system
    mode = stick_mode()
    if str(mode.cvt) != initial["expected_mode"]:
        raise RuntimeError("Archived full restart mode does not match")
    restart = SimpleNamespace(full_state=initial_state(fresh(), initial["cvt_vector"]), mode=mode)
    solver = dict(study["solver"], relative_tolerance=args.rtol, absolute_tolerance=args.atol)
    if args.level == "tight":
        solver["maximum_step_cap_s"] *= .5
    args.actual_max_step = max(float(solver["minimum_max_step_s"]),
        min(float(solver["maximum_step_cap_s"]), case.ramp_s / float(solver["ramp_step_divisor"])))
    result = e58._run_variant_case(case=case, restart=restart, route=route, ab=ab,
        full_assembly=full, engine=engine, road_load=road, constants=constants, variant=variant, solver=solver,
        initial_mode_override=mode if args.sticking_start else None)
    write_rows(out / "trajectory.csv.gz", result.rows)
    local, local_summary = audit_samples(fresh(), result.samples)
    write_rows(out / "local_wrap_audit.csv.gz", local)
    events = [{"start_s": float(s.start_time), "end_s": float(s.end_time), "mode": str(s.mode),
               "events": list(s.fired_event_names)} for s in result.result.segments]
    (out / "events.json").write_text(json.dumps(events, indent=2)+"\n")
    return {"completed": result.result.completed, "termination_reason": str(result.result.termination_reason), "end_s": float(result.samples[-1].time),
            "segment_count": len(result.result.segments), "local_audit": local_summary}, [helix / "experiments/run_paired_helix_performance.py", helix / "infrastructure/helix_mechanics.py", helix / "infrastructure/study_support.py"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["commercial", "severe", "stock"], required=True)
    parser.add_argument("--variant", choices=["full", "qs"], required=True)
    parser.add_argument("--level", choices=["nominal", "tight"], required=True)
    parser.add_argument("--estimate", choices=["low", "nominal", "high"], default="nominal")
    parser.add_argument("--sticking-start", action="store_true", help="Preserve the supplied sticking mode for both models; audit initial traction and speed compatibility separately.")
    parser.add_argument("--extra-compression-mm", type=float, default=0., help="Explicit additional secondary spring compression for a follow-up, not an archive replay.")
    parser.add_argument("--end-s", type=float, help="Explicit common end time for a follow-up.")
    parser.add_argument("--output-dir", type=Path, default=STUDY / "artifacts/secondary-publication")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(RELEASE / "verify_environment.py")], check=True)
    import cinder
    args.rtol, args.atol = ((1e-4, 1e-7) if args.level == "nominal" else (1e-5, 1e-8))
    source = STUDY / "publication_inputs/secondary_initial_conditions.json"
    cfg = json.loads(source.read_text())
    name = f"{args.kind}_{args.estimate}_{args.level}_{args.variant}"
    if args.sticking_start:
        name += '_stick'
    if args.extra_compression_mm:
        name += f'_compression{args.extra_compression_mm:g}'
    if args.end_s is not None:
        name += f'_end{args.end_s:g}'
    out = args.output_dir / name; out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic(); print("START", name, flush=True)
    summary, sources = commercial(args, cfg, out) if args.kind == "commercial" else paired(args, cfg, out)
    sources += [Path(__file__), source, *RELEASE.glob("defaults/**/*.py"), *RELEASE.glob("defaults/**/*.json")]
    provenance = {"kind": args.kind, "variant": args.variant, "level": args.level, "estimate": args.estimate,
        "rtol": args.rtol, "atol": args.atol, "release_commit": cfg["release_commit"],
        "cinder_version": cinder.__version__, "cinder_path": str(Path(cinder.__file__).resolve()),
        "host_angle_policy": cfg["host_angle"],
        "sticking_start": args.sticking_start,
        "extra_compression_mm": args.extra_compression_mm, "requested_end_s": args.end_s,
        "max_step_s": .001 if args.kind == "commercial" else args.actual_max_step,
        "source_sha256": {str(p.relative_to(RELEASE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(sources))},
        "elapsed_s": time.monotonic() - start, "results": summary}
    (out / "summary.json").write_text(json.dumps(provenance, indent=2, allow_nan=False)+"\n")
    print("DONE", name, json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
