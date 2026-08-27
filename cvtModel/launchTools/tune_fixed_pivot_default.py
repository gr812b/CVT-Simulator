"""Coordinate-search the physical fixed-pivot Baja default.

This is intentionally a practical calibration helper, not an optimizer that
changes measured geometry.  It keeps the fixed arm length, roller radius,
pivot, Point A, flyweight count, and arm mass unchanged.  It tunes only:

- concentrated tip-hardware mass per flyweight;
- physical ramp angles;
- secondary helix angle;
- secondary torsional preload;
- secondary compression preload.

Target behavior:
- lower-stop release near 2000 rpm (primary preload is re-resolved each run);
- clutch/contact slip ends promptly;
- the main shift holds primary speed near 3200 rpm;
- full shift is reached cleanly within the flat-launch window.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_route_grade_response as route  # noqa: E402
from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid  # noqa: E402
from cinder.contracts.document import encode_assembly_document  # noqa: E402

RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3


def default_candidate() -> route.TuneCandidate:
    return route.TuneCandidate(
        flyweight_mass_kg=0.25,
        helix_angle_degrees=20.0,
        secondary_torsional_pretension_degrees=300.0,
        secondary_compression_preload_mm=110.0,
        primary_ramp_kind="fixed_pivot_piecewise",
        primary_ramp_angle_degrees=35.0,
        primary_ramp_start_angle_degrees=35.0,
        primary_ramp_end_angle_degrees=10.0,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/fixed_pivot_tuning"),
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help=(
            "Overwrite launchTools/presets/circular_traction_first_reference.json "
            "with the best candidate."
        ),
    )
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--report-step-s", type=float, default=0.02)
    parser.add_argument("--rtol", type=float, default=1.0e-3)
    parser.add_argument("--atol", type=float, default=1.0e-6)
    parser.add_argument("--max-step-s", type=float, default=0.03)
    return parser.parse_args()


def evaluate_candidate(
    candidate: route.TuneCandidate,
    *,
    duration_s: float,
    report_step_s: float,
    rtol: float,
    atol: float,
    max_step_s: float,
) -> dict[str, object]:
    programme = route.GradeProgramme.default()
    try:
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
            host_state=system.host.initial_state(
                secondary_shaft_angle=0.0
            ),
        )
        initial_mode = system.classify_initial_mode(initial_full)
        result = integrate_hybrid(
            system=system,
            time_span=(0.0, duration_s),
            initial_state=initial_full,
            initial_mode=initial_mode,
            settings=HybridIntegratorSettings(
                relative_tolerance=rtol,
                absolute_tolerance=atol,
                method="LSODA",
                max_step=max_step_s,
                maximum_transitions=100,
                retain_dense_output=True,
            ),
        )
        if not result.completed:
            return {
                "ok": False,
                "score": 1.0e9,
                "reason": result.termination_reason,
                "candidate": candidate,
            }

        trace = route.sample_trace(
            system,
            result,
            programme,
            report_step_s=report_step_s,
        )
    except Exception as error:
        return {
            "ok": False,
            "score": 1.0e9,
            "reason": f"{type(error).__name__}: {error}",
            "candidate": candidate,
        }

    t = trace.time
    rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    deadzone_mm = resolved.constants.deadzone_shift / MILLIMETRE
    full_mm = resolved.constants.max_shift / MILLIMETRE

    engagement_time = 0.0
    for record in result.transitions:
        if "primary_closed_into_engaged_contact" in record.transition.reason:
            engagement_time = float(record.time)
            break

    slip_mask = np.asarray(
        ["slip" in mode.lower() for mode in trace.mode],
        dtype=bool,
    )
    post_engage_slip = slip_mask & (t >= engagement_time - 1.0e-9)
    if np.any(post_engage_slip):
        slip_end = float(t[np.flatnonzero(post_engage_slip)[-1]])
        slip_duration = max(0.0, slip_end - engagement_time)
    else:
        slip_end = engagement_time
        slip_duration = 0.0

    full_indices = np.flatnonzero(shift_mm >= full_mm - 0.20)
    full_shift_time = (
        float(t[full_indices[0]])
        if full_indices.size
        else float("nan")
    )

    plateau_mask = (
        (t >= slip_end)
        & (shift_mm >= deadzone_mm + 0.5)
        & (shift_mm <= full_mm - 0.5)
    )
    if np.count_nonzero(plateau_mask) < 8:
        plateau_mask = (
            (t >= slip_end)
            & (shift_mm >= deadzone_mm + 0.25)
            & (shift_mm <= full_mm - 0.2)
        )

    if np.count_nonzero(plateau_mask) >= 4:
        plateau_rpm = rpm[plateau_mask]
        plateau_mean = float(np.mean(plateau_rpm))
        plateau_std = float(np.std(plateau_rpm))
        plateau_rmse = float(
            np.sqrt(np.mean((plateau_rpm - 3200.0) ** 2))
        )
    else:
        plateau_mean = float("nan")
        plateau_std = float("nan")
        plateau_rmse = 1500.0

    # Score has interpretable scales rather than arbitrary giant weights:
    # 100 rpm RMS ~= 1 score unit; 0.25 s excess slip ~= 1 unit.
    score = plateau_rmse / 100.0
    score += max(0.0, slip_duration - 0.50) / 0.25

    if np.isfinite(full_shift_time):
        # We want enough time for a real shift plateau, but full shift during
        # the 10 s flat-launch window.
        if full_shift_time < 3.0:
            score += (3.0 - full_shift_time) * 2.0
        if full_shift_time > 8.5:
            score += (full_shift_time - 8.5) * 2.0
    else:
        score += 25.0

    max_rpm = float(np.max(rpm))
    if max_rpm > 3750.0:
        score += (max_rpm - 3750.0) / 50.0

    score += 0.10 * max(0, len(result.transitions) - 12)

    return {
        "ok": True,
        "score": float(score),
        "candidate": candidate,
        "resolved_primary_preload_mm": (
            resolved.resolved_primary_preload_mm
        ),
        "engagement_time_s": engagement_time,
        "slip_duration_after_engagement_s": slip_duration,
        "plateau_mean_rpm": plateau_mean,
        "plateau_std_rpm": plateau_std,
        "plateau_rmse_from_3200_rpm": plateau_rmse,
        "full_shift_time_s": full_shift_time,
        "max_primary_rpm": max_rpm,
        "transitions": len(result.transitions),
    }


def candidate_payload(candidate: route.TuneCandidate) -> dict[str, object]:
    return {
        "name": "fixed_pivot_3200_reference",
        "purpose": (
            "Physical fixed-pivot primary tune selected for prompt re-stick, "
            "approximately 3200 rpm main shift, and complete flat-launch shift."
        ),
        "candidate": {
            "flyweight_mass_kg": candidate.flyweight_mass_kg,
            "helix_angle_degrees": candidate.helix_angle_degrees,
            "secondary_torsional_pretension_degrees": (
                candidate.secondary_torsional_pretension_degrees
            ),
            "secondary_compression_preload_mm": (
                candidate.secondary_compression_preload_mm
            ),
            "primary_ramp_kind": candidate.primary_ramp_kind,
            "primary_ramp_angle_degrees": (
                candidate.primary_ramp_angle_degrees
            ),
            "primary_ramp_start_angle_degrees": (
                candidate.primary_ramp_start_angle_degrees
            ),
            "primary_ramp_end_angle_degrees": (
                candidate.primary_ramp_end_angle_degrees
            ),
        },
        "fixed_pivot_mass_semantics": {
            "flyweight_mass_kg": (
                "concentrated tip-hardware mass per flyweight; "
                "13.646 g arm/body is added separately"
            )
        },
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    current = default_candidate()
    all_results: list[dict[str, object]] = []

    stages = (
        (
            "tip_mass",
            [
                replace(current, flyweight_mass_kg=value)
                for value in (0.20, 0.225, 0.25, 0.275, 0.30)
            ],
        ),
        (
            "linear_angle",
            [
                replace(current, primary_ramp_angle_degrees=value)
                for value in (30.0, 35.0, 40.0)
            ],
        ),
        (
            "circle_start",
            [
                replace(current, primary_ramp_start_angle_degrees=value)
                for value in (32.0, 35.0, 38.0)
            ],
        ),
        (
            "circle_end",
            [
                replace(current, primary_ramp_end_angle_degrees=value)
                for value in (8.0, 10.0, 14.0)
            ],
        ),
        (
            "helix_angle",
            [
                replace(current, helix_angle_degrees=value)
                for value in (18.0, 20.0, 22.0)
            ],
        ),
        (
            "secondary_twist",
            [
                replace(
                    current,
                    secondary_torsional_pretension_degrees=value,
                )
                for value in (280.0, 300.0, 320.0)
            ],
        ),
        (
            "secondary_preload",
            [
                replace(
                    current,
                    secondary_compression_preload_mm=value,
                )
                for value in (105.0, 110.0, 115.0)
            ],
        ),
    )

    # Rebuild each stage around the best candidate from the previous stage.
    for stage_name, _initial_variants in stages:
        if stage_name == "tip_mass":
            variants = [
                replace(current, flyweight_mass_kg=value)
                for value in (0.20, 0.225, 0.25, 0.275, 0.30)
            ]
        elif stage_name == "linear_angle":
            variants = [
                replace(current, primary_ramp_angle_degrees=value)
                for value in (30.0, 35.0, 40.0)
            ]
        elif stage_name == "circle_start":
            variants = [
                replace(
                    current,
                    primary_ramp_start_angle_degrees=value,
                )
                for value in (32.0, 35.0, 38.0)
            ]
        elif stage_name == "circle_end":
            variants = [
                replace(
                    current,
                    primary_ramp_end_angle_degrees=value,
                )
                for value in (8.0, 10.0, 14.0)
            ]
        elif stage_name == "helix_angle":
            variants = [
                replace(current, helix_angle_degrees=value)
                for value in (18.0, 20.0, 22.0)
            ]
        elif stage_name == "secondary_twist":
            variants = [
                replace(
                    current,
                    secondary_torsional_pretension_degrees=value,
                )
                for value in (280.0, 300.0, 320.0)
            ]
        else:
            variants = [
                replace(
                    current,
                    secondary_compression_preload_mm=value,
                )
                for value in (105.0, 110.0, 115.0)
            ]

        stage_results = []
        for index, candidate in enumerate(variants, start=1):
            print(
                f"[{stage_name} {index}/{len(variants)}] "
                f"{candidate.label()}"
            )
            result = evaluate_candidate(
                candidate,
                duration_s=args.duration_s,
                report_step_s=args.report_step_s,
                rtol=args.rtol,
                atol=args.atol,
                max_step_s=args.max_step_s,
            )
            result["stage"] = stage_name
            stage_results.append(result)
            all_results.append(result)
            print(
                f"  score={result['score']:.3f}; "
                f"reason={result.get('reason', 'ok')}"
            )

        valid = [item for item in stage_results if item["ok"]]
        if valid:
            best = min(valid, key=lambda item: float(item["score"]))
            current = best["candidate"]
            print(f"BEST {stage_name}: {current.label()}")

    final = evaluate_candidate(
        current,
        duration_s=args.duration_s,
        report_step_s=args.report_step_s,
        rtol=args.rtol,
        atol=args.atol,
        max_step_s=args.max_step_s,
    )
    final["stage"] = "final"
    all_results.append(final)

    serializable = []
    for item in all_results:
        row = {
            key: value
            for key, value in item.items()
            if key != "candidate"
        }
        candidate = item["candidate"]
        row["candidate"] = candidate_payload(candidate)["candidate"]
        serializable.append(row)

    (args.output_dir / "fixed_pivot_tuning_results.json").write_text(
        json.dumps(serializable, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    best_payload = candidate_payload(current)
    best_path = args.output_dir / "fixed_pivot_3200_best.json"
    best_path.write_text(
        json.dumps(best_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\nFINAL")
    print(json.dumps(
        {
            key: value
            for key, value in final.items()
            if key != "candidate"
        },
        indent=2,
        allow_nan=True,
    ))
    print(current.label())
    print(f"Wrote {best_path}")

    if args.install:
        target = (
            HERE
            / "presets"
            / "circular_traction_first_reference.json"
        )
        target.write_text(
            json.dumps(best_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Installed best candidate to {target}")

        # Keep the backend's normal Baja launch preset on exactly the same
        # physical assembly.  Encoding the built assembly avoids duplicating
        # the fixed-pivot/C3 contract by hand.
        programme = route.GradeProgramme.default()
        resolved = route.resolve_primary_preload(
            current,
            target_engagement_rpm=2000.0,
            programme=programme,
        )
        assembly, _engine, _road = route.build_components(
            resolved.constants
        )
        encoded_assembly = encode_assembly_document(assembly)

        repo_root = HERE.parents[1]
        backend_preset = (
            repo_root / "backend/presets/baja-launch-baseline.json"
        )
        if backend_preset.exists():
            document = json.loads(
                backend_preset.read_text(encoding="utf-8")
            )
            document["simulation_case"]["assembly"] = encoded_assembly
            document["description"] = (
                "Physical fixed-pivot Baja default selected by "
                "tune_fixed_pivot_default.py: prompt clutch re-stick, "
                "~3200 rpm main shift target, dynamic flyweight and helix "
                "rotational/axial coupling enabled."
            )
            backend_preset.write_text(
                json.dumps(document, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Installed matching assembly to {backend_preset}")


if __name__ == "__main__":
    main()
