"""Run broad and controlled exploration of CINDER's surviving belt terms.

Stage A reproduces broad route/launch coverage. Stage B uses controlled smooth
secondary-load rises to separate disturbance *magnitude* from disturbance
*timescale*. No governing CVT equation or contact law is modified.
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
from typing import Any

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
from closure_design import (
    apply_belt_density_scale,
    apply_contact_stress,
    build_contact_stress_cases,
    build_inertia_continuations,
)
from closure_synthesis import synthesize_closure
from envelope_design import apply_tune_variant, build_baja_envelope
from equation_sensitivity import build_equation_sensitivity
from protocol_support import (
    SmoothGradeProgram,
    SmoothOverrunProgram,
    install_global_transport_inertia_scale,
    make_overrun_boundaries,
    make_time_programmed_boundary,
)
from sensitivity_synthesis import synthesize_sensitivity_connections
from study_support import ARTIFACTS, write_json, write_rows

BROAD_PROTOCOLS = (
    {
        "name": "ordinary_flat_launch",
        "title": "Ordinary flat launch",
        "family": "broad",
        "purpose": "Baseline launch and natural active upshift on the canonical full model.",
        "duration_s": 6.0,
        "grade_steps": ((0.0, 0.0),),
    },
    {
        "name": "moderate_load_step",
        "title": "Moderate wheel-load increase",
        "family": "broad",
        "purpose": "8 degree spatial grade step during natural upshift, then return to flat.",
        "duration_s": 8.0,
        "grade_steps": ((0.0, 0.0), (5.0, 8.0), (14.0, 0.0)),
    },
    {
        "name": "strong_load_step",
        "title": "Strong wheel-load increase",
        "family": "broad",
        "purpose": "18 degree spatial grade step during natural upshift, then return to flat.",
        "duration_s": 8.0,
        "grade_steps": ((0.0, 0.0), (5.0, 18.0), (14.0, 0.0)),
    },
    {
        "name": "severe_load_step",
        "title": "Severe load/contact-demand exploration",
        "family": "broad",
        "purpose": "28 degree spatial grade step to obtain a natural load-driven backshift if the full model produces one.",
        "duration_s": 8.0,
        "grade_steps": ((0.0, 0.0), (5.0, 28.0), (14.0, 0.0)),
    },
)

# Sparse, mechanistic design rather than a Cartesian sweep.  The 18-degree
# series isolates timescale.  The 0.20-s series isolates disturbance magnitude.
CONTROLLED_PROTOCOLS = (
    {"name": "controlled_18deg_step", "title": "18 degree instantaneous road-load application", "target_grade_deg": 18.0, "rise_time_s": 0.0},
    {"name": "controlled_18deg_050ms", "title": "18 degree rise over 50 ms", "target_grade_deg": 18.0, "rise_time_s": 0.05},
    {"name": "controlled_18deg_200ms", "title": "18 degree rise over 200 ms", "target_grade_deg": 18.0, "rise_time_s": 0.20},
    {"name": "controlled_18deg_800ms", "title": "18 degree rise over 800 ms", "target_grade_deg": 18.0, "rise_time_s": 0.80},
    {"name": "controlled_08deg_200ms", "title": "8 degree rise over 200 ms", "target_grade_deg": 8.0, "rise_time_s": 0.20},
    {"name": "controlled_28deg_200ms", "title": "28 degree rise over 200 ms", "target_grade_deg": 28.0, "rise_time_s": 0.20},
)
CONTROLLED_START_TIME_S = 1.50
CONTROLLED_DURATION_S = 4.50

OVERRUN_PROTOCOLS = (
    {
        "name": "overrun_mild",
        "title": "Controlled overrun: -20° downhill, -5 N·m primary",
        "start_time_s": 2.00,
        "rise_time_s": 0.20,
        "target_grade_deg": -20.0,
        "target_primary_torque_Nm": -5.0,
    },
    {
        "name": "overrun_strong",
        "title": "Controlled overrun: -20° downhill, -12 N·m primary",
        "start_time_s": 2.00,
        "rise_time_s": 0.20,
        "target_grade_deg": -20.0,
        "target_primary_torque_Nm": -12.0,
    },
)
CLOSURE_DURATION_S = 5.0


def _resolve_base_case(requested: Path | None) -> Path:
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


def _broad_document(base: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
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


def _controlled_document(base: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(base)
    document["scenario"]["time_span_s"] = [0.0, CONTROLLED_DURATION_S]
    document["shaft_boundaries"]["secondary"]["road_profile"] = {
        "kind": "constant_grade",
        "grade_angle_rad": 0.0,
    }
    return document


def _envelope_document(base: dict[str, Any], *, start_time_s: float, rise_time_s: float) -> dict[str, Any]:
    document = copy.deepcopy(base)
    duration = max(5.0, float(start_time_s) + float(rise_time_s) + 2.0)
    document["scenario"]["time_span_s"] = [0.0, duration]
    document["shaft_boundaries"]["secondary"]["road_profile"] = {
        "kind": "constant_grade",
        "grade_angle_rad": 0.0,
    }
    return document


def _inertia_scenario_document(base: dict[str, Any], scenario: str) -> tuple[dict[str, Any], SmoothGradeProgram | None]:
    document = copy.deepcopy(base)
    document["scenario"]["time_span_s"] = [0.0, CLOSURE_DURATION_S]
    document["shaft_boundaries"]["secondary"]["road_profile"] = {
        "kind": "constant_grade",
        "grade_angle_rad": 0.0,
    }
    if scenario == "flat":
        return document, None
    if scenario == "fast_backshift":
        return document, SmoothGradeProgram(start_time_s=1.50, rise_time_s=0.05, target_grade_deg=30.0)
    if scenario == "fast_unload":
        return document, SmoothGradeProgram(start_time_s=1.50, rise_time_s=0.05, target_grade_deg=-20.0)
    raise ValueError(f"unknown inertia scenario: {scenario}")


def _free_stick(summary: dict[str, Any]) -> dict[str, Any] | None:
    return summary.get("phase_analysis", {}).get("named_phases", {}).get("free_stick_all")


def _append_summary_rows(rows: list[dict[str, Any]], *, case: str, family: str, scope: str, summary: dict[str, Any] | None) -> None:
    if not summary:
        return
    terms = (
        "transport.belt_inertia_N",
        "loop.radial_shift_acceleration_N",
        "loop.radial_geometry_curvature_N",
        "loop.tangential_belt_acceleration_N",
        "loop.tangential_shifting_radius_N",
        "loop.normal_contact_N",
    )
    for term in terms:
        stats = summary.get("channels", {}).get(term, {})
        rows.append({
            "case": case,
            "family": family,
            "scope": scope,
            "term": term,
            "sample_count": summary.get("sample_count"),
            "max_abs_N": stats.get("max_abs"),
            "median_abs_N": stats.get("median_abs"),
            "p95_abs_N": stats.get("p95_abs"),
            "integrated_activity_share": summary.get("integrated_activity_share", {}).get(term),
        })


def _controlled_metric_row(name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    protocol = payload.get("protocol", {})
    control = protocol.get("controlled_load")
    if not isinstance(control, dict):
        return None
    windows = payload.get("phase_analysis", {}).get("controlled_windows", {})
    response = windows.get("first_1s_after_start", {}).get("summary")
    pre = windows.get("pre_load_reference", {}).get("summary")
    rise = windows.get("load_rise", {}).get("summary")
    if response is None:
        return None

    def channel(summary: dict[str, Any] | None, key: str, field: str = "max_abs"):
        if not summary:
            return None
        return summary.get("channels", {}).get(key, {}).get(field)

    def context(summary: dict[str, Any] | None, key: str, field: str = "max_abs"):
        if not summary:
            return None
        item = summary.get("context", {}).get(key)
        return None if item is None else item.get(field)

    return {
        "case": name,
        "target_grade_deg": control["target_grade_deg"],
        "rise_time_s": control["rise_time_s"],
        "start_time_s": control["start_time_s"],
        "response_max_abs_shift_acceleration_contribution_N": channel(response, "loop.radial_shift_acceleration_N"),
        "response_p95_abs_shift_acceleration_contribution_N": channel(response, "loop.radial_shift_acceleration_N", "p95_abs"),
        "response_activity_shift_acceleration_contribution": response["integrated_activity_share"].get("loop.radial_shift_acceleration_N"),
        "response_max_abs_path_curvature_contribution_N": channel(response, "loop.radial_geometry_curvature_N"),
        "response_max_abs_belt_acceleration_contribution_N": channel(response, "loop.tangential_belt_acceleration_N"),
        "response_max_abs_moving_radius_contribution_N": channel(response, "loop.tangential_shifting_radius_N"),
        "response_transport_inertia_max_abs_N": channel(response, "transport.belt_inertia_N"),
        "response_transport_inertia_activity": response["integrated_activity_share"].get("transport.belt_inertia_N"),
        "response_max_abs_shift_accel_mps2": context(response, "state.shift_acceleration_m_per_s2"),
        "response_max_abs_belt_accel_mps2": context(response, "state.belt_acceleration_m_per_s2"),
        "response_max_contact_static_fraction": context(response, "contact.max_static_utilization_fraction", "max"),
        "pre_max_contact_static_fraction": context(pre, "contact.max_static_utilization_fraction", "max"),
        "rise_activity_shift_acceleration_contribution": None if rise is None else rise["integrated_activity_share"].get("loop.radial_shift_acceleration_N"),
        "rise_max_abs_shift_acceleration_contribution_N": channel(rise, "loop.radial_shift_acceleration_N"),
    }


def _write_shift_coefficient_rows(case_summaries: dict[str, dict[str, Any]]) -> None:
    coefficient_keys = (
        "loop.response_coefficient.radial_shift_acceleration_N_per_mps2",
        "loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2",
        "loop.response_coefficient.tangential_belt_acceleration_N_per_mps2",
        "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2",
    )
    rows: list[dict[str, Any]] = []
    for case, payload in case_summaries.items():
        bands = payload.get("phase_analysis", {}).get("free_stick_by_shift_fraction", {})
        for band, summary in bands.items():
            for key in coefficient_keys:
                stats = summary.get("response_coefficients", {}).get(key)
                if not stats:
                    continue
                rows.append({
                    "case": case,
                    "shift_fraction_band": band,
                    "coefficient": key,
                    "median": stats.get("median"),
                    "p05": stats.get("p05"),
                    "p95": stats.get("p95"),
                    "max_abs": stats.get("max_abs"),
                })
    write_rows(ARTIFACTS / "response_coefficients_by_shift.csv", rows)



def _write_phase_dependence_tables(case_summaries: dict[str, dict[str, Any]]) -> None:
    terms = (
        "transport.belt_inertia_N",
        "loop.radial_shift_acceleration_N",
        "loop.radial_geometry_curvature_N",
        "loop.tangential_belt_acceleration_N",
        "loop.tangential_shifting_radius_N",
        "loop.normal_contact_N",
    )
    for family_key, filename in (
        ("free_stick_by_shift_fraction", "activity_by_shift_fraction.csv"),
        ("free_stick_by_contact_demand", "activity_by_contact_demand.csv"),
    ):
        rows: list[dict[str, Any]] = []
        for case, payload in case_summaries.items():
            groups = payload.get("phase_analysis", {}).get(family_key, {})
            for band, summary in groups.items():
                for term in terms:
                    stats = summary.get("channels", {}).get(term, {})
                    share_stats = summary.get("instantaneous_activity_share", {}).get(term) or {}
                    rows.append({
                        "case": case,
                        "band": band,
                        "term": term,
                        "sample_count": summary.get("sample_count"),
                        "max_abs_N": stats.get("max_abs"),
                        "p95_abs_N": stats.get("p95_abs"),
                        "integrated_activity_share": summary.get("integrated_activity_share", {}).get(term),
                        "instantaneous_share_p95": share_stats.get("p95"),
                        "instantaneous_share_max": share_stats.get("max"),
                    })
        write_rows(ARTIFACTS / filename, rows)


def _write_term_envelope(case_summaries: dict[str, dict[str, Any]], families: dict[str, str]) -> None:
    terms = (
        "transport.belt_inertia_N",
        "loop.radial_shift_acceleration_N",
        "loop.radial_geometry_curvature_N",
        "loop.tangential_belt_acceleration_N",
        "loop.tangential_shifting_radius_N",
        "loop.normal_contact_N",
    )
    rows: list[dict[str, Any]] = []
    for term in terms:
        candidates = []
        for case, payload in case_summaries.items():
            free = _free_stick(payload)
            if not free:
                continue
            stats = free.get("channels", {}).get(term)
            share_stats = free.get("instantaneous_activity_share", {}).get(term)
            if not stats:
                continue
            candidates.append((case, free, stats, share_stats or {}))
        if not candidates:
            continue
        peak_case, peak_summary, peak_stats, peak_share = max(
            candidates, key=lambda item: float(item[2].get("max_abs") or 0.0)
        )
        share_case, share_summary, share_mag, share_stats = max(
            candidates, key=lambda item: float(item[3].get("max") or 0.0)
        )
        integrated_values = [
            float(item[1].get("integrated_activity_share", {}).get(term) or 0.0)
            for item in candidates
        ]
        rows.append({
            "term": term,
            "free_stick_peak_abs_N": peak_stats.get("max_abs"),
            "free_stick_peak_case": peak_case,
            "free_stick_peak_context": json.dumps(peak_summary.get("peak_context", {}).get(term)),
            "free_stick_max_instantaneous_share": share_stats.get("max"),
            "free_stick_max_share_case": share_case,
            "free_stick_max_p95_share_across_cases": max(
                float(item[3].get("p95") or 0.0) for item in candidates
            ),
            "free_stick_integrated_share_min": min(integrated_values),
            "free_stick_integrated_share_max": max(integrated_values),
        })
    write_rows(ARTIFACTS / "term_envelope.csv", rows)

def _plot_synthesis(case_summaries: dict[str, dict[str, Any]], controlled_rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:
        return

    broad = [p["name"] for p in BROAD_PROTOCOLS if p["name"] in case_summaries]
    if broad:
        transient_terms = (
            "transport.belt_inertia_N",
            "loop.radial_shift_acceleration_N",
            "loop.radial_geometry_curvature_N",
            "loop.tangential_belt_acceleration_N",
            "loop.tangential_shifting_radius_N",
        )
        labels = ("whole-belt inertia", "shift acceleration", "shift-path curvature", "belt acceleration", "moving-radius transport")
        x = np.arange(len(broad), dtype=float)
        width = 0.14
        fig, ax = plt.subplots(figsize=(11, 5.5))
        for index, (term, label) in enumerate(zip(transient_terms, labels, strict=True)):
            values = []
            for case in broad:
                free = _free_stick(case_summaries[case])
                values.append(0.0 if free is None else (free["integrated_activity_share"].get(term) or 0.0))
            ax.bar(x + (index - 2) * width, values, width=width, label=label)
        ax.set_xticks(x, [case.replace("_", "\n") for case in broad])
        ax.set_ylabel("Free-stick integrated equation activity share [-]")
        ax.set_title("Reduced-belt exploration: continuously engaged free-stick mechanics")
        ax.legend(ncol=2)
        ax.grid(True, axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(ARTIFACTS / "cross_case_free_stick_activity.png", dpi=180)
        plt.close(fig)

    if controlled_rows:
        eighteen = sorted(
            [row for row in controlled_rows if abs(float(row["target_grade_deg"]) - 18.0) < 1e-12],
            key=lambda row: float(row["rise_time_s"]),
        )
        if eighteen:
            fig, ax = plt.subplots(figsize=(7.0, 5.2))
            ax.plot(
                [float(row["rise_time_s"]) for row in eighteen],
                [float(row["response_max_abs_shift_acceleration_contribution_N"]) for row in eighteen],
                marker="o",
            )
            ax.set_xlabel("18° load rise time [s]")
            ax.set_ylabel("max |shift-acceleration contribution| in first 1 s [N]")
            ax.set_title("Shift-acceleration contribution vs road-load application timescale")
            ax.grid(True, alpha=0.25)
            fig.tight_layout()
            fig.savefig(ARTIFACTS / "controlled_timescale_shift_acceleration.png", dpi=180)
            plt.close(fig)

        severity = sorted(
            [row for row in controlled_rows if abs(float(row["rise_time_s"]) - 0.20) < 1e-12],
            key=lambda row: float(row["target_grade_deg"]),
        )
        if severity:
            fig, ax = plt.subplots(figsize=(7.0, 5.2))
            ax.plot(
                [float(row["target_grade_deg"]) for row in severity],
                [float(row["response_max_abs_shift_acceleration_contribution_N"]) for row in severity],
                marker="o",
            )
            ax.set_xlabel("Target grade [deg], 0.20 s smooth rise")
            ax.set_ylabel("max |shift-acceleration contribution| in first 1 s [N]")
            ax.set_title("Shift-acceleration contribution vs road-load magnitude")
            ax.grid(True, alpha=0.25)
            fig.tight_layout()
            fig.savefig(ARTIFACTS / "controlled_severity_shift_acceleration.png", dpi=180)
            plt.close(fig)


def _synthesize(case_summaries: dict[str, dict[str, Any]], families: dict[str, str]) -> None:
    rows: list[dict[str, Any]] = []
    for name, payload in case_summaries.items():
        family = families[name]
        _append_summary_rows(rows, case=name, family=family, scope="overall", summary=payload.get("overall"))
        _append_summary_rows(rows, case=name, family=family, scope="free_stick_all", summary=_free_stick(payload))
    write_rows(ARTIFACTS / "exploration_summary.csv", rows)

    controlled_rows = [
        row for name, payload in case_summaries.items()
        if families.get(name) == "controlled"
        and (row := _controlled_metric_row(name, payload)) is not None
    ]
    write_rows(ARTIFACTS / "controlled_load_summary.csv", controlled_rows)
    _write_shift_coefficient_rows(case_summaries)
    _write_phase_dependence_tables(case_summaries)
    _write_term_envelope(case_summaries, families)
    write_json(
        ARTIFACTS / "exploration_summary.json",
        {
            "cases": case_summaries,
            "summary_rows": rows,
            "controlled_load_rows": controlled_rows,
        },
    )
    _plot_synthesis(case_summaries, controlled_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-case", type=Path, default=None)
    parser.add_argument("--max-samples", type=int, default=6000)
    parser.add_argument(
        "--stage",
        choices=("all", "broad", "controlled", "sensitivity", "envelope", "closure"),
        default="all",
    )
    parser.add_argument(
        "--envelope-points",
        type=int,
        default=18,
        help="Low-discrepancy Baja-envelope samples before fixed anchors are added.",
    )
    parser.add_argument("--only", action="append", help="Run only the named protocol(s).")
    parser.add_argument("--tests-only", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    if not args.skip_tests:
        subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(STUDY_ROOT / "tests"), "-v"],
            check=True,
        )
    if args.tests_only:
        return 0

    subprocess.run([sys.executable, str(VERIFY)], check=True)
    base_path = _resolve_base_case(args.base_case)
    print(f"Base simulation case: {base_path}")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    envelope_cases = build_baja_envelope(args.envelope_points)
    contact_cases = build_contact_stress_cases()
    inertia_cases = build_inertia_continuations()
    valid_names = (
        {p["name"] for p in BROAD_PROTOCOLS}
        | {p["name"] for p in CONTROLLED_PROTOCOLS}
        | {p["name"] for p in OVERRUN_PROTOCOLS}
        | {c.name for c in envelope_cases}
        | {c.name for c in contact_cases}
        | {c.name for c in inertia_cases}
    )
    if args.only:
        unknown = sorted(set(args.only) - valid_names)
        if unknown:
            raise ValueError("Unknown --only protocol(s): " + ", ".join(unknown))

    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)
    write_json(ARTIFACTS / "term_inventory.json", list(inventory()))

    # Direct equation analysis is independent of trajectory integration.  It
    # maps the final-equation coefficients over engaged ratio/contact space.
    if args.stage in {"all", "sensitivity", "envelope", "closure"}:
        from cinder.contracts import decode_simulation_case_document

        decoded_for_sensitivity = decode_simulation_case_document(base)
        print("\n=== Direct equation sensitivity ===")
        build_equation_sensitivity(
            system=decoded_for_sensitivity.system,
            document=base,
            output_dir=ARTIFACTS / "equation_sensitivity",
        )

    protocol_dir = ARTIFACTS / "resolved_protocols"
    protocol_dir.mkdir()
    summaries: dict[str, dict[str, Any]] = {}
    families: dict[str, str] = {}

    if args.stage in {"all", "broad"}:
        for protocol in BROAD_PROTOCOLS:
            if args.only and protocol["name"] not in args.only:
                continue
            document = _broad_document(base, protocol)
            case_path = protocol_dir / f"{protocol['name']}.json"
            write_json(case_path, document)
            print(f"\n=== {protocol['title']} ===")
            summaries[protocol["name"]] = run_case(
                case_path=case_path,
                name=protocol["name"],
                max_samples=args.max_samples,
                skip_environment_check=True,
                protocol=protocol,
            )
            families[protocol["name"]] = "broad"

    if args.stage in {"all", "controlled"}:
        controlled_document = _controlled_document(base)
        for protocol in CONTROLLED_PROTOCOLS:
            if args.only and protocol["name"] not in args.only:
                continue
            program = SmoothGradeProgram(
                start_time_s=CONTROLLED_START_TIME_S,
                rise_time_s=float(protocol["rise_time_s"]),
                target_grade_deg=float(protocol["target_grade_deg"]),
            )
            case_path = protocol_dir / f"{protocol['name']}.json"
            write_json(case_path, controlled_document)
            protocol_context = {
                **protocol,
                "family": "controlled",
                "purpose": (
                    "Controlled secondary road-load application. All cases are identical until "
                    f"t={CONTROLLED_START_TIME_S:.2f} s; only target grade or application time changes."
                ),
                "controlled_load": program.as_dict(),
            }

            def configure(system, *, _program=program):
                system.secondary_boundary = make_time_programmed_boundary(
                    base_boundary=system.secondary_boundary,
                    program=_program,
                )

            print(f"\n=== {protocol['title']} ===")
            summaries[protocol["name"]] = run_case(
                case_path=case_path,
                name=protocol["name"],
                max_samples=args.max_samples,
                skip_environment_check=True,
                protocol=protocol_context,
                configure_system=configure,
            )
            families[protocol["name"]] = "controlled"

    if args.stage in {"all", "envelope"}:
        write_rows(
            ARTIFACTS / "baja_envelope_design.csv",
            [
                {
                    "case": case.name,
                    "title": case.title,
                    "design_source": case.source,
                    "tune_variant": case.tune_variant,
                    "load_start_time_s": case.start_time_s,
                    "rise_time_s": case.rise_time_s,
                    "target_grade_deg": case.target_grade_deg,
                }
                for case in envelope_cases
            ],
        )
        print(f"\n=== Smart Baja operating envelope ({len(envelope_cases)} cases) ===")
        for index, case in enumerate(envelope_cases, start=1):
            if args.only and case.name not in args.only:
                continue
            document = _envelope_document(
                base, start_time_s=case.start_time_s, rise_time_s=case.rise_time_s
            )
            apply_tune_variant(document, case.tune_variant)
            case_path = protocol_dir / f"{case.name}.json"
            write_json(case_path, document)
            program = SmoothGradeProgram(
                start_time_s=case.start_time_s,
                rise_time_s=case.rise_time_s,
                target_grade_deg=case.target_grade_deg,
            )
            protocol_context = case.as_protocol()
            protocol_context["controlled_load"] = program.as_dict()
            protocol_context["design_bounds"] = {
                "grade_deg": [-20.0, 30.0],
                "load_start_time_s": [1.05, 3.35],
                "smooth_rise_time_s": [0.05, 0.80],
                "interpretation": (
                    "signed road-grade/load envelope during natural full-throttle Baja acceleration; "
                    "negative grade probes unloading/downhill but is not asserted to be closed-throttle overrun"
                ),
            }

            def configure_envelope(system, *, _program=program):
                system.secondary_boundary = make_time_programmed_boundary(
                    base_boundary=system.secondary_boundary,
                    program=_program,
                )

            print(
                f"[{index:02d}/{len(envelope_cases):02d}] {case.title}; "
                f"start={case.start_time_s:.3f}s; tune={case.tune_variant}"
            )
            summaries[case.name] = run_case(
                case_path=case_path,
                name=case.name,
                max_samples=args.max_samples,
                skip_environment_check=True,
                protocol=protocol_context,
                configure_system=configure_envelope,
            )
            families[case.name] = "baja_envelope"

    closure_failures: list[dict[str, Any]] = []
    if args.stage in {"all", "closure"}:
        print(f"\n=== Focused contact closure ({len(contact_cases)} cases) ===")
        for index, case in enumerate(contact_cases, start=1):
            if args.only and case.name not in args.only:
                continue
            document = _envelope_document(
                base, start_time_s=case.start_time_s, rise_time_s=case.rise_time_s
            )
            apply_contact_stress(document, case)
            case_path = protocol_dir / f"{case.name}.json"
            write_json(case_path, document)
            program = SmoothGradeProgram(
                start_time_s=case.start_time_s,
                rise_time_s=case.rise_time_s,
                target_grade_deg=case.target_grade_deg,
            )
            protocol_context = case.as_protocol()
            protocol_context["controlled_load"] = program.as_dict()

            def configure_contact(system, *, _program=program):
                system.secondary_boundary = make_time_programmed_boundary(
                    base_boundary=system.secondary_boundary, program=_program
                )

            print(f"[{index:02d}/{len(contact_cases):02d}] {case.title}")
            try:
                summaries[case.name] = run_case(
                    case_path=case_path,
                    name=case.name,
                    max_samples=args.max_samples,
                    skip_environment_check=True,
                    protocol=protocol_context,
                    configure_system=configure_contact,
                )
                families[case.name] = "contact_closure"
            except Exception as error:
                print(f"  CONTACT STRESS CASE FAILED: {type(error).__name__}: {error}")
                closure_failures.append({
                    "case": case.name,
                    "family": "contact_closure",
                    "error_type": type(error).__name__,
                    "message": str(error),
                })

        print(f"\n=== Controlled overrun ({len(OVERRUN_PROTOCOLS)} cases) ===")
        for protocol in OVERRUN_PROTOCOLS:
            if args.only and protocol["name"] not in args.only:
                continue
            document = copy.deepcopy(base)
            document["scenario"]["time_span_s"] = [0.0, CLOSURE_DURATION_S]
            document["shaft_boundaries"]["secondary"]["road_profile"] = {
                "kind": "constant_grade", "grade_angle_rad": 0.0
            }
            case_path = protocol_dir / f"{protocol['name']}.json"
            write_json(case_path, document)
            program = SmoothOverrunProgram(
                start_time_s=float(protocol["start_time_s"]),
                rise_time_s=float(protocol["rise_time_s"]),
                target_grade_deg=float(protocol["target_grade_deg"]),
                target_primary_torque_Nm=float(protocol["target_primary_torque_Nm"]),
            )
            context = {
                **protocol,
                "family": "overrun",
                "purpose": (
                    "Controlled power-flow reversal experiment. The reference engine/road boundaries "
                    "are used before the event; primary torque is then ramped to a specified resisting "
                    "torque while the road is ramped downhill. This is not a calibrated closed-throttle map."
                ),
                "controlled_overrun": program.as_dict(),
            }

            def configure_overrun(system, *, _program=program):
                primary, secondary = make_overrun_boundaries(
                    base_primary=system.primary_boundary,
                    base_secondary=system.secondary_boundary,
                    program=_program,
                )
                system.primary_boundary = primary
                system.secondary_boundary = secondary

            print(f"=== {protocol['title']} ===")
            try:
                summaries[protocol["name"]] = run_case(
                    case_path=case_path,
                    name=protocol["name"],
                    max_samples=args.max_samples,
                    skip_environment_check=True,
                    protocol=context,
                    configure_system=configure_overrun,
                )
                families[protocol["name"]] = "overrun"
            except Exception as error:
                print(f"  OVERRUN CASE FAILED: {type(error).__name__}: {error}")
                closure_failures.append({
                    "case": protocol["name"],
                    "family": "overrun",
                    "error_type": type(error).__name__,
                    "message": str(error),
                })

        print(f"\n=== Belt-inertia continuations ({len(inertia_cases)} cases) ===")
        for index, case in enumerate(inertia_cases, start=1):
            if args.only and case.name not in args.only:
                continue
            document, grade_program = _inertia_scenario_document(base, case.scenario)
            if case.kind == "coherent_density":
                apply_belt_density_scale(document, case.scale)
            case_path = protocol_dir / f"{case.name}.json"
            write_json(case_path, document)
            context = {
                "name": case.name,
                "title": case.title,
                "family": "inertia_continuation",
                "purpose": (
                    "Asymptotic belt-inertia continuation. global_transport isolates only the whole-belt "
                    "transport row; coherent_density scales belt density so global and local belt inertia "
                    "vanish together."
                ),
                "inertia_continuation": {
                    "scenario": case.scenario,
                    "kind": case.kind,
                    "scale": case.scale,
                },
            }
            if grade_program is not None:
                context["controlled_load"] = grade_program.as_dict()

            def configure_inertia(system, *, _case=case, _grade=grade_program):
                cleanup = None
                if _grade is not None:
                    system.secondary_boundary = make_time_programmed_boundary(
                        base_boundary=system.secondary_boundary, program=_grade
                    )
                if _case.kind == "global_transport":
                    cleanup = install_global_transport_inertia_scale(_case.scale)
                return cleanup

            print(f"[{index:02d}/{len(inertia_cases):02d}] {case.title}")
            try:
                summaries[case.name] = run_case(
                    case_path=case_path,
                    name=case.name,
                    max_samples=args.max_samples,
                    skip_environment_check=True,
                    protocol=context,
                    configure_system=configure_inertia,
                )
                families[case.name] = "inertia_continuation"
            except Exception as error:
                print(f"  INERTIA CASE FAILED: {type(error).__name__}: {error}")
                closure_failures.append({
                    "case": case.name,
                    "family": "inertia_continuation",
                    "error_type": type(error).__name__,
                    "message": str(error),
                })

    _synthesize(summaries, families)
    connection_summary = synthesize_sensitivity_connections(
        artifacts_dir=ARTIFACTS,
        families=families,
    )
    closure_summary = synthesize_closure(
        artifacts_dir=ARTIFACTS,
        families=families,
        failures=closure_failures,
    )
    write_json(
        ARTIFACTS / "stage_status.json",
        {
            "stage": "reduced-belt-final-closure",
            "governing_model_modified": False,
            "ablation_switches_present": False,
            "broad_protocol_count": sum(1 for family in families.values() if family == "broad"),
            "controlled_protocol_count": sum(1 for family in families.values() if family == "controlled"),
            "baja_envelope_protocol_count": sum(1 for family in families.values() if family == "baja_envelope"),
            "contact_closure_protocol_count": sum(1 for family in families.values() if family == "contact_closure"),
            "overrun_protocol_count": sum(1 for family in families.values() if family == "overrun"),
            "inertia_continuation_protocol_count": sum(1 for family in families.values() if family == "inertia_continuation"),
            "mixed_slip_found": closure_summary.get("contact", {}).get("mixed_slip_found"),
            "both_slip_found": closure_summary.get("contact", {}).get("both_slip_found"),
            "equation_sensitivity_generated": (ARTIFACTS / "equation_sensitivity" / "summary.json").is_file(),
            "baja_envelope_design": {
                "space_filling_count": args.envelope_points,
                "grade_bounds_deg": [-20.0, 30.0],
                "load_start_bounds_s": [1.05, 3.35],
                "rise_time_bounds_s": [0.05, 0.80],
                "documented_secondary_preload_robustness": {
                    "compression_m": [0.105, 0.110, 0.115],
                    "torsional_pretension_deg": [280.0, 300.0, 320.0],
                },
            },
            "threshold_definition": connection_summary.get("threshold_definition"),
            "next_action": (
                "Inspect contact_closure_summary.csv, mixed_slip_examples.csv, overrun_summary.csv, and "
                "inertia_continuation_comparison.csv. If mixed slip and true overrun were realized and the "
                "inertia continuations are converged, the reduced-belt transient-mechanics discovery study is "
                "ready for final synthesis rather than another broad search."
            ),
        },
    )
    print(f"\nExploration artifacts: {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
