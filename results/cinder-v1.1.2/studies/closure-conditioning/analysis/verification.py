"""Numerical cross-checks of retained arrays and selected frozen evidence."""
from __future__ import annotations
import numpy as np
from .evidence import read_json, rows, verify_record

NAMES = ("low_ratio_seat", "mid_shift", "upper_stop", "free_shift_opening_70")


def close(a, b, *, rtol=2e-9, atol=1e-10):
    if not np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True):
        raise ValueError(f"Evidence disagreement: {a!r} != {b!r}")


def verify_map(data, summary):
    n = int(summary["samples_per_axis"])
    if data["cond_A_scaled"].shape != (n,n) or len(data["lambda_p"]) != n or len(data["lambda_s"]) != n:
        raise ValueError("Wrong retained map resolution.")
    close(np.nanmax(data["cond_A_scaled"]), summary["A_scaled_condition_max"])
    close(np.nanpercentile(data["cond_A_scaled"], 99), summary["A_scaled_condition_p99"])
    if int(np.sum(data["rank_A"] < 8)) != int(summary["rank_deficient_grid_points"]):
        raise ValueError("Map rank counts disagree.")
    solved = np.isfinite(data["cond_A_scaled"])
    if int(solved.sum()) != round(float(summary["solved_fraction"])*n*n):
        raise ValueError("Missing map evaluations.")
    # Rebuild every physical-failure bit, retaining the historical mounted
    # contact guard rather than silently substituting a bilateral mask.
    code = np.zeros((n,n), dtype=np.int16)
    code[(data["N_p"]<0) | (data["N_s"]<0)] |= 1
    code[data["min_belt_tension"]<0] |= 2
    code[(data["min_local_normal_p"]<0) | (data["min_local_normal_s"]<0)] |= 4
    code[data["mechanism_margin"]<0] |= 8
    code[data["support_reaction"]<0] |= 16
    if not np.array_equal(code[solved], data["topology_failure_code"][solved]):
        raise ValueError("Stored admissibility mask contradicts signed mechanics.")
    if not np.array_equal(data["topology_admissible"], solved & (code==0)):
        raise ValueError("Wrong topology mask.")
    P,S = np.meshgrid(data["lambda_p"], data["lambda_s"])
    static = (P>=-.65)&(P<=.65)&(S>=-.65)&(S<=.65)&solved
    if not np.array_equal(data["static_capacity_admissible"], static):
        raise ValueError("Wrong static box.")
    if not np.array_equal(data["full_static_admissible"], static & (code==0)):
        raise ValueError("Static capacity was confused with mechanical admissibility.")
    return int(solved.sum())


def census(result, summary, actual):
    total, accepted, table = 0, 0, []
    if {r["state"] for r in result} != {r["state"] for r in summary}:
        raise ValueError("Census states missing.")
    for s in summary:
        selected = [r for r in result if r["state"] == s["state"]]
        good = [r for r in selected if r["accepted"]]
        if len(selected)!=49 or len(good)!=int(s["accepted_count"]):
            raise ValueError("735-start full census must not be replaced with quick starts.")
        starts = {(r["start_lambda_p"],r["start_lambda_s"]) for r in selected}
        expected = {(float(x),float(y)) for x in np.linspace(-.65,.65,7) for y in np.linspace(-.65,.65,7)}
        close(sorted(starts), sorted(expected))
        found = np.array([[r["root_lambda_p"],r["root_lambda_s"]] for r in good])
        a = actual[s["state"]]
        if np.max(np.linalg.norm(found-found[0],axis=1))>1e-6 or np.linalg.norm(found[0]-[a["lambda_p"],a["lambda_s"]])>1e-6:
            raise ValueError("Accepted roots are not one cluster at the recorded root.")
        if not all(r["statically_admissible"] and r["optimizer_success"] for r in good):
            raise ValueError("Accepted census root fails its reported checks.")
        table.append(dict(state=s["state"], starts=len(selected), accepted=len(good), not_accepted=len(selected)-len(good)))
        total += len(selected); accepted += len(good)
    if total!=735 or accepted!=666 or len(table)!=15:
        raise ValueError("Unexpected full census population.")
    return table


