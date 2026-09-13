"""Diagnose the weak 8x8 closure direction at selected lambda-plane ridge points.

This is a lightweight post-processing companion to ``run.py``.  It reuses the
same frozen operating states, reads the existing expanded-domain NPZ maps, and
reconstructs only a handful of exact trial closures.  No lambda-plane sweep is
repeated.

Outputs are written under ``artifacts/singular_vector_diagnostics``:

* ``points.csv`` -- exact selected point metrics and topology status;
* ``right_weak_direction.csv`` -- weakest right singular vector in the
  equilibrated closure coordinates, plus its back-scaled physical direction;
* ``left_weak_direction.csv`` -- weakest left singular vector, identifying the
  equation combination that becomes nearly redundant;
* ``secondary_tau_normal_feedback.csv`` -- focused diagnostic for the
  secondary axial/traction coupling in the (tau_s, N_s) subspace;
* one three-panel PNG per requested state.

The singular vectors are computed from the *same row/column-equilibrated 8x8
matrix* used for the reported scaled condition number.  This matters because
raw singular-vector magnitudes would otherwise be dominated by mixed units.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Import the canonical study implementation from this directory.  Keeping the
# operating-state construction and closure evaluation in one place prevents
# this diagnostic from becoming a second mechanics implementation.
import run as cc
from case_library import load_case_library
from cinder.model.cvt.contact import ContactTractionUtilization
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
from cinder.model.cvt.dynamics.equations import build_closure_equations

HERE = Path(__file__).resolve().parent
OUT = cc.ARTIFACTS / "singular_vector_diagnostics"

UNKNOWN_NAMES = (
    "alpha_p",
    "alpha_s",
    "v_b_dot",
    "s_ddot",
    "tau_p",
    "tau_s",
    "N_p",
    "N_s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--states",
        nargs="+",
        default=["upper_stop", "mid_shift"],
        help="Mapped state labels to diagnose (default: upper_stop mid_shift).",
    )
    parser.add_argument(
        "--ridge-percentile",
        type=float,
        default=99.5,
        help="Expanded-map scaled-kappa(A) percentile defining a high-conditioning ridge.",
    )
    return parser.parse_args()


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
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def equilibrated_svd(matrix: np.ndarray, rhs: np.ndarray):
    """Return the exact scaling used by CINDER's reported scaled condition number."""
    A = np.asarray(matrix, dtype=float)
    b = np.asarray(rhs, dtype=float)
    row_norm = np.maximum(np.max(np.abs(A), axis=1), np.abs(b))
    row_scale = np.where(row_norm > 0.0, 1.0 / row_norm, 1.0)
    row_matrix = row_scale[:, None] * A
    column_norm = np.max(np.abs(row_matrix), axis=0)
    column_scale = np.where(column_norm > 0.0, 1.0 / column_norm, 1.0)
    scaled = row_matrix * column_scale[None, :]
    U, singular, Vh = np.linalg.svd(scaled, full_matrices=True)
    return scaled, row_scale, column_scale, U, singular, Vh


def deterministic_weak_vectors(U: np.ndarray, Vh: np.ndarray):
    """Fix the arbitrary SVD sign so tables/plots remain stable across runs."""
    left = np.asarray(U[:, -1], dtype=float).copy()
    right = np.asarray(Vh[-1, :], dtype=float).copy()
    pivot = int(np.argmax(np.abs(right)))
    if right[pivot] < 0.0:
        right *= -1.0
        left *= -1.0
    return left, right


def state_catalog(spec: dict, library: dict):
    print("Rebuilding frozen state catalog (no lambda maps are recomputed)...")
    launch = cc.build_reference(spec, "launch")
    nominal = cc.select_nominal_states(launch)
    controlled, _ = cc.build_controlled_states(launch.decoded, library)
    return {label: (ref, sample) for label, ref, sample in nominal + controlled}


def actual_lambdas(ref, sample):
    inspection = cc.reconstruct(ref, sample, closure_audit=True)
    if inspection.contact is None:
        raise RuntimeError("Requested diagnostic state is not engaged contact.")
    u = inspection.contact.traction_utilization
    return float(u.primary_lambda), float(u.secondary_lambda)


