"""Run the broad discovery pass for reduced-belt transient mechanics.

This runner does not modify the governing model.  It creates a small family of
transparent Baja-style protocols from the canonical v1.1.2 reference document,
runs each full model, and builds the same final-equation term atlas for all of
them.  The purpose is orientation before any ablation is designed.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
REPO_ROOT = STUDY_ROOT.parents[3]
RELEASE_DEFAULT_CASE = RELEASE_ROOT / "defaults" / "baja_reference_simulation_case.json"
REPO_EXAMPLE_CASE = REPO_ROOT / "cvtModel" / "examples" / "baja_baseline_simulation_case.json"
VERIFY = RELEASE_ROOT / "verify_environment.py"
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from audit_simulation_case import run_case
from belt_terms import inventory
from study_support import ARTIFACTS, write_json, write_rows


PROTOCOLS = (
    {
        "name": "ordinary_flat_launch",
        "title": "Ordinary flat launch",
        "purpose": "Baseline launch and natural active upshift on the canonical full model.",
        "duration_s": 6.0,
        "grade_steps": ((0.0, 0.0),),
    },
    {
        "name": "moderate_load_step",
        "title": "Moderate wheel-load increase",
        "purpose": "Introduce a moderate grade step during the launch/upshift trajectory and observe load-driven backshift/recovery if it occurs.",
        "duration_s": 8.0,
        "grade_steps": ((0.0, 0.0), (5.0, 8.0), (14.0, 0.0)),
    },
    {
        "name": "strong_load_step",
        "title": "Strong wheel-load increase",
        "purpose": "Excite faster shift and belt-transport response without changing belt/contact physics.",
        "duration_s": 8.0,
        "grade_steps": ((0.0, 0.0), (5.0, 18.0), (14.0, 0.0)),
    },
    {
        "name": "severe_load_step",
        "title": "Severe load/contact-demand exploration",
        "purpose": "Explore the high-demand end of the same physical model; contact transition is observed only if it occurs naturally.",
        "duration_s": 8.0,
        "grade_steps": ((0.0, 0.0), (5.0, 28.0), (14.0, 0.0)),
    },
)


def _resolved_protocol(base: dict, protocol: dict) -> dict:
    document = copy.deepcopy(base)
    document["scenario"]["time_span_s"] = [0.0, float(protocol["duration_s"])]
    steps = protocol["grade_steps"]
    if len(steps) == 1:
        document["shaft_boundaries"]["secondary"]["road_profile"] = {
            "kind": "constant_grade",
            "grade_angle_rad": math.radians(float(steps[0][1])),
        }
    else:
        document["shaft_boundaries"]["secondary"]["road_profile"] = {
            "kind": "piecewise_constant_grade",
            "segments": [
                {"start_distance_m": float(distance), "grade_angle_rad": math.radians(float(degrees))}
                for distance, degrees in steps
            ],
        }
    return document


def _synthesize(case_summaries: dict[str, dict]) -> None:
    terms = (
        "transport.belt_inertia_N",
        "loop.radial_shift_acceleration_N",
        "loop.radial_geometry_curvature_N",
        "loop.tangential_belt_acceleration_N",
        "loop.tangential_shifting_radius_N",
        "loop.normal_contact_N",
    )
    rows = []
    for name, payload in case_summaries.items():
        summary = payload["overall"]
        for term in terms:
            stats = summary["channels"].get(term, {})
            rows.append({
                "case": name,
                "term": term,
                "max_abs_N": stats.get("max_abs"),
                "median_abs_N": stats.get("median_abs"),
                "p95_abs_N": stats.get("p95_abs"),
                "integrated_activity_share": summary["integrated_activity_share"].get(term),
            })
    write_rows(ARTIFACTS / "exploration_summary.csv", rows)
    write_json(ARTIFACTS / "exploration_summary.json", {"cases": case_summaries, "term_rows": rows})

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:
        return

    transient_terms = (
        "transport.belt_inertia_N",
        "loop.radial_shift_acceleration_N",
        "loop.radial_geometry_curvature_N",
        "loop.tangential_belt_acceleration_N",
        "loop.tangential_shifting_radius_N",
    )
    labels = ("transport inertia", "radial sddot", "radial sdot^2", "tangential vbdot", "tangential sdot*vb")
    cases = list(case_summaries)
    x = np.arange(len(cases), dtype=float)
    width = 0.14
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for index, (term, label) in enumerate(zip(transient_terms, labels, strict=True)):
        values = [case_summaries[case]["overall"]["integrated_activity_share"].get(term) or 0.0 for case in cases]
        ax.bar(x + (index - 2) * width, values, width=width, label=label)
    ax.set_xticks(x, [case.replace("_", "\n") for case in cases])
    ax.set_ylabel("Time-integrated equation activity share [-]")
    ax.set_title("Reduced-belt discovery: transient-term activity across broad protocols")
    ax.legend(ncol=2)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "cross_case_activity.png", dpi=180)
    plt.close(fig)


def _resolve_base_case(requested: Path | None) -> Path:
    """Resolve the canonical executable Baja baseline without assuming one tree layout.

    Results releases normally carry their own frozen baseline under ``defaults/``.
    Development/result worktrees also carry the same executable baseline under
    ``cvtModel/examples``.  Prefer the release-local copy when available; otherwise
    use the repository example so the study still runs in lean result checkouts.
    An explicit ``--base-case`` always wins.
    """

    if requested is not None:
        candidate = requested.expanduser().resolve()
        if not candidate.is_file():
            raise FileNotFoundError(f"Explicit --base-case does not exist: {candidate}")
        return candidate

    for candidate in (RELEASE_DEFAULT_CASE, REPO_EXAMPLE_CASE):
        if candidate.is_file():
            return candidate.resolve()

    searched = "\n  - ".join(str(path) for path in (RELEASE_DEFAULT_CASE, REPO_EXAMPLE_CASE))
    raise FileNotFoundError(
        "Could not locate the executable Baja baseline. Searched:\n  - "
        + searched
        + "\nPass --base-case PATH to an equivalent cinder_composed_simulation_case JSON."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-case",
        type=Path,
        default=None,
        help=(
            "Optional executable baseline JSON. By default the study prefers the "
            "release-local defaults case and falls back to "
            "cvtModel/examples/baja_baseline_simulation_case.json."
        ),
    )
    parser.add_argument("--max-samples", type=int, default=6000)
    parser.add_argument("--only", choices=[p["name"] for p in PROTOCOLS], action="append")
    parser.add_argument("--tests-only", action="store_true", help="Run pure final-equation tests and stop before importing CINDER.")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    if not args.skip_tests:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(STUDY_ROOT / "tests"), "-v"], check=True)
    if args.tests_only:
        return 0

    subprocess.run([sys.executable, str(VERIFY)], check=True)
    base_path = _resolve_base_case(args.base_case)
    print(f"Base simulation case: {base_path}")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)
    write_json(ARTIFACTS / "term_inventory.json", list(inventory()))

    selected = [p for p in PROTOCOLS if not args.only or p["name"] in args.only]
    protocol_dir = ARTIFACTS / "resolved_protocols"
    protocol_dir.mkdir()
    summaries: dict[str, dict] = {}
    for protocol in selected:
        document = _resolved_protocol(base, protocol)
        case_path = protocol_dir / f"{protocol['name']}.json"
        write_json(case_path, document)
        print(f"\n=== {protocol['title']} ===")
        summaries[protocol["name"]] = run_case(
            case_path=case_path,
            name=protocol["name"],
            max_samples=args.max_samples,
            skip_environment_check=True,
        )
        summaries[protocol["name"]]["study_purpose"] = protocol["purpose"]

    _synthesize(summaries)
    write_json(ARTIFACTS / "stage_status.json", {
        "stage": "broad-exploration",
        "governing_model_modified": False,
        "ablation_switches_present": False,
        "protocol_count": len(selected),
        "next_action": "Inspect the atlas and cross-case activity before designing targeted transient sweeps or coherent reductions.",
    })
    print(f"\nExploration artifacts: {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