def expanded_census(result, summary, actual):
    table = []
    if len(result) != 324 or {r["state"] for r in result} != set(NAMES):
        raise ValueError("Expanded census is incomplete.")
    for s in summary:
        selected = [r for r in result if r["state"] == s["state"]]
        good = [r for r in selected if r["accepted"]]
        if len(selected) != 81 or len(good) != int(s["accepted_count"]):
            raise ValueError("Expanded start counts disagree.")
        expected = {(float(x),float(y)) for x in np.linspace(-2.6,2.6,9) for y in np.linspace(-2.6,2.6,9)}
        close(sorted((r["start_lambda_p"],r["start_lambda_s"]) for r in selected), sorted(expected))
        a = actual[s["state"]]
        found = np.array([[r["root_lambda_p"],r["root_lambda_s"]] for r in good])
        if np.max(np.linalg.norm(found-[a["lambda_p"],a["lambda_s"]],axis=1)) > 1e-6:
            raise ValueError("Expanded accepted roots differ from the physical-root cluster.")
        if not all(r["statically_admissible"] and r["optimizer_success"] for r in good):
            raise ValueError("Expanded accepted root fails reported checks.")
        table.append(dict(state=s["state"], starts=81, accepted=len(good), not_accepted=81-len(good)))
    if len(table) != 4 or sum(r["accepted"] for r in table) != 163:
        raise ValueError("Wrong expanded census population.")
    return table


