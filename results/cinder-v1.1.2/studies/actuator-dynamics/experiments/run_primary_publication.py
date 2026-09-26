"""Frozen primary-only baseline and fixed-input refinement for Results 4.4.1."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import time

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]
sys.path[:0] = [str(STUDY), str(RELEASE)]

import numpy as np
import cinder
from cinder.execution.hybrid.composed import ComposedCVTMode
from cinder.execution.hybrid.cvt_regime import CVTOperatingRegime
from cinder.model.cvt.contact.regime import ContactRegime
from infrastructure.study_support import verify_environment, load_study_modules
from experiments import run_controlled_transients as transient


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(gzip.compress(text.getvalue().encode(), mtime=0))


def export_result(out, result):
    ab, _ = load_study_modules()
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out/"trajectory.csv.gz", [s.row for s in result.samples])
    write_csv(out/"contributions.csv.gz", result.contribution_rows)
    events = ab.transition_rows(result)
    (out/"events.json").write_text(json.dumps(events, indent=2, allow_nan=True)+"\n")
    (out/"summary.json").write_text(json.dumps(result.metrics, indent=2, allow_nan=True)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=["baseline", "transient"], required=True)
    p.add_argument("--level", choices=["nominal", "tight"], required=True)
    p.add_argument("--variant", choices=["full", "qs"], required=True)
    p.add_argument("--output-dir", type=Path, default=STUDY/"artifacts/primary-publication")
    args = p.parse_args()
    verify_environment()
    cfg = json.loads((STUDY/"publication_inputs/primary_publication.json").read_text())
    ab, route = load_study_modules()
    variant = ab.VARIANTS[0 if args.variant == "full" else 1]
    settings = cfg["settings"][args.level]
    programme, resolved, assembly, engine, road = transient.build_components(ab, route, 10.0)
    out = args.output_dir/f"{args.kind}_{args.level}_{args.variant}"
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    print(f"START {out.name}", flush=True)
    if args.kind == "baseline":
        early = cfg["baseline_early_window_s"]
        result = ab.run_variant(
            variant=variant, full_assembly=assembly, engine=engine, road_load=road,
            constants=resolved.constants, programme=programme,
            duration_s=cfg["baseline_duration_s"], sample_step_s=cfg["baseline_report_step_s"],
            rtol=settings["rtol"], atol=settings["atol"], max_step_s=settings["max_step_s"],
            extra_sample_times=np.arange(early[0], early[1], cfg["baseline_early_report_step_s"]),
        )
        export_result(out, result)
    else:
        candidate = transient.Candidate(**cfg["candidate"])
        system = transient.build_perturbed_system(
            ab, route, variant, full_assembly=assembly, engine=engine,
            road_load=road, constants=resolved.constants, candidate=candidate,
        )
        initial = cfg["initial_states"][args.variant]
        cvt = ab.CVTState.from_vector(np.array(initial["cvt_vector"]))
        state = system.initial_state(cvt_state=cvt, host_state=system.host.initial_state(secondary_shaft_angle=initial["host_angle_rad"]))
        # A restart includes its contact mode. Reclassification from velocities
        # alone discards the archived sticking continuation's mode memory.
        mode = ComposedCVTMode(cvt=CVTOperatingRegime.engaged_free(contact_regime=ContactRegime.stick_stick()), host=None)
        if str(mode.cvt) != initial["expected_mode"]:
            raise RuntimeError("Recovered physical state did not recover its archived initial mode")
        restart = transient.Restart(variant.key, 50.0, 0.0, state, mode, 0.0, 0.0, cvt.shift_position*1000)
        for role, amplitude in [("stress", None), ("control", 0.0)]:
            result, error = transient.run_from_restart(
                ab, route, variant, restart, full_assembly=assembly, engine=engine, road_load=road,
                constants=resolved.constants, candidate=candidate, amplitude_override=amplitude,
                rtol=settings["rtol"], atol=settings["atol"], sample_step=cfg["transient_report_step_s"], screening=False,
            )
            if result is None:
                raise RuntimeError(error)
            export_result(out/role, result)
    sources = [*STUDY.glob("infrastructure/*.py"), *STUDY.glob("experiments/*.py"),
               *RELEASE.glob("defaults/**/*.py"), *RELEASE.glob("defaults/**/*.json"),
               STUDY/"study.json", STUDY/"publication_inputs/primary_publication.json"]
    manifest = {
        "kind": args.kind, "level": args.level, "variant": args.variant,
        "cinder_version": cinder.__version__, "cinder_path": str(Path(cinder.__file__).resolve()),
        "release_commit": cfg["release_commit"], "settings": settings,
        "transient_max_step_note": "Existing runner: min(1 ms, max(0.25 ms, ramp/8)); unchanged between tolerances.",
        "initial_state": cfg["initial_states"].get(args.variant) if args.kind == "transient" else "Existing launch: primary 1800 rpm, all other CVT velocities and shift zero; host angle zero.",
        "source_sha256": {str(x.relative_to(RELEASE)): hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(set(sources))},
        "elapsed_s": time.monotonic()-start,
    }
    (out/"provenance.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"DONE {out.name}: {manifest['elapsed_s']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