def finite_argmax(values: np.ndarray, mask: np.ndarray | None = None):
    valid = np.isfinite(values)
    if mask is not None:
        valid &= np.asarray(mask, dtype=bool)
    if not np.any(valid):
        return None
    score = np.where(valid, values, -np.inf)
    return np.unravel_index(int(np.argmax(score)), values.shape)


def select_points(state: str, actual_lp: float, actual_ls: float, percentile: float):
    path = cc.ARTIFACTS / "states" / state / "expanded_map.npz"
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}. Run the closure-conditioning study first so the expanded map exists."
        )
    with np.load(path) as data:
        lp = np.asarray(data["lambda_p"], dtype=float)
        ls = np.asarray(data["lambda_s"], dtype=float)
        cond = np.asarray(data["cond_A_scaled"], dtype=float)
        topology = np.asarray(data["topology_admissible"], dtype=bool)

        points: list[tuple[str, float, float, str]] = [
            ("actual_root", actual_lp, actual_ls, "exact actual stick root"),
        ]

        idx = finite_argmax(cond)
        if idx is not None:
            i, j = idx
            points.append(("expanded_max_A", float(lp[j]), float(ls[i]), "global expanded-domain max scaled kappa(A)"))

        idx = finite_argmax(cond, topology)
        if idx is not None:
            i, j = idx
            points.append(("expanded_max_A_topology_admissible", float(lp[j]), float(ls[i]), "max scaled kappa(A) among retained-topology points"))

        finite = cond[np.isfinite(cond)]
        if finite.size:
            threshold = float(np.percentile(finite, percentile))
            LP, LS = np.meshgrid(lp, ls)
            ridge = np.isfinite(cond) & (cond >= threshold)
            if np.any(ridge):
                distance = np.hypot(LP - actual_lp, LS - actual_ls)
                distance = np.where(ridge, distance, np.inf)
                i, j = np.unravel_index(int(np.argmin(distance)), cond.shape)
                points.append((
                    "nearest_high_A_ridge",
                    float(lp[j]),
                    float(ls[i]),
                    f"nearest point in top {100.0-percentile:.3g}% of expanded scaled kappa(A)",
                ))

    # Deduplicate coordinates while retaining the first semantic label.
    out = []
    seen = set()
    for item in points:
        key = (round(item[1], 14), round(item[2], 14))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def diagnose_point(state: str, point_name: str, lp: float, ls: float, description: str, ref, sample):
    inspection = cc.reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    if contact is None:
        raise RuntimeError(f"{state}: no engaged contact snapshot")
    snapshot = contact.snapshot
    closure = EngagedContactClosure(snapshot=snapshot, shift_constraint=cc.engaged_constraint(sample))
    utilization = ContactTractionUtilization(primary_lambda=float(lp), secondary_lambda=float(ls))
    trial = closure.evaluate_trial(
        traction_utilization=utilization,
        maximum_closure_condition_number=None,
        capture_diagnostics=True,
    )
    audit = trial.closure

    context = TrialEquationContext(snapshot=snapshot, traction_utilization=utilization)
    equations = build_closure_equations(fixed_equations=closure.fixed_equations, trial_context=context)
    row_names = tuple(eq.name for eq in equations)
    if len(row_names) != 8:
        raise RuntimeError(f"Expected eight closure rows, got {row_names!r}")

    scaled, row_scale, column_scale, U, singular, Vh = equilibrated_svd(audit.matrix, audit.right_hand_side)
    left, right = deterministic_weak_vectors(U, Vh)
    backscaled = column_scale * right
    if np.max(np.abs(backscaled)) > 0.0:
        backscaled_relative = backscaled / np.max(np.abs(backscaled))
    else:
        backscaled_relative = backscaled.copy()

    code, extra = cc.topology_failure_code(ref, sample, trial, utilization, snapshot)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0.0 else float("inf")

    point_row = {
        "state": state,
        "point": point_name,
        "description": description,
        "lambda_p": lp,
        "lambda_s": ls,
        "scaled_condition_A": condition,
        "sigma_min_A_scaled": float(singular[-1]),
        "sigma_max_A_scaled": float(singular[0]),
        "matrix_rank": int(audit.matrix_rank),
        "topology_failure_code": int(code),
        "topology_admissible": bool(code == 0),
        "N_p": float(audit.unknowns.primary_normal_resultant),
        "N_s": float(audit.unknowns.secondary_normal_resultant),
        "tau_p": float(audit.unknowns.primary_torque),
        "tau_s": float(audit.unknowns.secondary_torque),
        "min_belt_tension": float(extra["min_belt_tension"]),
        "min_local_normal_p": float(extra["min_local_normal_p"]),
        "min_local_normal_s": float(extra["min_local_normal_s"]),
        "mechanism_margin": float(extra["mechanism_margin"]),
        "support_reaction": float(extra["support_reaction"]),
    }

    right_rows = []
    for index, name in enumerate(UNKNOWN_NAMES):
        right_rows.append({
            "state": state,
            "point": point_name,
            "unknown": name,
            "equilibrated_right_component": float(right[index]),
            "column_scale": float(column_scale[index]),
            "backscaled_direction": float(backscaled[index]),
            "backscaled_relative_direction": float(backscaled_relative[index]),
        })

    left_rows = []
    for index, name in enumerate(row_names):
        left_rows.append({
            "state": state,
            "point": point_name,
            "equation": name,
            "equilibrated_left_component": float(left[index]),
            "row_scale": float(row_scale[index]),
        })

    feedback_row = {
        "state": state,
        "point": point_name,
        "lambda_p": lp,
        "lambda_s": ls,
        "available": False,
    }
    try:
        axial_i = row_names.index("secondary_axial")
        traction_i = row_names.index("secondary_traction")
        tau_s_i = UNKNOWN_NAMES.index("tau_s")
        N_s_i = UNKNOWN_NAMES.index("N_s")
        block = scaled[np.ix_([axial_i, traction_i], [tau_s_i, N_s_i])]
        r0 = block[0]
        r1 = block[1]
        n0 = float(np.linalg.norm(r0))
        n1 = float(np.linalg.norm(r1))
        cosine = float(np.dot(r0, r1) / (n0 * n1)) if n0 > 0.0 and n1 > 0.0 else float("nan")
        normalized_det = float(np.linalg.det(np.vstack((r0 / n0, r1 / n1)))) if n0 > 0.0 and n1 > 0.0 else float("nan")
        feedback_row.update({
            "available": True,
            "secondary_axial_tau_s_scaled": float(block[0, 0]),
            "secondary_axial_N_s_scaled": float(block[0, 1]),
            "secondary_traction_tau_s_scaled": float(block[1, 0]),
            "secondary_traction_N_s_scaled": float(block[1, 1]),
            "row_cosine": cosine,
            "abs_row_cosine": abs(cosine),
            "normalized_2x2_determinant": normalized_det,
            "abs_normalized_2x2_determinant": abs(normalized_det),
        })
    except ValueError:
        # Defensive: this should not occur for the current CINDER v1.1.2 row names.
        pass

    return point_row, right_rows, left_rows, feedback_row, singular, right, left, row_names


