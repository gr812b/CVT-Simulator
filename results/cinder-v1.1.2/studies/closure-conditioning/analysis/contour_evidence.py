"""Contact masks for the publication contours, using frozen CINDER 1.1.2.

The two retained vehicle maps do not need a rerun: every previously rejected
point has an independent belt/support failure. Removing only the secondary
helix inequality therefore cannot change either mask, and never drops a
primary-contact failure. The focused two-root grid needs fresh contact data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from .evidence import (REPO, digest, input_paths, read_json, rows, verify_record,
                       write_json)


def retained_mask(data):
    """Prove equality for these maps; do not merely discard mechanism bit 8."""
    code = data["topology_failure_code"]
    independent = ((data["N_p"] < 0) | (data["N_s"] < 0)
        | (data["min_belt_tension"] < 0) | (data["min_local_normal_p"] < 0)
        | (data["min_local_normal_s"] < 0) | (data["support_reaction"] < 0))
    if not np.array_equal(code != 0, independent):
        raise ValueError("Legacy actuator guard cannot be separated by this proof at this state.")
    # Previously accepted points passed BOTH actuator guards. Previously
    # rejected points still fail a guard unchanged by the bilateral wrapper.
    return data["full_static_admissible"].copy()


def prepare_contours(cc, artifacts):
    from .frozen_audit import FrozenFamily, utilization
    prior = verify_record(artifacts)
    out = artifacts / "contour_audit"
    if out.exists():
        raise FileExistsError(f"Keep existing contour evidence intact: {out}")
    inputs = {p.relative_to(REPO).as_posix(): p.read_bytes() for p in input_paths()}
    out.mkdir(parents=True)
    masks = {}
    for name in ("upper_stop", "mid_shift"):
        with np.load(artifacts / "full/states" / name / "physical_map.npz") as d:
            good = retained_mask(d)
            masks[name] = {"points": int(good.size), "admissible": int(good.sum()),
                "changed_from_historical_mask": 0,
                "proof": "Every rejected point independently fails belt loading or support; every accepted point passes both historical actuator guards."}

    library = read_json(artifacts / "full/summary.json")["shared_case_library"]
    c = rows(artifacts / "two_contact/candidate.csv")[0]
    family = FrozenFamily(cc, c, library, c["refined_Tp_Nm"], c["refined_Ts_Nm"], bilateral=True)
    bundle = family.base
    model = bundle.system.cvt.model
    pc = model.primary_actuation_context(time=0., state=bundle.cvt, geometry=bundle.snapshot.geometry)
    sc = model.secondary_actuation_context(time=0., state=bundle.cvt, geometry=bundle.snapshot.geometry)
    with np.load(artifacts / "selected_audit/focused_residual_map.npz") as old:
        lp, ls = old["lambda_p"].copy(), old["lambda_s"].copy()
        original = np.stack((old["R_p"], old["R_s"]))
    shape = (len(ls), len(lp))
    keys = ("R_p", "R_s", "N_p", "N_s", "min_belt_tension", "min_local_normal_p",
            "min_local_normal_s", "primary_contact_margin", "secondary_contact_margin",
            "cond_A_scaled", "rank_A")
    arrays = {k: np.empty(shape) for k in keys}
    arrays["topology_failure_code"] = np.empty(shape, dtype=np.int16)
    for i, y in enumerate(ls):
        if i % 40 == 0:
            print(f"Focused contact audit: row {i+1}/{len(ls)}", flush=True)
        for j, x in enumerate(lp):
            u = utilization(x, y)
            t = family.at(bundle, x, y, diagnostics=True)
            code, extra = cc.topology_failure_code(bundle.ref, bundle.sample, t, u, bundle.snapshot)
            z = t.closure.unknowns
            p = model.primary_actuator.compressive_contact_margins(pc, z)
            s = model.secondary_actuator.compressive_contact_margins(sc, z)
            values = {"R_p": t.relative_motion.primary_relative_acceleration,
                "R_s": t.relative_motion.secondary_relative_acceleration,
                "N_p": z.primary_normal_resultant, "N_s": z.secondary_normal_resultant,
                "primary_contact_margin": min((v for _, v in p), default=np.inf),
                "secondary_contact_margin": min((v for _, v in s), default=np.inf),
                "cond_A_scaled": t.closure.scaled_condition_number, "rank_A": t.closure.matrix_rank,
                **extra, "topology_failure_code": code}
            for key in arrays:
                arrays[key][i, j] = values[key]
    # Same literal state, loads, equations and coordinates as the old grid.
    delta = float(np.max(np.abs(np.stack((arrays["R_p"], arrays["R_s"])) - original)))
    if not np.allclose(np.stack((arrays["R_p"], arrays["R_s"])), original, rtol=2e-10, atol=2e-8):
        raise ValueError("Fresh contour no longer represents the retained residual field.")
    arrays.update(lambda_p=lp, lambda_s=ls,
        admissible=(arrays["topology_failure_code"] == 0)
            & (np.abs(lp)[None, :] <= .65) & (np.abs(ls)[:, None] <= .65))
    np.savez_compressed(out / "focused_contact_map.npz", **arrays)
    write_json(out / "checks.json", {"retained_maps": masks,
        "focused_grid_points": int(np.prod(shape)), "focused_residual_max_abs_difference": delta,
        "focused_admissible_points": int(arrays["admissible"].sum()),
        "primary_guard_retained": True, "secondary_guard": "bilateral zero-clearance slot",
        "transients_rerun": 0, "full_maps_rerun": 0, "multistart_searches_rerun": 0})
    for name, content in inputs.items():
        path = out / "execution_inputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if (REPO / name).read_bytes() != content:
            raise ValueError(f"Input changed during contour audit: {name}")
    hashes = {n: hashlib.sha256(b).hexdigest() for n, b in inputs.items()}
    outputs = {p.name: digest(p) for p in out.iterdir() if p.is_file()}
    identity = hashlib.sha256(json.dumps({"inputs": hashes, "outputs": outputs}, sort_keys=True).encode()).hexdigest()
    write_json(out / "execution_provenance.json", {"run_id": "closure-contours-" + identity[:16],
        "parent_execution": prior["run_id"], "mechanics_version": "1.1.2",
        "mechanics_commit": prior["mechanics_commit"],
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "input_sha256": hashes, "output_sha256": outputs})
    print(f"Contour evidence prepared: {out}", flush=True)


def verify_contours(artifacts):
    out = artifacts / "contour_audit"
    record = verify_record(out)
    for name in ("upper_stop", "mid_shift"):
        with np.load(artifacts / "full/states" / name / "physical_map.npz") as d:
            retained_mask(d)
    with np.load(out / "focused_contact_map.npz") as d:
        code = np.zeros(d["R_p"].shape, dtype=np.int16)
        code[(d["N_p"] < 0) | (d["N_s"] < 0)] |= 1
        code[d["min_belt_tension"] < 0] |= 2
        code[(d["min_local_normal_p"] < 0) | (d["min_local_normal_s"] < 0)] |= 4
        code[(d["primary_contact_margin"] < 0) | (d["secondary_contact_margin"] < 0)] |= 8
        if not np.array_equal(code, d["topology_failure_code"]):
            raise ValueError("Focused contact mask contradicts its signed fields.")
        if not np.array_equal(code == 0, d["admissible"]):
            raise ValueError("Focused admissibility mask differs from its physical checks.")
    return record
