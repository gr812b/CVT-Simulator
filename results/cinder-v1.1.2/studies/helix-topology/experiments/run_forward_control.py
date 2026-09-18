"""E2: natural forward-operation helix reaction audit under the slotted reference."""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.metrics import contact_topology_metrics  # noqa: E402
from infrastructure.study_support import (  # noqa: E402
    ARTIFACTS,
    load_json,
    run_flat_slotted_reference,
    verify_environment,
    write_reference_provenance,
    write_rows,
)


def _finite_series(rows, key):
    pairs = []
    for row in rows:
        try:
            t = float(row["time_s"])
            v = float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(t) and np.isfinite(v):
            pairs.append((t, v))
    if not pairs:
        return np.asarray([]), np.asarray([])
    return np.asarray([p[0] for p in pairs]), np.asarray([p[1] for p in pairs])


def main() -> int:
    verify_environment()
    cfg = load_json(STUDY_ROOT / "study.json")["experiments"]["forward_control"]
    solver = cfg["solver"]
    run, _resolved, _assembly, _engine, _road_load, ab, _route = run_flat_slotted_reference(
        duration_s=float(cfg["duration_s"]),
        sample_step_s=float(cfg["sample_step_s"]),
        rtol=float(solver["relative_tolerance"]),
        atol=float(solver["absolute_tolerance"]),
        max_step_s=float(solver["max_step_s"]),
    )
    rows = [sample.row for sample in run.samples]
    metrics = contact_topology_metrics(
        rows,
        case_start_s=0.0,
        case_end_s=float(cfg["duration_s"]),
    )

    force_residuals = []
    for row in rows:
        try:
            x = float(row["helix_force_reconstruction_residual_N"])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(x):
            force_residuals.append(abs(x))
    metrics.update(
        {
            "stage": "E2",
            "scenario": cfg["scenario"],
            "hybrid_transition_count": len(run.result.transitions),
            "max_abs_helix_force_reconstruction_residual_N": (
                max(force_residuals) if force_residuals else None
            ),
            "topology": getattr(run.topology_status, "secondary_helix_topology", str(run.topology_status)),
        }
    )

    out = ARTIFACTS / "forward-control"
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "trace.csv", rows)
    try:
        write_rows(out / "transitions.csv", ab.transition_rows(
            ab.VariantResult(
                variant=next(v for v in ab.VARIANTS if v.key == "full"),
                assembly=_assembly,
                system=run.system,
                hybrid_result=run.result,
                samples=run.samples,
                contribution_rows=run.contribution_rows,
                metrics={},
            )
        ))
    except Exception as exc:
        (out / "transition_export_warning.txt").write_text(
            f"Transition export was nonessential and failed: {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
    (out / "summary.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    t, margin = _finite_series(rows, "helix_reacted_torque_margin_Nm")
    _t_force, force = _finite_series(rows, "helix_full_reaction_force_N")
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 7.0), sharex=True)
    axes[0].plot(t, margin, label="reacted torque margin")
    axes[0].axhline(0.0, linewidth=1.0)
    axes[0].set_ylabel("$M_h$ [N m]")
    axes[0].set_title("Natural forward operation — helix contact margin")
    axes[0].grid(True, alpha=0.25)
    axes[1].plot(_t_force, force, label="helix axial force")
    axes[1].axhline(0.0, linewidth=1.0)
    axes[1].set_ylabel("$F_h$ [N]")
    axes[1].set_xlabel("Time [s]")
    axes[1].grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "helix_margin_and_force.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    for key, label in (
        ("helix_belt_reaction_torque_Nm", "belt torque share"),
        ("helix_torsional_spring_torque_Nm", "torsional spring"),
        ("helix_shaft_accel_reaction_torque_Nm", "shaft acceleration"),
        ("helix_shift_accel_reaction_torque_Nm", "shift acceleration"),
        ("helix_curvature_reaction_torque_Nm", "profile curvature"),
    ):
        tx, vx = _finite_series(rows, key)
        ax.plot(tx, vx, label=label)
    ax.axhline(0.0, linewidth=1.0)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Reacted-torque contribution [N m]")
    ax.set_title("Helix reaction decomposition")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out / "helix_reaction_decomposition.png", dpi=180)
    plt.close(fig)

    write_reference_provenance(
        out / "provenance",
        plant=run.system.cvt.model,
        extra={
            "study_stage": "E2_forward_control",
            "solver": solver,
            "duration_s": cfg["duration_s"],
            "sample_step_s": cfg["sample_step_s"],
        },
    )
    print(json.dumps(metrics, indent=2))
    print(f"Wrote E2 forward-control artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