def plot_state(state: str, diagnostics: list[dict[str, Any]], out_path: Path) -> None:
    point_names = [d["point_row"]["point"] for d in diagnostics]
    x_u = np.arange(len(UNKNOWN_NAMES), dtype=float)

    fig, axes = plt.subplots(3, 1, figsize=(13, 12), constrained_layout=True)

    width = 0.8 / max(1, len(diagnostics))
    for k, d in enumerate(diagnostics):
        offset = (k - (len(diagnostics) - 1) / 2.0) * width
        axes[0].bar(x_u + offset, d["right"], width=width, label=d["point_row"]["point"])
    axes[0].axhline(0.0, linewidth=0.8)
    axes[0].set_xticks(x_u, UNKNOWN_NAMES, rotation=25, ha="right")
    axes[0].set_ylabel("weak right-vector component")
    axes[0].set_title("Weak 8×8 response direction in equilibrated unknown coordinates")
    axes[0].legend(fontsize=8)

    row_names = diagnostics[0]["row_names"]
    x_r = np.arange(len(row_names), dtype=float)
    for k, d in enumerate(diagnostics):
        offset = (k - (len(diagnostics) - 1) / 2.0) * width
        axes[1].bar(x_r + offset, d["left"], width=width, label=d["point_row"]["point"])
    axes[1].axhline(0.0, linewidth=0.8)
    axes[1].set_xticks(x_r, row_names, rotation=25, ha="right")
    axes[1].set_ylabel("weak left-vector component")
    axes[1].set_title("Nearly redundant equation combination in equilibrated row coordinates")

    cond = [float(d["point_row"]["scaled_condition_A"]) for d in diagnostics]
    sigma = [float(d["point_row"]["sigma_min_A_scaled"]) for d in diagnostics]
    x = np.arange(len(diagnostics))
    axes[2].bar(x - 0.18, np.log10(np.maximum(cond, 1.0)), width=0.36, label=r"log10 kappa(A)")
    axes[2].bar(x + 0.18, -np.log10(np.maximum(sigma, np.finfo(float).tiny)), width=0.36, label=r"-log10 sigma_min(A)")
    axes[2].set_xticks(x, point_names, rotation=20, ha="right")
    axes[2].set_ylabel("log severity")
    axes[2].set_title("How strongly the closure softens at each selected point")
    axes[2].legend(fontsize=8)

    fig.suptitle(f"{state}: singular-vector anatomy of the 8×8 closure", fontsize=14)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    if not 0.0 < args.ridge_percentile < 100.0:
        raise ValueError("--ridge-percentile must lie strictly between 0 and 100.")

    cc.verify_environment()
    spec = cc.load_json(cc.SPEC_FILE)
    library = load_case_library(cc.CASE_LIBRARY_FILE)
    catalog = state_catalog(spec, library)

    OUT.mkdir(parents=True, exist_ok=True)
    point_rows: list[dict[str, Any]] = []
    right_rows: list[dict[str, Any]] = []
    left_rows: list[dict[str, Any]] = []
    feedback_rows: list[dict[str, Any]] = []

    for state in args.states:
        if state not in catalog:
            raise KeyError(f"Unknown state {state!r}. Available labels: {sorted(catalog)}")
        ref, sample = catalog[state]
        actual_lp, actual_ls = actual_lambdas(ref, sample)
        selected = select_points(state, actual_lp, actual_ls, args.ridge_percentile)
        print(f"\n{state}: diagnosing {len(selected)} exact points")
        state_diagnostics = []
        for point_name, lp, ls, description in selected:
            print(f"  {point_name}: lambda_p={lp:.6g}, lambda_s={ls:.6g}")
            point_row, rr, lr, fr, singular, right, left, row_names = diagnose_point(
                state, point_name, lp, ls, description, ref, sample
            )
            point_rows.append(point_row)
            right_rows.extend(rr)
            left_rows.extend(lr)
            feedback_rows.append(fr)
            state_diagnostics.append({
                "point_row": point_row,
                "singular": singular,
                "right": right,
                "left": left,
                "row_names": row_names,
            })
        plot_state(state, state_diagnostics, OUT / f"{state}_singular_vector_diagnostic.png")

    write_rows(OUT / "points.csv", point_rows)
    write_rows(OUT / "right_weak_direction.csv", right_rows)
    write_rows(OUT / "left_weak_direction.csv", left_rows)
    write_rows(OUT / "secondary_tau_normal_feedback.csv", feedback_rows)

    summary = OUT / "README.txt"
    summary.write_text(
        "Singular-vector diagnostics for CINDER v1.1.2 closure conditioning.\n"
        "\n"
        "Interpret the right/left vector components in equilibrated coordinates;\n"
        "the equilibration deliberately removes raw unit-scale dominance.  The\n"
        "secondary_tau_normal_feedback table tests whether the secondary axial\n"
        "and secondary traction rows become nearly parallel in the (tau_s,N_s)\n"
        "projection: |row_cosine| -> 1 and |normalized determinant| -> 0 indicate\n"
        "the torque-reactive clamp feedback described in the upper-stop analysis.\n"
        "The back-scaled right direction is also stored, but its components carry\n"
        "different physical units and should not be ranked by raw magnitude.\n",
        encoding="utf-8",
    )
    print(f"\nWrote diagnostics to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