def audit(artifacts):
    record = verify_record(artifacts)
    full = artifacts / "full"
    summary = read_json(full / "summary.json")
    actual = {r["label"]:r for r in rows(full / "actual_root_state_scan.csv")}
    result = rows(full / "multistart_results.csv")
    table = census(result, rows(full / "multistart_summary.csv"), actual)
    expanded = expanded_census(rows(full / "expanded_multistart_results.csv"),
                              rows(full / "expanded_multistart_summary.csv"), actual)
    maps, checked = [], 0
    for r in rows(full / "domain_conditioning_summary.csv"):
        with np.load(full / "states" / r["state"] / (r["domain"]+"_map.npz"), allow_pickle=False) as d:
            checked += verify_map(d, r)
            if r["domain"] == "physical":
                ij = np.unravel_index(np.nanargmax(d["cond_A_scaled"]), d["cond_A_scaled"].shape)
                maps.append(dict(state=r["state"], maximum=r["A_scaled_condition_max"],
                    root=actual[r["state"]]["A_condition_scaled"], samples=int(r["samples_per_axis"]),
                    max_lambda_p=float(d["lambda_p"][ij[1]]), max_lambda_s=float(d["lambda_s"][ij[0]]),
                    max_topology_failure_code=int(d["topology_failure_code"][ij]),
                    topology_admissible_fraction=r["topology_admissible_fraction"]))
    # Differentiate metadata is not proof: reconstruct singular diagnostics
    # directly from every retained 2x2 central-difference matrix.
    steps = rows(full / "root_jacobian_step_sweep.csv")
    for r in steps:
        if r["error"]:
            raise ValueError("Retained frozen-Jacobian step failed.")
        J = np.array([[r["J00"],r["J01"]],[r["J10"],r["J11"]]])
        sv = np.linalg.svd(J, compute_uv=False)
        close(sv, [r["sigma_max"],r["sigma_min"]])
        close(sv[0]/sv[-1],r["kappa"])
        close(np.linalg.det(J),r["determinant"])
    spans=[]
    for label in actual:
        group=[r for r in steps if r["state"]==label and 1e-6<=r["step"]<=3e-4]
        k=actual[label]["J_condition"]
        span=(max(r["kappa"] for r in group)-min(r["kappa"] for r in group))/max(abs(k),1)
        if span>1e-5 or actual[label]["J_definition"]!="central_difference_of_frozen_R_at_root":
            raise ValueError("Root-Jacobian plateau or definition failed.")
        spans.append(span)
    roots = rows(artifacts / "selected_audit/two_contact_roots.csv")
    curve = rows(artifacts / "selected_audit/fixed_primary_curve.csv")
    frozen = read_json(artifacts / "selected_audit/summary.json")
    for r in roots:
        if not r["physical"] or not r["bilateral_physical"] or r["A_rank"] != 8 or np.hypot(r["R_p"],r["R_s"])>1e-6:
            raise ValueError("Selected two-contact root failed.")
    close([r["primary_boundary_torque_Nm"] for r in roots], frozen["fixed_primary_torque_Nm"])
    close([r["secondary_boundary_torque_Nm"] for r in roots], frozen["selected_secondary_torque_Nm"])
    selected_steps = rows(artifacts / "selected_audit/root_jacobian_steps.csv")
    selected_spans = []
    for r in roots:
        step = [j for j in selected_steps if j["root_id"]==r["root_id"] and 1e-6<=j["step"]<=3e-4]
        span = (max(j["condition"] for j in step)-min(j["condition"] for j in step))/r["J_condition"]
        if span > 1e-4:
            raise ValueError("Selected root Jacobian is not on a finite-difference plateau.")
        selected_spans.append(span)
    # The fold is a torque extremum on an open branch, not an extra time state.
    lam=np.array([r["lambda_s"] for r in curve]); tq=np.array([r["secondary_boundary_torque_Nm"] for r in curve])
    if not np.all(np.diff(lam)>0):
        raise ValueError("Continuation coordinate is not ordered; do not join endpoints.")
    if not (roots[0]["lambda_s"]<frozen["fold"]["lambda_s"]<roots[1]["lambda_s"]):
        raise ValueError("Same two roots do not straddle the displayed fold.")
    if np.max(np.abs([[r["R_p"],r["R_s"]] for r in curve]))>1e-6:
        raise ValueError("Displayed curve is not corrected to sticking.")
    if not frozen["fold"]["physical"] or any(r["A_rank"] != 8 for r in curve):
        raise ValueError("Fold admissibility or displayed mechanical rank changed.")
    failed = [r for r in curve if not r["physical"]]
    if not failed or not all(r["topology_failure_code"] == 4 and r["min_local_normal_s_N_per_rad"]<0 for r in failed):
        raise ValueError("Dotted curve no longer represents secondary local-contact loss.")
    mixed = rows(artifacts / "selected_audit/one_contact_roots.csv")
    for r in mixed:
        if (abs(r["R_s"])>1e-6 or not r["physical"] or not r["bilateral_physical"]
                or not r["slip_direction_consistent"] or r["lambda_p"] != -.55):
            raise ValueError("Mixed root failed scalar or direction checks.")
    candidates=rows(artifacts / "one_contact/all_one_contact_fold_candidates.csv")
    states=rows(artifacts / "one_contact/states_scanned.csv")
    geometry={(r["state_id"],r["branch"],r["varied_torque"]) for r in candidates}
    if len(candidates)!=15 or len(states)!=62 or len(geometry)!=1:
        raise ValueError("Targeted mixed-search counts changed.")
    values=dict(run_id=record["run_id"], census=table, total_starts=735, accepted_starts=666,
        expanded_census=expanded, expanded_starts=324, expanded_accepted=163,
        map_values=maps, map_points_checked=checked, root_jacobian_matrices_checked=len(steps),
        max_root_jacobian_plateau_relative_span=max(spans), selected_roots=roots,
        max_selected_jacobian_plateau_relative_span=max(selected_spans),
        frozen=frozen, mixed_roots=mixed, mixed_search_states=62, mixed_candidate_rows=15,
        mixed_distinct_state_branch_geometries=1,
        no_transient_rerun=True, historical_quick_starts=375,
        superseded_static_map_maximum=338405.4991605586)
    return values, result, actual, curve
